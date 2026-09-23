"""种春风·五育成长画像域 路由（A0 §6，挂载前缀 /api/v1/portfolio）。

集成接入：main.py 加一行
    app.include_router(portfolio.router, prefix="/api/v1")
"""
from __future__ import annotations

import datetime
import os
import re
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.grading.file_auth import user_id_from_request
from app.models.assessment_comment import AssessmentComment
from app.models.class_model import Class
from app.models.report_snapshot import ReportSnapshot
from app.models.student_growth_record import StudentGrowthRecord
from app.models.student_memory import StudentMemory
from app.schemas.common import ApiResponse
from app.schemas.portfolio.models import (
    CommentConfirmRequest,
    CommentGenerateRequest,
    GrowthRecordCreate,
    MemoryItem,
    ReportFreezeRequest,
)
from app.services.portfolio.comment import FALLBACK_COMMENT, build_comment_messages, sanitize_comment
from app.services.portfolio.llm import generate_comment
from app.services.portfolio.pdf import render_growth_album_pdf, render_report_pdf
from app.services.portfolio.repository import PortfolioRepository
from app.services.ai_policy import require_ai_access
from app.services.assessment.access import get_parent_bound_student_ids
from app.utils.anonymize import Anonymizer
from app.utils.class_access import can_view_class, get_class_role
from app.utils.security import build_download_url
from app.services.audit.access_log import log_access, resolve_user_role

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# 画像维度集合（五育 + AI 素养，E02）。查询/校验用，与 event_catalog.DIMENSIONS 一致。
DIMENSIONS_SET = {"moral", "intellectual", "physical", "aesthetic", "labor", "ai_literacy"}


# ── 内部工具 ────────────────────────────────────────

def _parse_term(term: str) -> tuple[datetime.datetime, datetime.datetime]:
    """解析 '2025-2026-1' → (date_from, date_to)。非法格式 422。"""
    m = re.match(r"^(\d{4})-(\d{4})-([12])$", str(term))
    if not m:
        raise HTTPException(status_code=422, detail="term 格式应为 学年-学年-学期，如 2025-2026-1")
    y1, y2, half = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y2 != y1 + 1:
        raise HTTPException(status_code=422, detail="term 学年范围应连续，如 2025-2026-1")
    tz = datetime.timezone.utc
    if half == 1:  # 上学期：当年 9/1 ~ 次年 1/31
        return (datetime.datetime(y1, 9, 1, tzinfo=tz),
                datetime.datetime(y2, 1, 31, 23, 59, 59, tzinfo=tz))
    # 下学期：当年 2/1 ~ 当年 7/31
    return (datetime.datetime(y2, 2, 1, tzinfo=tz),
            datetime.datetime(y2, 7, 31, 23, 59, 59, tzinfo=tz))


def _parse_date(s: str) -> datetime.datetime:
    try:
        return datetime.datetime.strptime(str(s), "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")


def _parse_month(month: str) -> tuple[datetime.datetime, datetime.datetime]:
    """解析 '2025-09' → (month_from, month_to) 当月首日 00:00 ~ 末日 23:59:59 UTC。非法格式 422。"""
    m = re.match(r"^(\d{4})-(\d{2})$", str(month))
    if not m:
        raise HTTPException(status_code=422, detail="month 格式应为 YYYY-MM，如 2025-09")
    year, mon = int(m.group(1)), int(m.group(2))
    if not 1 <= mon <= 12:
        raise HTTPException(status_code=422, detail="month 月份应在 1-12 之间")
    tz = datetime.timezone.utc
    start = datetime.datetime(year, mon, 1, tzinfo=tz)
    if mon == 12:
        end = datetime.datetime(year + 1, 1, 1, tzinfo=tz) - datetime.timedelta(seconds=1)
    else:
        end = datetime.datetime(year, mon + 1, 1, tzinfo=tz) - datetime.timedelta(seconds=1)
    return start, end


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _get_student_or_404(repo: PortfolioRepository, db: Session, user_id: str, student_id: str) -> dict:
    """查学生并做跨班隔离（非本班/本校 → 404，与不存在同处理，防信息泄露）。"""
    student = repo.get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    class_id = str(student.get("class_id") or "")
    if class_id and not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="学生不存在")
    return student


