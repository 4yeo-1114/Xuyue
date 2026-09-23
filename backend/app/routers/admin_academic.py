"""学情板块 4 接口：成绩学情对比 / 学情趋势 / 班级排名 / 知识掌握度。

面向校长驾驶舱学情板块，支持 grade / class_id 过滤（class_id 优先），
聚合口径与全站一致：优秀线 85、及格线 60，student → class → grade 关联。

范围过滤与权限校验复用 admin_dashboard.py 的实现，避免口径漂移：
  - _scope_class_ids(db, grade, class_id, user)   年级/班级 → 班级 id 集合
  - _check_admin_permission(db, admin_id)         管理员鉴权
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.class_model import Class
from app.models.exam import Exam
from app.models.exam_score import ExamScore
from app.models.knowledge_point import KnowledgePoint
from app.models.student import Student
from app.routers.admin import _check_admin_permission
from app.routers.admin_dashboard import _scope_class_ids
from app.schemas.common import ApiResponse
from app.services.grade_scores import (
    GRADE_EXCELLENT,
    GRADE_GOOD,
    GRADE_NEEDS_WORK,
    GRADE_PASS,
)

router = APIRouter(prefix="/admin/academic", tags=["admin_academic"])

# 等级线（与 app/services/grade_scores.grade_for_score 契约一致，勿改）
EXCELLENT_LINE = 85  # 优秀
GOOD_LINE = 70       # 良好
PASS_LINE = 60       # 及格


def _fmt(value) -> float:
    """保留 1 位小数；None → 0.0。"""
    if value is None:
        return 0.0
    return round(float(value), 1)


def _pass_expr():
    return case((ExamScore.score >= PASS_LINE, 1), else_=0)


def _excellent_expr():
    return case((ExamScore.score >= EXCELLENT_LINE, 1), else_=0)


def _rate(cnt, total) -> float:
    return _fmt(cnt / total * 100 if total else 0.0)


def _scope_label(db: Session, grade, class_id) -> str:
    """当前过滤范围的展示名：班级名 > 年级名 > 全校。"""
    if class_id:
        cls = db.query(Class.name).filter(Class.id == class_id).first()
        return cls[0] if cls and cls[0] else class_id
    if grade:
        return grade
    return "全校"


def _score_agg(db: Session, class_ids, group_cols):
    """成绩聚合：student → class 关联，可选按 group_cols 分组。

    返回行结构：group_cols... + (score_count, student_count, avg_score, pass_cnt, excellent_cnt)。
    仅统计有 score 的记录（score 为 NULL 不计入）。
    """
    q = (
        db.query(
            *group_cols,
            func.count(ExamScore.id).label("score_count"),
            func.count(func.distinct(Student.id)).label("student_count"),
            func.avg(ExamScore.score).label("avg_score"),
            func.sum(_pass_expr()).label("pass_cnt"),
            func.sum(_excellent_expr()).label("excellent_cnt"),
        )
        .join(Student, Student.id == ExamScore.student_id)
        .join(Class, Class.id == Student.class_id)
        .filter(ExamScore.score.isnot(None))
    )
    if class_ids is not None:
        q = q.filter(Student.class_id.in_(class_ids))
    if group_cols:
        q = q.group_by(*group_cols)
    return q.all()


def _stat_row(row):
    """从聚合行提取指标 dict（分组列之外的列）。"""
    score_count = int(row[-5] or 0)
    return {
        "avg_score": _fmt(row[-3]),
        "pass_rate": _rate(row[-2], score_count),
        "excellent_rate": _rate(row[-1], score_count),
        "score_count": score_count,
        "student_count": int(row[-4] or 0),
    }


@router.get("/overview", response_model=ApiResponse[dict])
def academic_overview(
    grade: Optional[str] = Query(None, description="年级，如：小学一年级"),
    class_id: Optional[str] = Query(None, description="班级 ID，优先于 grade"),
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_user_id),
):
    """成绩学情对比：当前范围 summary + 分组 items（全校→按年级 / 选年级→各班 / 选班级→1 条）。"""
    user = _check_admin_permission(db, admin_id)
    class_ids = _scope_class_ids(db, grade, class_id, user=user)

    # summary = 当前过滤范围整体聚合
    rows = _score_agg(db, class_ids, [])
    summary = _stat_row(rows[0]) if rows else {
        "avg_score": 0.0, "pass_rate": 0.0, "excellent_rate": 0.0,
        "score_count": 0, "student_count": 0,
    }

    # 分组粒度按查询参数决定（class_id 优先于 grade，均无 → 按年级），
    # 与是否带 school scope 无关：school scope 只收敛数据集合，不改分组层级。
    if class_id:
        # 选班级 → 该班 1 条
        rows = _score_agg(db, class_ids, [Class.id, Class.name])
        items = [{"key": r[0], "label": r[1] or r[0], **_stat_row(r)}
                 for r in sorted(rows, key=lambda r: str(r[1] or ""))]
    elif grade:
        # 选年级 → 该年级各班
        rows = _score_agg(db, class_ids, [Class.id, Class.name])
        items = [{"key": r[0], "label": r[1] or r[0], **_stat_row(r)}
                 for r in sorted(rows, key=lambda r: str(r[1] or ""))]
    else:
        # 全校 → 按年级分组
        rows = _score_agg(db, class_ids, [Class.grade])
        items = [{"key": r[0], "label": r[0], **_stat_row(r)}
                 for r in sorted(rows, key=lambda r: str(r[0] or ""))]

    return ApiResponse(data={
        "scope": {"grade": grade, "class_id": class_id, "label": _scope_label(db, grade, class_id)},
        "summary": summary,
        "items": items,
    })


@router.get("/trend", response_model=ApiResponse[dict])
def academic_trend(
    grade: Optional[str] = Query(None, description="年级过滤"),
    class_id: Optional[str] = Query(None, description="班级过滤"),
    limit: int = Query(12, ge=1, le=60, description="最近 N 个月"),
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_user_id),
):
    """学情趋势：按 exam_date 所在月份聚合，最近 limit 个月，升序。"""
    user = _check_admin_permission(db, admin_id)
    class_ids = _scope_class_ids(db, grade, class_id, user=user)

    # 双引擎兼容（P3 业务库迁移 F1b）：MySQL 用 date_format，PG 用 to_char
    if settings.db_engine == "postgresql":
        period_expr = func.to_char(Exam.exam_date, "YYYY-MM")
    else:
        period_expr = func.date_format(Exam.exam_date, "%Y-%m")
    q = (
        db.query(
            period_expr.label("period"),
            func.count(ExamScore.id),
            func.avg(ExamScore.score),
            func.sum(_pass_expr()),
            func.sum(_excellent_expr()),
        )
        .join(Exam, Exam.id == ExamScore.exam_id)
        .join(Student, Student.id == ExamScore.student_id)
        .filter(ExamScore.score.isnot(None))
    )
    if class_ids is not None:
        q = q.filter(Student.class_id.in_(class_ids))
    q = q.group_by(period_expr).order_by(period_expr)

    points = []
    for period, score_count, avg, pass_cnt, excellent_cnt in q.all():
        score_count = int(score_count or 0)
        points.append({
            "period": period,
            "label": period,
            "avg_score": _fmt(avg),
            "pass_rate": _rate(pass_cnt, score_count),
            "excellent_rate": _rate(excellent_cnt, score_count),
            "score_count": score_count,
        })

    return ApiResponse(data={"points": points[-limit:]})


@router.get("/class-ranking", response_model=ApiResponse[dict])
def academic_class_ranking(
    grade: Optional[str] = Query(None, description="年级过滤；空 = 全校"),
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_user_id),
):
    """班级排名：范围（全校/年级）内按 avg_score 降序，仅统计有成绩的班级。"""
    user = _check_admin_permission(db, admin_id)
    class_ids = _scope_class_ids(db, grade, None, user=user)

    q = (
        db.query(
            Class.id,
            Class.name,
            Class.grade,
            func.count(ExamScore.id),
            func.count(func.distinct(Student.id)),
            func.avg(ExamScore.score),
            func.sum(_pass_expr()),
            func.sum(_excellent_expr()),
        )
        .join(Student, Student.class_id == Class.id)
        .join(ExamScore, ExamScore.student_id == Student.id)
        .filter(ExamScore.score.isnot(None))
    )
    if class_ids is not None:
        q = q.filter(Class.id.in_(class_ids))
    q = q.group_by(Class.id, Class.name, Class.grade)

    ranked = sorted(q.all(), key=lambda r: (float(r[5] or 0.0), float(r[4] or 0.0)), reverse=True)
    classes = []
    for rank, (cid, cname, cgrade, score_count, student_count, avg, pass_cnt, exc_cnt) in enumerate(ranked, start=1):
        score_count = int(score_count or 0)
        classes.append({
            "rank": rank,
            "class_id": cid,
            "class_name": cname,
            "grade": cgrade,
            "avg_score": _fmt(avg),
            "pass_rate": _rate(pass_cnt, score_count),
            "excellent_rate": _rate(exc_cnt, score_count),
            "student_count": int(student_count or 0),
        })

    return ApiResponse(data={
        "scope": {"grade": grade, "label": grade or "全校"},
        "classes": classes,
    })


@router.get("/mastery", response_model=ApiResponse[dict])
def academic_mastery(
    grade: Optional[str] = Query(None, description="年级过滤"),
    class_id: Optional[str] = Query(None, description="班级过滤"),
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_user_id),
):
    """知识掌握度：成绩等级分布（按 score 实时派生）+ 知识点掌握度（knowledge_points）。

    score 为 NULL 的成绩忽略；knowledge_points 表空时 mastery_available=false 且 mastery 为空数组。
    """
    user = _check_admin_permission(db, admin_id)
    class_ids = _scope_class_ids(db, grade, class_id, user=user)

    # 等级分布：按年级 + 实时 score 派生等级统计。
    # exam_scores.grade 种子数据未落库（全 NULL），不依赖该列；
    # 等级口径与 app/services/grade_scores.grade_for_score 一致，score 为 NULL 不计入。
    grade_expr = case(
        (ExamScore.score >= EXCELLENT_LINE, GRADE_EXCELLENT),
        (ExamScore.score >= GOOD_LINE, GRADE_GOOD),
        (ExamScore.score >= PASS_LINE, GRADE_PASS),
        else_=GRADE_NEEDS_WORK,
    )
    gq = (
        db.query(Class.grade, grade_expr, func.count(ExamScore.id))
        .join(Student, Student.id == ExamScore.student_id)
        .join(Class, Class.id == Student.class_id)
        .filter(ExamScore.score.isnot(None))
    )
    if class_ids is not None:
        gq = gq.filter(Student.class_id.in_(class_ids))
    gq = gq.group_by(Class.grade, grade_expr).all()

    dist_map: dict[str, dict] = {}
    for grade_name, level, cnt in gq:
        d = dist_map.setdefault(grade_name, {
            "grade": grade_name, "label": grade_name,
            "excellent": 0, "good": 0, "pass": 0, "needs_work": 0, "total": 0,
        })
        key = level if level in {GRADE_EXCELLENT, GRADE_GOOD, GRADE_PASS, GRADE_NEEDS_WORK} else GRADE_NEEDS_WORK
        d[key] = int(cnt or 0)
        d["total"] += int(cnt or 0)
    grade_distribution = [dist_map[k] for k in sorted(dist_map)]

    # 掌握度：knowledge_points.user_id → students → classes.grade
    mq = (
        db.query(
            Class.grade,
            func.avg(KnowledgePoint.mastery),
            func.sum(case((KnowledgePoint.is_weak.is_(True), 1), else_=0)),
        )
        .join(Student, Student.user_id == KnowledgePoint.user_id)
        .join(Class, Class.id == Student.class_id)
    )
    if class_ids is not None:
        mq = mq.filter(Student.class_id.in_(class_ids))
    mq = mq.group_by(Class.grade).all()

    mastery = [
        {"grade": g, "label": g,
         "avg_mastery": _fmt(avg), "weak_points": int(weak or 0)}
        for g, avg, weak in mq
    ]

    return ApiResponse(data={
        "mastery_available": bool(mastery),
        "grade_distribution": grade_distribution,
        "mastery": mastery,
    })
