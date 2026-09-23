"""综评档案·遴选→公示→成档 路由（种春风 A 域，挂载前缀 /api/v1/portfolio）。

补齐合同「综评档案：写实记录→遴选→公示→成档」中的遴选与公示环节。
状态流：draft(待遴选) → selected(已遴选) → publicity(公示中) → archived(已存档)。
公示中可撤回(→draft)，公示期默认 7 天。
权限：本班教师/班主任/管理员可操作班级；全局管理员可跨班（can_view_class / get_class_role 已覆盖）。
"""
from __future__ import annotations

import datetime
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.evaluation_archive import EvaluationArchive
from app.models.student import Student
from app.schemas.common import ApiResponse
from app.utils.class_access import can_view_class, get_class_role
from app.services.audit.access_log import log_access, resolve_user_role

router = APIRouter(prefix="/portfolio", tags=["portfolio-archive"])

TERM_PATTERN = re.compile(r"^\d{4}-\d{4}-[12]$")
PUBLICITY_DAYS = 7
STATUSES = {"draft", "selected", "publicity", "archived"}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(v) -> Optional[str]:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _validate_term(term: str) -> None:
    if not term or not TERM_PATTERN.match(term):
        raise HTTPException(status_code=422, detail="term 格式应为 学年-学年-学期，如 2025-2026-1")


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