def _require_class_write(db: Session, user_id: str, student: dict) -> None:
    """写操作权限：本班教师及以上（head/deputy/teacher/管理员）。"""
    class_id = str(student.get("class_id") or "")
    if not class_id:
        raise HTTPException(status_code=403, detail="无权限操作该资源")
    if get_class_role(db, user_id, class_id) is None:
        raise HTTPException(status_code=403, detail="无权限操作该班级")


def _log_access(
    db: Session,
    user_id: str,
    action: str,
    target_type: str,
    target_id: str,
    detail: Optional[dict] = None,
) -> None:
    """E03/E14 访问留痕助手（写失败不阻断主流程）。"""
    role = resolve_user_role(db, user_id)
    log_access(
        db,
        user_id=user_id,
        user_role=role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )


def _class_info(db: Session, class_id: str) -> dict:
    if not class_id:
        return {"class_name": None, "grade": None}
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c:
        return {"class_name": None, "grade": None}
    return {"class_name": c.name, "grade": c.grade}


def _growth_record_dict(r, indicator_names: Optional[dict] = None) -> dict:
    indicator_id = getattr(r, "indicator_id", None)
    indicator_name = (indicator_names or {}).get(indicator_id) if indicator_id else None
    return {
        "id": r.id,
        "student_id": r.student_id,
        "class_id": r.class_id,
        "dimension": r.dimension,
        "source_type": r.source_type,
        "source_id": r.source_id,
        "indicator_id": indicator_id,
        "indicator_name": indicator_name,
        "growth_point": r.growth_points,
        "evidence": r.evidence,
        "note": r.note,
        "created_by": r.created_by,
        "occurred_at": _iso(r.occurred_at),
        "created_at": _iso(r.created_at),
    }


# ── §6.1 学生五育画像 ─────────────────────────────

