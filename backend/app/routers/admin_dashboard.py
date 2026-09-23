"""学校数据驾驶舱 · 全校级学情监控（合同七模块·数据看板）。

仅管理员可访问。提供全校 KPI 总览（支持 grade / class_id 过滤）与
日 / 周 / 月三种粒度的批改量·预警数·兑换量时间序列。

聚合口径：
  - class_count       班级数（按过滤范围）
  - student_count     学生数（按过滤范围）
  - grading_count     近 30 天批改量（grading_daily_stats.grade_count 汇总）
  - alert_count       健康预警数（health_checks.is_alert=1）
  - redemption_count  兑换量（redemption_records 记录数）
  - growth_score_available  五育均分是否可用（portfolio 表当前范围有行）
  - growth_score_avg  五育均分（student_portfolios.total_growth_point 均值；无数据时 None）

批改量按班级维度聚合：grading_daily_stats.folder_safe 形如
`cls_{class_id}__{考试名}`，可据 class_id 前缀归属到班级 / 年级。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.class_model import Class
from app.models.exam import Exam
from app.models.grading_daily_stat import GradingDailyStat
from app.models.health_check import HealthCheck
from app.models.redemption_record import RedemptionRecord
from app.models.student import Student
from app.models.student_portfolio import StudentPortfolio
from app.models.user import User
from app.routers.admin import _check_admin_permission
from app.schemas.common import ApiResponse
from app.utils.school_access import (
    get_school_user_ids,
    get_user_school_id,
    school_scope_class_ids,
)

router = APIRouter(prefix="/admin", tags=["admin_dashboard"])

GRADING_DAYS_DEFAULT = 30


def _scope_class_ids(
    db: Session,
    grade: Optional[str],
    class_id: Optional[str],
    user=None,
):
    """解析过滤范围 → 班级 id 集合；未过滤返回 None（全校）。

    class_id 优先于 grade；两者均空 → None。user 带 school_id 时按学校收敛
    （school_id 空则行为与现状一致，全量放行）。
    """
    q = db.query(Class.id)
    if class_id:
        q = q.filter(Class.id == class_id)
    elif grade:
        q = q.filter(Class.grade == grade)
    ids = {str(r[0]) for r in q.all()}
    ids = ids if (class_id or grade) else None
    if user is not None:
        ids = school_scope_class_ids(db, user, ids)
    return ids


def _folder_in_scope(folder_safe: str, class_ids) -> bool:
    """grading_daily_stats.folder_safe 是否归属于过滤班级集合。

    class_ids 为 None（全校）时全部命中；空集合返回 False。
    """
    if class_ids is None:
        return True
    if not class_ids:
        return False
    safe = str(folder_safe or "")
    if safe.startswith("cls_") and "__" in safe:
        cid = safe.split("__", 1)[0][4:]
        return cid in class_ids
    return False


def _grade_grading_series(db: Session, start: date, end: date) -> list:
    """近 period 的批改聚合行（stat_date / folder_safe / grade_count），供 Python 端分桶。"""
    rows = (
        db.query(GradingDailyStat.stat_date, GradingDailyStat.folder_safe,
                 GradingDailyStat.grade_count)
        .filter(GradingDailyStat.stat_date >= start,
                GradingDailyStat.stat_date <= end)
        .all()
    )
    return [{"stat_date": r.stat_date, "folder_safe": r.folder_safe,
             "grade_count": int(r.grade_count or 0)} for r in rows]


@router.get("/dashboard/overview", response_model=ApiResponse[dict])
def dashboard_overview(
    grade: Optional[str] = Query(None, description="年级，如：小学三年级"),
    class_id: Optional[str] = Query(None, description="班级 ID"),
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_user_id),
):
    """全校 / 年级 / 班级 KPI 总览。"""
    user = _check_admin_permission(db, admin_id)

    class_ids = _scope_class_ids(db, grade, class_id, user=user)

    cq = db.query(Class)
    if class_ids is not None:
        cq = cq.filter(Class.id.in_(class_ids))
    class_count = cq.count()

    sq = db.query(func.count(Student.id))
    if class_ids is not None:
        sq = sq.filter(Student.class_id.in_(class_ids))
    student_count = sq.scalar() or 0

    # D9：school scope——调用者有 school_id 时只统计本校用户（空则全量，兼容现状）
    uq = db.query(func.count(User.id))
    school_id = get_user_school_id(db, user)
    if school_id:
        uq = uq.filter(User.id.in_(get_school_user_ids(db, school_id)))
    users_count = uq.scalar() or 0

    eq = db.query(func.count(Exam.id))
    if class_ids is not None:
        eq = eq.filter(Exam.class_id.in_(class_ids))
    exams_count = eq.scalar() or 0

    since = date.today() - timedelta(days=GRADING_DAYS_DEFAULT - 1)
    grading_count = sum(
        r["grade_count"]
        for r in _grade_grading_series(db, since, date.today())
        if _folder_in_scope(r["folder_safe"], class_ids)
    )

    aq = db.query(func.count(HealthCheck.id)).filter(HealthCheck.is_alert == 1)
    if class_ids is not None:
        aq = aq.filter(HealthCheck.class_id.in_(class_ids))
    alert_count = aq.scalar() or 0

    rq = db.query(func.count(RedemptionRecord.id))
    if class_ids is not None:
        rq = rq.filter(RedemptionRecord.class_id.in_(class_ids))
    redemption_count = rq.scalar() or 0

    pq = db.query(func.avg(StudentPortfolio.total_growth_point))
    if class_ids is not None:
        pq = pq.filter(StudentPortfolio.class_id.in_(class_ids))
    growth_value = pq.scalar()
    # 五育均分：portfolio 表当前范围无数据时 available=false 且 avg=None（前端显示占位，不显示 0.00）
    growth_score_available = growth_value is not None
    growth_score_avg = round(float(growth_value), 2) if growth_value is not None else None

    return ApiResponse(data={
        "grade": grade,
        "class_id": class_id,
        "class_count": int(class_count),
        "student_count": int(student_count),
        "users_count": int(users_count),
        "exams_count": int(exams_count),
        "grading_count": int(grading_count),
        "alert_count": int(alert_count),
        "redemption_count": int(redemption_count),
        "growth_score_available": growth_score_available,
        "growth_score_avg": growth_score_avg,
        "grading_days": GRADING_DAYS_DEFAULT,
    })


def _build_buckets(granularity: str, days: int) -> list[dict]:
    """按粒度生成时间桶骨架（period / label / start / end，闭区间）。"""
    today = date.today()
    buckets: list[dict] = []
    if granularity == "daily":
        n = max(1, days)
        for i in range(n - 1, -1, -1):
            d = today - timedelta(days=i)
            buckets.append({"period": d.isoformat(), "label": d.strftime("%m-%d"),
                            "start": d, "end": d})
        return buckets
    if granularity == "weekly":
        n = max(1, (days + 6) // 7)
        for i in range(n - 1, -1, -1):
            end = today - timedelta(days=7 * i)
            start = end - timedelta(days=6)
            buckets.append({"period": start.isoformat(),
                            "label": f"{start.strftime('%m-%d')}~{end.strftime('%m-%d')}",
                            "start": start, "end": end})
        return buckets
    # monthly
    n = max(1, (days + 29) // 30)
    base = today.year * 12 + (today.month - 1)
    for i in range(n - 1, -1, -1):
        total = base - i
        by, bm = divmod(total, 12)
        bm += 1
        bstart = date(by, bm, 1)
        if bm == 12:
            bend = date(by + 1, 1, 1) - timedelta(days=1)
        else:
            bend = date(by, bm + 1, 1) - timedelta(days=1)
        buckets.append({"period": f"{by:04d}-{bm:02d}", "label": f"{by}-{bm:02d}",
                        "start": bstart, "end": bend})
    return buckets


def _index_for(bucket_starts: list[date], bucket_ends: list[date], d: date) -> int:
    if d is None:
        return -1
    for i in range(len(bucket_starts)):
        if bucket_starts[i] <= d <= bucket_ends[i]:
            return i
    return -1


def _empty_series(buckets: list[dict]) -> list[dict]:
    return [{
        "period": b["period"],
        "label": b["label"],
        "grading_count": 0,
        "alert_count": 0,
        "redemption_count": 0,
    } for b in buckets]


def _build_trend(
    db: Session,
    granularity: str,
    days: int,
    grade: Optional[str],
    class_id: Optional[str],
    user=None,
) -> dict:
    class_ids = _scope_class_ids(db, grade, class_id, user=user)
    buckets = _build_buckets(granularity, days)
    series = _empty_series(buckets)
    starts = [b["start"] for b in buckets]
    ends = [b["end"] for b in buckets]

    if buckets:
        range_start, range_end = starts[0], ends[-1]

        for r in _grade_grading_series(db, range_start, range_end):
            if _folder_in_scope(r["folder_safe"], class_ids):
                idx = _index_for(starts, ends, r["stat_date"])
                if idx >= 0:
                    series[idx]["grading_count"] += r["grade_count"]

        aq = (db.query(HealthCheck.check_date, func.count(HealthCheck.id))
              .filter(HealthCheck.is_alert == 1,
                      HealthCheck.check_date >= range_start,
                      HealthCheck.check_date <= range_end))
        if class_ids is not None:
            aq = aq.filter(HealthCheck.class_id.in_(class_ids))
        for check_date, cnt in aq.group_by(HealthCheck.check_date).all():
            idx = _index_for(starts, ends, check_date)
            if idx >= 0:
                series[idx]["alert_count"] += int(cnt or 0)

        rq = (db.query(func.date(RedemptionRecord.created_at),
                       func.count(RedemptionRecord.id))
              .filter(RedemptionRecord.created_at >= range_start,
                      RedemptionRecord.created_at <= (range_end + timedelta(days=1))))
        if class_ids is not None:
            rq = rq.filter(RedemptionRecord.class_id.in_(class_ids))
        for created_dt, cnt in rq.group_by(func.date(RedemptionRecord.created_at)).all():
            d = created_dt.date() if hasattr(created_dt, "date") else created_dt
            idx = _index_for(starts, ends, d)
            if idx >= 0:
                series[idx]["redemption_count"] += int(cnt or 0)

    return {
        "granularity": granularity,
        "days": days,
        "start_date": starts[0].isoformat() if buckets else None,
        "end_date": ends[-1].isoformat() if buckets else None,
        "periods": series,
    }


@router.get("/dashboard/daily", response_model=ApiResponse[dict])
def dashboard_daily(
    days: int = Query(GRADING_DAYS_DEFAULT, ge=7, le=365, description="最近天数"),
    grade: Optional[str] = Query(None, description="年级过滤"),
    class_id: Optional[str] = Query(None, description="班级过滤"),
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_user_id),
):
    """日监测：按天聚合批改量 / 预警数 / 兑换量。"""
    user = _check_admin_permission(db, admin_id)
    return ApiResponse(data=_build_trend(db, "daily", days, grade, class_id, user=user))


@router.get("/dashboard/weekly", response_model=ApiResponse[dict])
def dashboard_weekly(
    days: int = Query(GRADING_DAYS_DEFAULT, ge=7, le=730, description="最近天数"),
    grade: Optional[str] = Query(None, description="年级过滤"),
    class_id: Optional[str] = Query(None, description="班级过滤"),
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_user_id),
):
    """周分析：按周聚合批改量 / 预警数 / 兑换量。"""
    user = _check_admin_permission(db, admin_id)
    return ApiResponse(data=_build_trend(db, "weekly", days, grade, class_id, user=user))


@router.get("/dashboard/monthly", response_model=ApiResponse[dict])
def dashboard_monthly(
    days: int = Query(GRADING_DAYS_DEFAULT, ge=30, le=730, description="最近天数"),
    grade: Optional[str] = Query(None, description="年级过滤"),
    class_id: Optional[str] = Query(None, description="班级过滤"),
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_user_id),
):
    """月评估：按月聚合批改量 / 预警数 / 兑换量。"""
    user = _check_admin_permission(db, admin_id)
    return ApiResponse(data=_build_trend(db, "monthly", days, grade, class_id, user=user))
