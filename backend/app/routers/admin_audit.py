"""合规后台 · 年度审计（E14）。

前缀 /admin/audit，挂载后为 /api/v1/admin/audit/...
  - GET /admin/audit/access-logs?student_id=&action=&from=&to=&page=&page_size=
      访问留痕分页查询
  - GET /admin/audit/report?year=&school_id=
      年度审计报告：访问量 / action 分布 / 高频访问学生 / 同意分布 / 导出与删除次数

权限：仅管理员（super_admin / org_admin / school_admin，复用 access_svc.is_admin）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func as sa_func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.access_log import AccessLog
from app.models.assessment_result import AssessmentResult
from app.models.student import Student
from app.services.assessment import access as access_svc

router = APIRouter(prefix="/admin/audit", tags=["admin_audit"])

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100


def _require_admin(db: Session, user_id: str) -> None:
    if not access_svc.is_admin(db, user_id):
        raise HTTPException(status_code=403, detail="仅管理员可访问审计接口")


def _iso(v) -> Optional[str]:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _parse_dt(s: Optional[str], field: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} 格式应为 YYYY-MM-DD")


@router.get("/access-logs")
def list_access_logs(
    student_id: Optional[str] = Query(None, description="按学生 ID 过滤（target_id）"),
    action: Optional[str] = Query(None, description="按动作过滤，如 view_report/export"),
    from_: Optional[str] = Query(None, alias="from", description="起始日期 YYYY-MM-DD"),
    to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _require_admin(db, user_id)
    q = db.query(AccessLog)
    if student_id:
        q = q.filter(AccessLog.target_id == student_id)
    if action:
        q = q.filter(AccessLog.action == action)
    from_dt = _parse_dt(from_, "from")
    to_dt = _parse_dt(to, "to")
    if from_dt:
        q = q.filter(AccessLog.created_at >= from_dt)
    if to_dt:
        # 含当日
        to_end = datetime(to_dt.year, to_dt.month, to_dt.day, 23, 59, 59)
        q = q.filter(AccessLog.created_at <= to_end)

    total = q.count()
    rows = (
        q.order_by(desc(AccessLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "list": [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "user_role": r.user_role,
                    "action": r.action,
                    "target_type": r.target_type,
                    "target_id": r.target_id,
                    "detail": r.detail,
                    "created_at": _iso(r.created_at),
                }
                for r in rows
            ],
            "total": int(total),
        },
    }


def _latest_consent_stats(db: Session) -> dict:
    """同意分布：每位学生取最新一条 assessment_result 的 guardian_consent.status（当前状态快照）。"""
    stats = {"granted": 0, "withdrawn": 0, "not_required": 0}
    rows = (
        db.query(AssessmentResult.student_id, AssessmentResult.guardian_consent)
        .order_by(AssessmentResult.created_at.desc())
        .all()
    )
    seen = set()
    for sid, consent in rows:
        if sid in seen:
            continue
        seen.add(sid)
        st = (consent or {}).get("status", "not_required")
        if st in stats:
            stats[st] += 1
        else:
            stats["not_required"] += 1
    return stats


@router.get("/report")
def audit_report(
    year: Optional[int] = Query(None, ge=2000, le=2100, description="审计年度，如 2026"),
    school_id: Optional[str] = Query(None, description="学校 ID（预留，当前全校口径）"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _require_admin(db, user_id)
    del school_id  # 预留：目前全校口径，school_id 透传返回

    q = db.query(AccessLog)
    if year:
        start = datetime(year, 1, 1)
        end = datetime(year, 12, 31, 23, 59, 59)
        q = q.filter(AccessLog.created_at >= start, AccessLog.created_at <= end)

    total_access = q.count()

    action_rows = (
        q.with_entities(AccessLog.action, sa_func.count(AccessLog.id))
        .group_by(AccessLog.action)
        .all()
    )
    action_stats = {a: int(c) for a, c in action_rows}

    top_q = q.filter(AccessLog.target_type == "student")
    top_rows = (
        top_q.with_entities(AccessLog.target_id, sa_func.count(AccessLog.id).label("cnt"))
        .group_by(AccessLog.target_id)
        .order_by(desc("cnt"))
        .limit(10)
        .all()
    )
    target_ids = [tid for tid, _ in top_rows]
    name_map = {}
    if target_ids:
        students = db.query(Student.id, Student.name).filter(Student.id.in_(target_ids)).all()
        name_map = {str(sid): sname for sid, sname in students}
    top_accessed = [
        {
            "student_id": tid,
            "target_name": name_map.get(tid),
            "count": int(cnt),
        }
        for tid, cnt in top_rows
    ]

    export_count = q.filter(AccessLog.action == "export").count()
    delete_count = q.filter(AccessLog.action == "delete").count()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "year": year,
            "total_access": int(total_access),
            "action_stats": action_stats,
            "top_accessed": top_accessed,
            "consent_stats": _latest_consent_stats(db),
            "export_count": int(export_count),
            "delete_count": int(delete_count),
        },
    }
