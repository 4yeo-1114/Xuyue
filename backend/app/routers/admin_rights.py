"""教师/管理员代办行权（E03 监护人同意闭环 · 数据主体权利）。

前缀 /admin/rights，挂载后为 /api/v1/admin/rights/...
提供学生个人信息汇总 / CSV 导出 / 更正 / 删除(匿名化)，全部写 access_log。

权限：复用 app/services/assessment/access.py 的角色判定 + app/utils/class_access.can_view_class。
  - 查询/导出/更正：管理员 或 该生班级教师（can_view_class 放行）
  - 删除(匿名化)：同上，但必须带 confirm=true 二次校验；实现为敏感字段匿名化 + 标记 deleted，
    不级联删子表（不炸库）。

原则：增量不破坏；异常不阻断主流程（留痕写失败仅记日志）。
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.assessment_result import AssessmentResult
from app.models.class_model import Class
from app.models.evaluation_archive import EvaluationArchive
from app.models.exam_score import ExamScore
from app.models.student import Student
from app.models.student_growth_record import StudentGrowthRecord
from app.models.student_portfolio import StudentPortfolio
from app.services.assessment import access as access_svc
from app.services.audit.access_log import log_access, resolve_user_role
from app.services.field_masking import mask_address, mask_name, mask_phone, mask_student_number
from app.utils.class_access import can_view_class, can_view_student_pii

router = APIRouter(prefix="/admin/rights", tags=["admin_rights"])

# 可更正字段白名单（联系方式类）。成绩/画像维度等敏感核心字段不允许"更正"（走删除匿名化）。
CORRECTABLE_FIELDS = {"phone", "parent_phone", "address", "parent_name", "notes"}

# 删除匿名化涉及的敏感字段
ANONYMIZE_FIELDS = {
    "name": "已删除学生",
    "student_number": "",
    "phone": None,
    "parent_name": None,
    "parent_phone": None,
    "address": None,
    "birthday": None,
    "gender": None,
    "cadre_role": None,
    "notes": None,
}


class CorrectRequest(BaseModel):
    student_id: str
    field: str
    value: str = ""


def _iso(v) -> Optional[str]:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _get_student(db: Session, student_id: str) -> Student:
    s = db.query(Student).filter(Student.id == student_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="学生不存在")
    return s


def _require_rights_perm(db: Session, user_id: str, student: Student) -> None:
    """行权权限：管理员 或 该生班级教师。无权限 403。"""
    if access_svc.is_admin(db, user_id):
        return
    if access_svc.is_teacher(db, user_id) and can_view_class(db, user_id, student.class_id):
        return
    raise HTTPException(status_code=403, detail="无权限对该学生执行行权操作")


def _consent_status(db: Session, student_id: str) -> str:
    latest = (
        db.query(AssessmentResult)
        .filter(AssessmentResult.student_id == student_id)
        .order_by(AssessmentResult.created_at.desc())
        .first()
    )
    if not latest:
        return "not_required"
    return (latest.guardian_consent or {}).get("status", "not_required")


def _student_summary(db: Session, student: Student) -> dict:
    """学生个人信息汇总（契约 §3 返回结构）。"""
    class_name = None
    if student.class_id:
        c = db.query(Class).filter(Class.id == student.class_id).first()
        class_name = c.name if c else None

    sp = (
        db.query(StudentPortfolio)
        .filter(StudentPortfolio.student_id == student.id)
        .first()
    )
    profile = dict(sp.dimensions or {}) if sp else {}

    growth_count = (
        db.query(sa_func.count(StudentGrowthRecord.id))
        .filter(StudentGrowthRecord.student_id == student.id)
        .scalar()
        or 0
    )
    archive_count = (
        db.query(sa_func.count(EvaluationArchive.id))
        .filter(EvaluationArchive.student_id == student.id)
        .scalar()
        or 0
    )
    scores_count = (
        db.query(sa_func.count(ExamScore.id))
        .filter(ExamScore.student_id == student.id)
        .scalar()
        or 0
    )

    return {
        "student": {
            "id": student.id,
            "name": student.name,
            "class_name": class_name,
        },
        "profile": profile,
        "growth_count": int(growth_count),
        "archive_count": int(archive_count),
        "scores_count": int(scores_count),
        "consent_status": _consent_status(db, student.id),
    }


def _log(
    db: Session,
    user_id: str,
    action: str,
    target_type: str,
    target_id: str,
    detail: Optional[dict] = None,
) -> None:
    """带角色推导的留痕助手（写失败不阻断，由 log_access 内部兜底）。"""
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


# ── 行权 1：学生个人信息汇总 ─────────────────────────────

@router.get("/data")
def rights_data(
    student_id: str = Query(..., description="学生 ID"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    student = _get_student(db, student_id)
    _require_rights_perm(db, user_id, student)
    summary = _student_summary(db, student)
    _log(db, user_id, "export", "student", student.id, {"action": "rights_data"})
    return {"code": 0, "message": "success", "data": summary}


# ── 行权 2：CSV 导出（档案/成长记录/画像关键字段）─────────

def _csv_rows(db: Session, student: Student, include_pii: bool = True) -> list[list[str]]:
    """学生个人信息 CSV 行。

    include_pii=False（副班主任/协作教师）时对 PII 字段掩码：
    学号 → mask_student_number、生日 → 置空、联系电话/家长电话 → mask_phone、
    家长姓名 → mask_name、家庭住址 → mask_address；姓名/性别/状态保持原样。
    """
    rows: list[list[str]] = []
    rows.append(["学生信息", "字段", "值"])
    if include_pii:
        student_number = student.student_number
        birthday = student.birthday
        phone = student.phone
        parent_name = student.parent_name
        parent_phone = student.parent_phone
        address = student.address
    else:
        student_number = mask_student_number(student.student_number) if student.student_number is not None else ""
        birthday = None
        phone = mask_phone(student.phone) if student.phone is not None else None
        parent_name = mask_name(student.parent_name) if student.parent_name is not None else None
        parent_phone = mask_phone(student.parent_phone) if student.parent_phone is not None else None
        address = mask_address(student.address) if student.address is not None else None
    info_fields = [
        ("姓名", student.name),
        ("学号", student_number),
        ("性别", student.gender),
        ("生日", birthday),
        ("联系电话", phone),
        ("家长姓名", parent_name),
        ("家长电话", parent_phone),
        ("家庭住址", address),
        ("状态", student.status),
    ]
    for label, val in info_fields:
        rows.append(["学生信息", label, "" if val is None else str(val)])

    sp = (
        db.query(StudentPortfolio)
        .filter(StudentPortfolio.student_id == student.id)
        .first()
    )
    rows.append(["画像", "维度", "分值"])
    dims = dict(sp.dimensions or {}) if sp else {}
    for dim, val in sorted(dims.items()):
        rows.append(["画像", dim, str(val)])
    if sp:
        rows.append(["画像", "总成长分", str(sp.total_growth_point)])

    growth_rows = (
        db.query(StudentGrowthRecord)
        .filter(StudentGrowthRecord.student_id == student.id)
        .order_by(StudentGrowthRecord.occurred_at.desc())
        .limit(200)
        .all()
    )
    rows.append(["成长记录", "维度/分值/时间/说明", ""])
    for g in growth_rows:
        rows.append([
            "成长记录",
            f"{g.dimension}/{g.growth_points}/{_iso(g.occurred_at) or ''}/{g.note or ''}",
            "",
        ])

    archive_rows = (
        db.query(EvaluationArchive)
        .filter(EvaluationArchive.student_id == student.id)
        .order_by(EvaluationArchive.created_at.desc())
        .all()
    )
    rows.append(["综评档案", "学期/状态/成档时间", ""])
    for a in archive_rows:
        rows.append([
            "综评档案",
            f"{a.term}/{a.status}/{_iso(a.archived_at) or ''}",
            "",
        ])

    result_rows = (
        db.query(AssessmentResult)
        .filter(AssessmentResult.student_id == student.id)
        .order_by(AssessmentResult.created_at.desc())
        .all()
    )
    rows.append(["测评结果", "域/同意状态/时间", ""])
    for r in result_rows:
        st = (r.guardian_consent or {}).get("status", "not_required")
        rows.append([
            "测评结果",
            f"{r.domain}/{st}/{_iso(r.created_at) or ''}",
            "",
        ])
    return rows


@router.get("/data/export")
def rights_export(
    student_id: str = Query(..., description="学生 ID"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    student = _get_student(db, student_id)
    _require_rights_perm(db, user_id, student)
    _log(db, user_id, "export", "student", student.id, {"action": "rights_export"})

    include_pii = can_view_student_pii(db, user_id, student.class_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["叙阅 · 学生个人信息导出", "导出时间", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")])
    writer.writerow([])
    for r in _csv_rows(db, student, include_pii=include_pii):
        writer.writerow(r)

    filename = f"学生个人信息_{student.name}_{datetime.now().strftime('%Y%m%d')}.csv"
    quoted = quote(filename)
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


# ── 行权 3：更正（仅联系方式类可更正字段）────────────────

@router.put("/data/correct")
def rights_correct(
    body: CorrectRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    student = _get_student(db, body.student_id)
    _require_rights_perm(db, user_id, student)
    field = body.field
    if field not in CORRECTABLE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"仅允许更正可更正字段（联系方式类）：{', '.join(sorted(CORRECTABLE_FIELDS))}",
        )
    setattr(student, field, body.value if body.value is not None else "")
    db.commit()
    _log(db, user_id, "correct", "student", student.id, {"field": field, "student_id": student.id})
    summary = _student_summary(db, student)
    return {"code": 0, "message": f"已更正字段 {field}", "data": summary}


# ── 行权 4：删除/匿名化（二次校验 confirm=true）───────────

@router.delete("/data")
def rights_delete(
    student_id: str = Query(...),
    confirm: bool = Query(False, description="对不可逆操作必须 confirm=true"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    student = _get_student(db, student_id)
    _require_rights_perm(db, user_id, student)
    if not confirm:
        raise HTTPException(status_code=400, detail="删除/匿名化不可逆，需二次确认 confirm=true")

    applied = []
    for field, value in ANONYMIZE_FIELDS.items():
        if getattr(student, field, None) not in (None, ""):
            applied.append(field)
        setattr(student, field, value)
    student.status = "deleted"
    db.commit()
    _log(
        db,
        user_id,
        "delete",
        "student",
        student.id,
        {"student_id": student.id, "anonymized_fields": applied, "mode": "anonymize"},
    )
    summary = _student_summary(db, student)
    summary["anonymized"] = True
    summary["anonymized_fields"] = applied
    return {"code": 0, "message": "已匿名化处理（学生记录保留，敏感字段置空并标记 deleted）", "data": summary}