def _require_class_write(db: Session, user_id: str, class_id: str) -> None:
    """写操作权限：本班教师及以上（head/deputy/teacher/管理员）。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    if get_class_role(db, user_id, class_id) is None:
        raise HTTPException(status_code=403, detail="无权限操作该班级")


def _get_archive_or_404(db: Session, archive_id: str) -> EvaluationArchive:
    row = db.query(EvaluationArchive).filter(EvaluationArchive.id == archive_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="档案记录不存在")
    return row


def _ensure_archive_write(db: Session, user_id: str, row: EvaluationArchive) -> None:
    _require_class_write(db, user_id, row.class_id)


def _archive_dict(row: EvaluationArchive, student: Optional[Student] = None) -> dict:
    return {
        "id": row.id,
        "class_id": row.class_id,
        "student_id": row.student_id,
        "student_name": student.name if student else None,
        "student_number": student.student_number if student else None,
        "term": row.term,
        "status": row.status,
        "selected_at": _iso(row.selected_at),
        "publicity_at": _iso(row.publicity_at),
        "publicity_end_at": _iso(row.publicity_end_at),
        "archived_at": _iso(row.archived_at),
        "operator_id": row.operator_id,
        "created_at": _iso(row.created_at),
        "publicity_expired": bool(
            row.status == "publicity"
            and row.publicity_end_at is not None
            and row.publicity_end_at < _now()
        ),
    }


class ArchiveSelectRequest(BaseModel):
    """遴选：把候选学生标记为「已遴选」进入公示前阶段。"""

    student_ids: List[str] = Field(..., min_length=1, description="本班学生 ID 列表")
    term: str = Field(..., description="学年-学期，如 2025-2026-1")


# ── 遴选 ───────────────────────────────────────────────

@router.post("/classes/{class_id}/archive/select")
def select_archive(
    class_id: str,
    body: ArchiveSelectRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[list]:
    _require_class_write(db, user_id, class_id)
    _validate_term(body.term)

    student_ids = [str(s) for s in (body.student_ids or [])]
    # 校验学生归属本班
    students = (
        db.query(Student)
        .filter(Student.id.in_(student_ids), Student.class_id == class_id)
        .all()
    )
    found = {str(s.id) for s in students}
    missing = [sid for sid in student_ids if sid not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"以下学生不属于该班级：{', '.join(missing[:5])}")

    now = _now()
    rows: List[EvaluationArchive] = []
    for sid in student_ids:
        row = (
            db.query(EvaluationArchive)
            .filter(
                EvaluationArchive.class_id == class_id,
                EvaluationArchive.student_id == sid,
                EvaluationArchive.term == body.term,
            )
            .first()
        )
        if row is None:
            row = EvaluationArchive(
                class_id=class_id,
                student_id=sid,
                term=body.term,
                status="selected",
                selected_at=now,
                operator_id=user_id,
            )
            db.add(row)
        else:
            # 已存档的不可再遴选；公示中需先撤回
            if row.status == "archived":
                continue
            if row.status == "publicity":
                continue
            row.status = "selected"
            row.selected_at = row.selected_at or now
            row.operator_id = user_id
        rows.append(row)

    db.commit()
    for r in rows:
        db.refresh(r)
    students_by_id = {str(s.id): s for s in students}
    data = [_archive_dict(r, students_by_id.get(r.student_id)) for r in rows]
    return ApiResponse(message=f"已遴选 {len(rows)} 名学生", data=data)


# ── 公示 ───────────────────────────────────────────────

@router.post("/archive/{archive_id}/publicity")
def start_publicity(
    archive_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    row = _get_archive_or_404(db, archive_id)
    _ensure_archive_write(db, user_id, row)
    if row.status not in ("draft", "selected"):
        raise HTTPException(status_code=400, detail="当前状态不可开启公示（仅 draft/selected 可开启）")
    now = _now()
    row.status = "publicity"
    row.publicity_at = now
    row.publicity_end_at = now + datetime.timedelta(days=PUBLICITY_DAYS)
    row.operator_id = user_id
    db.commit()
    db.refresh(row)
    student = db.query(Student).filter(Student.id == row.student_id).first()
    return ApiResponse(message="公示已开启", data=_archive_dict(row, student))


@router.post("/archive/{archive_id}/withdraw")
def withdraw_publicity(
    archive_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    row = _get_archive_or_404(db, archive_id)
    _ensure_archive_write(db, user_id, row)
    if row.status != "publicity":
        raise HTTPException(status_code=400, detail="仅公示中状态可撤回")
    row.status = "draft"
    row.publicity_at = None
    row.publicity_end_at = None
    row.operator_id = user_id
    db.commit()
    db.refresh(row)
    student = db.query(Student).filter(Student.id == row.student_id).first()
    return ApiResponse(message="公示已撤回", data=_archive_dict(row, student))


@router.post("/archive/{archive_id}/archive")
def archive_evaluation(
    archive_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[dict]:
    row = _get_archive_or_404(db, archive_id)
    _ensure_archive_write(db, user_id, row)
    if row.status != "publicity":
        raise HTTPException(status_code=400, detail="仅公示中状态可成档")
    now = _now()
    row.status = "archived"
    row.archived_at = now
    row.operator_id = user_id
    db.commit()
    db.refresh(row)
    student = db.query(Student).filter(Student.id == row.student_id).first()
    return ApiResponse(message="已成档归档", data=_archive_dict(row, student))


# ── 档案列表 ───────────────────────────────────────────

@router.get("/archive")
def list_archive(
    class_id: Optional[str] = Query(None, description="按班级过滤（本班教师必传；全局管理员可空）"),
    term: Optional[str] = Query(None, description="按学期过滤，如 2025-2026-1"),
    status: Optional[str] = Query(None, description="按状态过滤：draft/selected/publicity/archived"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ApiResponse[list]:
    q = db.query(EvaluationArchive)

    if class_id:
        if not can_view_class(db, user_id, class_id):
            raise HTTPException(status_code=404, detail="班级不存在")
        q = q.filter(EvaluationArchive.class_id == class_id)
    else:
        # 未传班级：仅全局管理员可跨班查看
        if not _is_global_admin(db, user_id):
            raise HTTPException(status_code=403, detail="未指定班级，仅全局管理员可跨班查看档案")

    if term:
        _validate_term(term)
        q = q.filter(EvaluationArchive.term == term)
    if status:
        if status not in STATUSES:
            raise HTTPException(status_code=422, detail="status 必须在 draft/selected/publicity/archived 中")
        q = q.filter(EvaluationArchive.status == status)

    rows = q.order_by(EvaluationArchive.created_at.desc()).all()
    _log_access(
        db,
        user_id,
        "view_archive",
        "class",
        class_id or "",
        {"term": term, "status": status, "cross_class": not bool(class_id)},
    )
    if not rows:
        return ApiResponse(data=[])

    student_ids = [r.student_id for r in rows]
    students = (
        db.query(Student)
        .filter(Student.id.in_(student_ids))
        .all()
    )
    students_by_id = {str(s.id): s for s in students}
    data = [_archive_dict(r, students_by_id.get(r.student_id)) for r in rows]
    return ApiResponse(data=data)


def _is_global_admin(db: Session, user_id: str) -> bool:
    """全局管理员（可跨班）判定，复用 class_access 的实现口径。"""
    from app.utils.class_access import _is_global_admin as _check
    return _check(db, user_id)