@router.get("/students/{student_id}")
def get_portfolio(
    student_id: str,
    trend: bool = Query(False, description="是否返回按月趋势"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    grade = _class_info(db, str(student.get("class_id") or ""))["grade"]
    data = repo.compute_portfolio(student, grade=grade, with_trend=trend)
    _log_access(db, user_id, "view_portfolio", "student", student_id, {"trend": bool(trend)})
    return ApiResponse(data=data)


# ── §6.2 成长记录列表 ─────────────────────────────

@router.get("/students/{student_id}/growth-records")
def list_growth_records(
    student_id: str,
    dimension: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    _get_student_or_404(repo, db, user_id, student_id)
    if dimension and dimension not in DIMENSIONS_SET:
        raise HTTPException(status_code=422, detail="dimension 不在五育枚举中")
    from_dt = _parse_date(date_from) if date_from else None
    to_dt = _parse_date(date_to) if date_to else None
    result = repo.list_growth_records(
        student_id, dimension=dimension, date_from=from_dt, date_to=to_dt,
        page=page, page_size=pageSize)
    _log_access(db, user_id, "view_growth", "student", student_id, {"dimension": dimension})
    indicator_names = repo.indicator_map()
    return ApiResponse(data={
        "rows": [_growth_record_dict(r, indicator_names) for r in result["rows"]],
        "total": result["total"],
        "page": result["page"],
        "pageSize": result["pageSize"],
    })


# ── §6.2b 二级指标字典 ────────────────────────────

@router.get("/indicators")
def list_indicators(
    dimension: Optional[str] = Query(None, description="按五育维度过滤（可选）"),
    include_inactive: bool = Query(False, description="是否包含已停用指标"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[list]:
    del user_id
    repo = PortfolioRepository(db)
    if dimension and dimension not in DIMENSIONS_SET:
        raise HTTPException(status_code=422, detail="dimension 不在五育枚举中")
    data = repo.list_indicators(dimension=dimension, include_inactive=include_inactive)
    return ApiResponse(data=data)


@router.get("/indicators/tree")
def list_indicator_tree(
    dimension: Optional[str] = Query(None, description="按五育维度过滤（可选），返回该维度子树"),
    include_inactive: bool = Query(False, description="是否包含已停用指标"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[list]:
    """层级指标树（E01）：维度(level=1) → 方面(level=2) → 观测点(level=3)，嵌套 children 返回。"""
    del user_id
    repo = PortfolioRepository(db)
    if dimension and dimension not in DIMENSIONS_SET:
        raise HTTPException(status_code=422, detail="dimension 不在五育枚举中")
    data = repo.list_indicator_tree(dimension=dimension, include_inactive=include_inactive)
    return ApiResponse(data=data)


# ── §6.3 录入成长记录 ─────────────────────────────

@router.post("/students/{student_id}/growth-records")
def create_growth_record(
    student_id: str,
    body: GrowthRecordCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    _require_class_write(db, user_id, student)
    if body.indicator_id:
        ind = repo.get_indicator(body.indicator_id)
        if not ind or not ind.get("is_active"):
            raise HTTPException(status_code=422, detail="indicator_id 无效或已停用")
        if ind.get("dimension") != body.dimension:
            raise HTTPException(status_code=422, detail="indicator_id 与 dimension 不一致")
    rec = repo.create_growth_record(
        student_id=student_id,
        class_id=str(student.get("class_id") or ""),
        school_id=str(student.get("school_id") or "") or None,
        dimension=body.dimension,
        source_type=body.source_type,  # E02：manual / ai_course / ai_project
        growth_point=body.growth_point,
        created_by=user_id,
        source_id=body.source_id,
        evidence=body.evidence,
        note=body.note,
        indicator_id=body.indicator_id,
    )
    indicator_names = repo.indicator_map() if body.indicator_id else None
    return ApiResponse(message="成长记录已录入", data=_growth_record_dict(rec, indicator_names))


# ── §6.3b 删除成长记录 ─────────────────────────────

@router.delete("/students/{student_id}/growth-records/{record_id}")
def delete_growth_record(
    student_id: str,
    record_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    _require_class_write(db, user_id, student)
    record = (db.query(StudentGrowthRecord)
              .filter(StudentGrowthRecord.id == record_id,
                      StudentGrowthRecord.student_id == student_id)
              .first())
    if not record:
        raise HTTPException(status_code=404, detail="not_found: 成长记录不存在")
    db.delete(record)
    db.commit()
    return ApiResponse(data={"id": record_id, "deleted": True})


# ── §6.4 学期报告（快照优先 → 实时聚合）────────────

def _resolve_report(db: Session, repo: PortfolioRepository, student: dict,
                    term: str, term_from, term_to,
                    version: Optional[int]) -> tuple[dict, bool]:
    """返回 (report, from_snapshot)。version 指定且不存在 → 404。"""
    snap = repo.find_report_snapshot(str(student["id"]), term, version=version)
    if version is not None and not snap:
        raise HTTPException(status_code=404, detail="报告快照不存在")
    if snap:
        report = dict(snap.payload)
        report["from_snapshot"] = True
        report["version"] = snap.version
        return report, True
    grade = _class_info(db, str(student.get("class_id") or ""))["grade"]
    report = repo.compute_report_for_student(student, term, term_from, term_to, grade=grade)
    report["from_snapshot"] = False
    report["version"] = None
    return report, False


@router.get("/students/{student_id}/report")
def get_report(
    student_id: str,
    term: str = Query(...),
    version: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    term_from, term_to = _parse_term(term)
    report, _ = _resolve_report(db, repo, student, term, term_from, term_to, version)
    _log_access(db, user_id, "view_report", "student", student_id, {"term": term, "version": version})
    return ApiResponse(data=report)


@router.get("/students/{student_id}/monthly-report")
def get_monthly_report(
    student_id: str,
    month: str = Query(..., description="月度 'YYYY-MM'，如 2025-09"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    """月度报告（实时聚合，不含快照）：按当月区间转调 compute_report_for_student，term 存 'YYYY-MM'。

    返回结构与 GET /report 一致（term=YYYY-MM），前端月度报告直接复用现有 ReportBody。
    """
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    month_from, month_to = _parse_month(month)
    grade = _class_info(db, str(student.get("class_id") or ""))["grade"]
    report = repo.compute_report_for_student(student, month, month_from, month_to, grade=grade)
    report["from_snapshot"] = False
    report["version"] = None
    _log_access(db, user_id, "view_report", "student", student_id, {"month": month})
    return ApiResponse(data=report)


# ── §6.5 冻结学期报告 ─────────────────────────────

@router.post("/students/{student_id}/report/freeze")
def freeze_report(
    student_id: str,
    body: ReportFreezeRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    _require_class_write(db, user_id, student)
    term_from, term_to = _parse_term(body.term)
    grade = _class_info(db, str(student.get("class_id") or ""))["grade"]
    report = repo.compute_report_for_student(student, body.term, term_from, term_to, grade=grade)
    snap = repo.create_report_snapshot(
        student_id=student_id,
        term=body.term,
        class_id=str(student.get("class_id") or ""),
        school_id=str(student.get("school_id") or "") or None,
        payload=report,
        generated_by=user_id,
    )
    if not snap:
        raise HTTPException(status_code=500, detail="报告快照写入失败")
    data = {**report, "from_snapshot": True, "version": snap.version}
    return ApiResponse(message=f"报告已冻结 (v{snap.version})", data=data)


# ── §6.6 查看 AI 评语 ─────────────────────────────

@router.get("/students/{student_id}/report/comment")
def get_comment(
    student_id: str,
    term: str = Query(...),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    _get_student_or_404(repo, db, user_id, student_id)
    _parse_term(term)  # 校验格式
    section = repo.get_comment_section(student_id, term)
    return ApiResponse(data=section)


# ── §6.7 生成 AI 评语 ─────────────────────────────

@router.post("/students/{student_id}/report/comment/generate")
def generate_comment_endpoint(
    student_id: str,
    body: CommentGenerateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    _require_class_write(db, user_id, student)
    # E08 · 学校级 AI 管控：AI 学业评语开关关闭时一律 403
    require_ai_access(db, user_id, "ai_comment")
    term_from, term_to = _parse_term(body.term)
    grade = _class_info(db, str(student.get("class_id") or ""))["grade"]
    report = repo.compute_report_for_student(student, body.term, term_from, term_to, grade=grade)
    # E08 · PII 防护：登记学生真名 → build_comment_messages 拼 prompt 时匿名化，返回后再还原
    anon = Anonymizer()
    anon.anon(str(student.get("name") or "该学生"))
    # S2 注入：学期评语为五育整体画像，report 暂无单一 subject 维度；
    # 传 report.get("subject")（当前恒 None，行为不变），待 subject 维度接入后自动生效。
    messages = build_comment_messages(report, anon=anon, subject=report.get("subject"))
    llm = generate_comment(db, messages)
    if llm["ok"]:
        content = anon.restore_text(llm["content"])
        content, flagged = sanitize_comment(content)
        status = "ai_generated"
        message = "评语已生成（待教师确认）" if not flagged else "评语已生成（含禁词已清洗）"
    else:
        content, flagged = FALLBACK_COMMENT, False
        status = "ai_failed"
        message = "评语生成失败（AI 网关不可用），已记录兜底状态"

    existing = (db.query(AssessmentComment)
                .filter(AssessmentComment.student_id == student_id,
                        AssessmentComment.term == body.term).first())
    if existing:
        existing.ai_content = content
        existing.status = status
        existing.ai_model = llm.get("model")
        existing.tokens_used = llm.get("tokens_used")
        existing.cost_cent = llm.get("cost_cent")
        existing.gate_flagged = flagged
        existing.created_by = user_id
        db.commit()
    else:
        c = AssessmentComment(
            student_id=student_id,
            term=body.term,
            class_id=str(student.get("class_id") or ""),
            school_id=str(student.get("school_id") or "") or None,
            status=status,
            ai_content=content,
            ai_model=llm.get("model"),
            tokens_used=llm.get("tokens_used"),
            cost_cent=llm.get("cost_cent"),
            gate_flagged=flagged,
            created_by=user_id,
        )
        db.add(c)
        db.commit()

    section = repo.get_comment_section(student_id, body.term)
    return ApiResponse(message=message, data=section)


# ── §6.8 确认评语 ─────────────────────────────────

@router.post("/students/{student_id}/report/comment/confirm")
def confirm_comment(
    student_id: str,
    body: CommentConfirmRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    _require_class_write(db, user_id, student)
    _parse_term(body.term)
    c = (db.query(AssessmentComment)
         .filter(AssessmentComment.student_id == student_id,
                 AssessmentComment.term == body.term).first())
    if not c:
        raise HTTPException(status_code=400, detail="该学期尚无评语，请先生成")
    if c.status == "ai_failed":
        raise HTTPException(status_code=400, detail="评语生成失败，无法确认，请重新生成")
    content = (body.content or "").strip() if body.content else ""
    if not content:
        content = (c.ai_content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="评语内容为空，请先生成或填写内容")
    content, flagged = sanitize_comment(content)
    if flagged:
        raise HTTPException(status_code=422, detail="确认评语含人格归因词，请修改后重试")
    c.confirmed_content = content
    c.status = "confirmed"
    c.confirmed_by = user_id
    c.confirmed_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    section = repo.get_comment_section(student_id, body.term)
    return ApiResponse(message="评语已确认", data=section)


# ── §6.9 下载 PDF 报告 ────────────────────────────

@router.get("/students/{student_id}/report/pdf")
def get_report_pdf(
    student_id: str,
    term: str = Query(...),
    version: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    term_from, term_to = _parse_term(term)
    report, from_snapshot = _resolve_report(db, repo, student, term, term_from, term_to, version)
    info = _class_info(db, str(student.get("class_id") or ""))
    pdf_bytes = render_report_pdf(
        report,
        report.get("comment"),
        school_name=info["class_name"],
        version=report.get("version") if from_snapshot else None,
    )
    _log_access(db, user_id, "export", "student", student_id, {"term": term, "pdf": True})
    filename = f"学期成长报告_{student.get('name') or '学生'}_{term}.pdf"
    quoted = quote(filename)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


# ── §6.9b 下载成长纪念册 PDF（G1）────────────────────

@router.get("/students/{student_id}/growth-album/pdf")
def get_growth_album_pdf(
    student_id: str,
    term: str = Query(...),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """合成并下载「成长纪念册」PDF：封面 + 教师评语 + 学期照片 + 学期成长记录。

    MVP 时间窗：照片按 created_at、成长记录按 occurred_at 落在 term 区间内。
    权限沿用本路由器默认依赖（跨班隔离 + JWT 鉴权），与 /report/pdf 一致。
    """
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    term_from, term_to = _parse_term(term)
    grade = _class_info(db, str(student.get("class_id") or ""))["grade"]
    report = repo.compute_report_for_student(student, term, term_from, term_to, grade=grade)
    comment = repo.get_comment_section(student_id, term)

    # 学期照片（created_at 时间窗；物理文件缺失的项传 file_path=None，渲染层跳过）
    mem_rows = (
        db.query(StudentMemory)
        .filter(StudentMemory.student_id == student_id,
                StudentMemory.created_at >= term_from,
                StudentMemory.created_at <= term_to)
        .order_by(StudentMemory.created_at.desc())
        .all()
    )
    memories = []
    for r in mem_rows:
        try:
            resolved = _resolve_memory_file(r.image_path)
            file_path = str(resolved)
        except HTTPException:
            file_path = None
        memories.append({
            "id": r.id,
            "image_path": r.image_path,
            "file_path": file_path,
            "caption": r.caption,
            "created_at": _iso(r.created_at),
        })

    # 学期成长记录（occurred_at 时间窗）
    rec_rows = (
        db.query(StudentGrowthRecord)
        .filter(StudentGrowthRecord.student_id == student_id,
                StudentGrowthRecord.occurred_at >= term_from,
                StudentGrowthRecord.occurred_at <= term_to)
        .order_by(StudentGrowthRecord.occurred_at.desc())
        .all()
    )
    indicator_names = repo.indicator_map()
    growth_records = [_growth_record_dict(r, indicator_names) for r in rec_rows]

    info = _class_info(db, str(student.get("class_id") or ""))
    pdf_bytes = render_growth_album_pdf(
        report,
        comment,
        memories=memories,
        growth_records=growth_records,
        school_name=info["class_name"],
        student_name=student.get("name"),
        term=term,
    )
    _log_access(db, user_id, "export", "student", student_id, {"term": term, "pdf": "growth_album"})
    filename = f"成长纪念册_{student.get('name') or '学生'}_{term}.pdf"
    quoted = quote(filename)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


# ── §6.9c 综评档案聚合（G3）────────────────────────

@router.get("/students/{student_id}/dossier")
def get_dossier(
    student_id: str,
    term: Optional[str] = Query(None, description="学年-学期，如 2025-2026-1；缺省返回全量/最近"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    """综评档案一体化查看：学期报告 + 成长记录明细 + 照片 + 奖章 + 学分流水 + 测评 + 成档状态。

    权限沿用本路由器默认依赖（跨班隔离 + JWT 鉴权），与 /report 一致。只读聚合，不写库。
    term 缺省时各明细取最近 N 条（全量区间），archive_status 为 None。
    """
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    if term:
        _parse_term(term)  # 校验格式（非法 422）
    grade = _class_info(db, str(student.get("class_id") or ""))["grade"]
    data = repo.compute_dossier(student, term=term, grade=grade)
    _log_access(db, user_id, "view_dossier", "student", student_id, {"term": term})
    return ApiResponse(data=data)


# ── §6.10 班级画像总览 ────────────────────────────

_TIER_ORDER = {"A+": 6, "A": 5, "B": 4, "C": 3, "D": 2}


def _metric_value(metric_map, default=float("-inf")):
    """从 per-dimension 指标映射（percentile/composite/rank…）取 total，缺省回退 default。"""
    if not isinstance(metric_map, dict):
        return default
    v = metric_map.get("total")
    return v if v is not None else default


def _sort_class_students(students: list, sort: str) -> tuple[list, str]:
    """班级学生排序：name / total(默认) / tier / percentile / composite。返回 (students, sorted_by)。"""
    if sort == "name":
        return sorted(students, key=lambda x: (x.get("name") or "")), "name"
    if sort == "tier":
        # 档位 A+ > A > B > C > D，同档按成长分降序
        key = lambda x: (_TIER_ORDER.get((x.get("tier") or {}).get("total"), 0),
                         x.get("total_growth_point") or 0)
        return sorted(students, key=key, reverse=True), "tier"
    if sort == "percentile":
        return (sorted(students, key=lambda x: _metric_value(x.get("percentile")), reverse=True),
                "percentile")
    if sort == "composite":
        return (sorted(students, key=lambda x: _metric_value(x.get("composite")), reverse=True),
                "composite")
    return sorted(students, key=lambda x: x.get("total_growth_point") or 0, reverse=True), "total"


@router.get("/classes/{class_id}")
def get_class_overview(
    class_id: str,
    sort: str = Query("total", description="total(默认) / name / tier / percentile / composite"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    info = _class_info(db, class_id)
    data = repo.compute_class_assessment(class_id)
    data["class_name"] = info["class_name"]
    data["grade"] = info["grade"]
    students, sorted_by = _sort_class_students(data["students"], sort)
    data["students"] = students
    data["sorted_by"] = sorted_by
    return ApiResponse(data=data)


# ── §6.10b 家长端（孩子五育画像）────────────────────

def _current_term(now: Optional[datetime.datetime] = None) -> str:
    """当前学年-学期：上学期 9/1~次年 1/31，下学期 2/1~7/31。"""
    now = now or datetime.datetime.now()
    y, m = now.year, now.month
    if m >= 9:
        return f"{y}-{y + 1}-1"
    if m <= 1:
        return f"{y - 1}-{y}-1"
    return f"{y - 1}-{y}-2"


def _parent_student_dict(db: Session, student: dict) -> dict:
    info = _class_info(db, str(student.get("class_id") or ""))
    return {
        "student_id": str(student.get("id") or ""),
        "name": student.get("name"),
        "class_id": str(student.get("class_id") or ""),
        "class_name": info["class_name"],
        "grade": info["grade"],
    }


@router.get("/parent/students")
def list_parent_students(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[list]:
    """家长查看已绑定孩子列表（家长身份以 parent_students 绑定表为准，见 access.get_parent_bound_student_ids）。"""
    repo = PortfolioRepository(db)
    students = []
    for sid in get_parent_bound_student_ids(db, user_id):
        student = repo.get_student(sid)
        if student:
            students.append(_parent_student_dict(db, student))
    return ApiResponse(data=students)


@router.get("/parent/students/{student_id}/overview")
def get_parent_student_overview(
    student_id: str,
    recent: int = Query(10, ge=1, le=50, description="最近成长记录条数"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    """家长查看绑定孩子的五育画像：实时画像（radar）+ 最近成长记录 + 学期报告摘要。

    归属校验：仅家长本人绑定的学生可访问（与不存在同处理，防信息泄露）。
    """
    repo = PortfolioRepository(db)
    if student_id not in get_parent_bound_student_ids(db, user_id):
        raise HTTPException(status_code=404, detail="学生不存在")
    student = repo.get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    info = _class_info(db, str(student.get("class_id") or ""))
    grade = info["grade"]

    # 实时五育画像（dimensions 扁平 → radar，含 total_growth_point）
    try:
        portfolio = repo.compute_portfolio(student, grade=grade)
    except Exception:  # noqa: BLE001 —— 画像计算失败降级为空，不阻断概览返回
        portfolio = {"dimensions": {}, "data_status": {}, "total_growth_point": 0}
    data_status = portfolio.get("data_status") or {}
    raw_dims = portfolio.get("dimensions") or {}
    # 无数据维度置 null（前端据此显示「数据不足」而非 0.0）
    dimensions = {
        dim: raw_dims.get(dim) if data_status.get(dim) == "has_data" else None
        for dim in DIMENSIONS_SET
    }
    total_growth_point = portfolio.get("total_growth_point")

    # 最近成长记录（复用 _growth_record_dict 口径，含 indicator_name）
    indicator_names = repo.indicator_map()
    rec_result = repo.list_growth_records(student_id, page=1, page_size=recent)
    recent_records = [_growth_record_dict(r, indicator_names) for r in rec_result["rows"]]

    # 学期报告摘要（快照优先 → 实时聚合当前学期）
    report = None
    snap = (db.query(ReportSnapshot)
            .filter(ReportSnapshot.student_id == student_id)
            .order_by(ReportSnapshot.created_at.desc())
            .first())
    if snap:
        payload = snap.payload or {}
        report = {"term": snap.term, "total_growth_point": payload.get("total_growth_point")}
    else:
        try:
            term = _current_term()
            term_from, term_to = _parse_term(term)
            rep = repo.compute_report_for_student(student, term, term_from, term_to, grade=grade)
            report = {"term": term, "total_growth_point": rep.get("total_growth_point")}
        except Exception:  # noqa: BLE001 —— 实时报告失败降级为空
            report = None

    _log_access(db, user_id, "view_parent_overview", "student", student_id, {"recent": recent})
    return ApiResponse(data={
        "student_id": student_id,
        "name": student.get("name"),
        "class_id": str(student.get("class_id") or ""),
        "class_name": info["class_name"],
        "grade": grade,
        "dimensions": dimensions,
        "total_growth_point": total_growth_point,
        "recent_growth_records": recent_records,
        "report": report,
    })


# ── §6.11 学生成长印记（动态相册）────────────────────

MEMORY_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
MEMORY_MAX_BYTES = 10 * 1024 * 1024
# 项目根目录下 assets/memories（与批改文件同一存储根）
MEMORY_ROOT = Path(__file__).resolve().parent.parent.parent / "assets" / "memories"


def _save_memory_image(file_bytes: bytes, filename: str) -> dict:
    """校验并保存单张成长照片到 assets/memories/，返回 {path, thumbPath}（相对路径）。"""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in MEMORY_ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="仅支持 JPG/PNG/HEIC/WebP 格式图片")
    if len(file_bytes) > MEMORY_MAX_BYTES:
        raise HTTPException(status_code=400, detail="图片大小不能超过 10MB")

    month_dir = datetime.datetime.utcnow().strftime("%Y-%m")
    abs_dir = MEMORY_ROOT / month_dir
    thumb_dir = abs_dir / "thumb"
    abs_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    new_name = f"{uuid.uuid4().hex}{ext}"
    with open(abs_dir / new_name, "wb") as f:
        f.write(file_bytes)

    # 生成缩略图（宽 400px），失败不影响上传
    try:
        from PIL import Image
        img = Image.open(abs_dir / new_name)
        img.thumbnail((400, 400))
        img.save(thumb_dir / new_name, quality=80)
    except Exception:
        pass

    return {
        "path": f"{month_dir}/{new_name}",
        "thumbPath": f"{month_dir}/thumb/{new_name}",
    }


def _resolve_memory_file(rel_path: str) -> Path:
    """将相对路径解析到 assets/memories/ 绝对路径，防目录穿越。"""
    if not rel_path:
        raise HTTPException(status_code=400, detail="无效路径")
    safe_rel = rel_path.replace("\\", "/")
    if safe_rel.startswith("/") or ".." in safe_rel.split("/"):
        raise HTTPException(status_code=403, detail="无效路径")
    file_path = (MEMORY_ROOT / safe_rel).resolve()
    if not file_path.is_relative_to(MEMORY_ROOT.resolve()):
        raise HTTPException(status_code=403, detail="无效路径")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return file_path


def _memory_thumb_path(image_path: str) -> str:
    """由原图相对路径推导缩略图相对路径：2026-08/a.jpg → 2026-08/thumb/a.jpg。"""
    p = (image_path or "").replace("\\", "/")
    i = p.rfind("/")
    if i == -1:
        return ""
    return f"{p[:i]}/thumb/{p[i + 1:]}"


def _memory_dict(r: StudentMemory, user_id: str) -> dict:
    """序列化单条记忆，并附带绑定当前用户 download ticket 的直链。"""
    thumb_rel = _memory_thumb_path(r.image_path)
    return {
        "id": r.id,
        "student_id": r.student_id,
        "class_id": r.class_id,
        "image_path": r.image_path,
        "download_url": build_download_url(f"portfolio/memories/{r.image_path}", user_id),
        "thumb_url": (
            build_download_url(f"portfolio/memories/{thumb_rel}", user_id) if thumb_rel else None
        ),
        "caption": r.caption,
        "source_type": r.source_type,
        "created_by": r.created_by,
        "created_at": _iso(r.created_at),
    }


@router.get("/students/{student_id}/memories", response_model=ApiResponse[list[MemoryItem]])
def list_memories(
    student_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[list]:
    repo = PortfolioRepository(db)
    _get_student_or_404(repo, db, user_id, student_id)
    rows = (
        db.query(StudentMemory)
        .filter(StudentMemory.student_id == student_id)
        .order_by(StudentMemory.created_at.desc())
        .all()
    )
    return ApiResponse(data=[_memory_dict(r, user_id) for r in rows])


@router.post("/students/{student_id}/memories", response_model=ApiResponse[MemoryItem])
def upload_memory(
    student_id: str,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    _require_class_write(db, user_id, student)
    contents = file.file.read()
    try:
        saved = _save_memory_image(contents, file.filename or "image.jpg")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"internal_error: 图片保存失败 {str(e)}")
    rec = StudentMemory(
        student_id=student_id,
        class_id=str(student.get("class_id") or ""),
        school_id=str(student.get("school_id") or "") or None,
        image_path=saved["path"],
        caption=(caption or "").strip() or None,
        source_type="memory",
        created_by=user_id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return ApiResponse(message="照片已上传", data=_memory_dict(rec, user_id))


@router.delete("/students/{student_id}/memories/{memory_id}")
def delete_memory(
    student_id: str,
    memory_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    repo = PortfolioRepository(db)
    student = _get_student_or_404(repo, db, user_id, student_id)
    _require_class_write(db, user_id, student)
    rec = (
        db.query(StudentMemory)
        .filter(StudentMemory.id == memory_id, StudentMemory.student_id == student_id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="not_found: 照片不存在")
    image_path = rec.image_path or ""
    thumb_rel = _memory_thumb_path(image_path)
    db.delete(rec)
    db.commit()
    # 删除物理文件（尽力而为，缺失不阻断）
    for rel in (image_path, thumb_rel):
        if not rel:
            continue
        try:
            p = _resolve_memory_file(rel)
            p.unlink(missing_ok=True)
        except Exception:
            pass
    return ApiResponse(data={"id": memory_id, "deleted": True})


@router.get("/memories/{memory_path:path}")
def serve_memory_file(memory_path: str, request: Request):
    """复用 download ticket 机制校验后返回成长照片（H2，资源绑定 portfolio/memories/{path}）。"""
    resource = f"portfolio/memories/{memory_path}"
    user_id_from_request(request, resource=resource)
    file_path = _resolve_memory_file(memory_path)
    return FileResponse(str(file_path))
