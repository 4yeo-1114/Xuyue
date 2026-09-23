"""学校级预警中心（D10 · 学校版「预警中心」数据接口）。

从班级学情报告（class_analysis_reports）推导教学质量预警，返回与前端局版
WarningAlert 兼容的结构（局版数据是前端 localStorage mock，学校版接真实后端）。

阈值规则（固定，每班每科）：
  - 平均分 < 60                        → red    (metric="平均分",  threshold=60)
  - 60 ≤ 平均分 < 70                   → yellow (metric="平均分",  threshold=70)
  - 及格率 < 70                        → yellow (metric="及格率",  threshold=70)
  - 优秀率 < 20                        → yellow (metric="优秀率",  threshold=20)
  - 均不命中 且 及格率 ≥ 85 且 平均分 ≥ 85 → green  (metric="综合表现", threshold=85)
每班每科最多输出前 2 条（red 优先于 yellow 优先于 green）；无数据该班科跳过。

复用而非复制：指标提炼一律走 class_analysis 的 _class_metrics / _score_num，
权限走 admin 的 _check_admin_permission（已含 is_school_admin）。
"""
import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.class_analysis import ClassAnalysisReport
from app.models.class_model import Class
from app.routers.admin import _check_admin_permission
from app.routers.class_analysis import _class_metrics, _score_num
from app.schemas.common import ApiResponse
from app.utils.school_access import get_user_school_id, school_scope_class_ids

router = APIRouter(prefix="/school", tags=["school_warnings"])

_LEVEL_RANK = {"red": 0, "yellow": 1, "green": 2}


def _school_name_map(db: Session, school_ids: set[str]) -> dict[str, str]:
    """schools 表批量查名；表不存在/查询失败返回空映射（schoolName 置 None，不 500）。"""
    if not school_ids:
        return {}
    try:
        from app.models.school import School

        rows = db.query(School.id, School.name).filter(School.id.in_(list(school_ids))).all()
        return {str(r[0]): str(r[1]) for r in rows if r[1]}
    except Exception:
        return {}


def _derive_candidates(metrics: dict) -> list[dict]:
    """按固定阈值推导某班某科预警候选（含 level/metric/threshold/value）。"""
    avg = metrics.get("average_score")
    pass_rate = float(metrics.get("pass_rate") or 0.0)
    excellent_rate = float(metrics.get("excellent_rate") or 0.0)
    candidates: list[dict] = []
    if avg is not None and avg < 60:
        candidates.append({"metric": "平均分", "threshold": 60, "value": _score_num(avg), "level": "red"})
    elif avg is not None and avg < 70:
        candidates.append({"metric": "平均分", "threshold": 70, "value": _score_num(avg), "level": "yellow"})
    if pass_rate < 70:
        candidates.append({"metric": "及格率", "threshold": 70, "value": _score_num(pass_rate), "level": "yellow"})
    if excellent_rate < 20:
        candidates.append({"metric": "优秀率", "threshold": 20, "value": _score_num(excellent_rate), "level": "yellow"})
    if not candidates and pass_rate >= 85 and avg is not None and avg >= 85:
        candidates.append({"metric": "综合表现", "threshold": 85, "value": _score_num(avg), "level": "green"})
    candidates.sort(key=lambda c: _LEVEL_RANK[c["level"]])
    return candidates[:2]


@router.get("/warnings", response_model=ApiResponse[dict])
def list_school_warnings(
    subject: Optional[str] = Query(None, description="学科过滤，默认全部"),
    grade: Optional[str] = Query(None, description="年级过滤，默认全部"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """学校版预警中心：按本校班级学情报告推导教学质量预警列表。"""
    caller = _check_admin_permission(db, user_id)

    # school scope：None=全校放行（兼容无学校绑定用户），有 school_id 则收敛到本校班级集
    class_ids = school_scope_class_ids(db, caller, None)

    class_q = db.query(Class)
    if class_ids is not None:
        class_q = class_q.filter(Class.id.in_(list(class_ids)))
    if grade:
        class_q = class_q.filter(Class.grade == grade)
    class_rows = class_q.all()
    cls_by_id: dict[str, Class] = {str(c.id): c for c in class_rows}

    report_q = db.query(ClassAnalysisReport)
    if class_ids is not None:
        report_q = report_q.filter(ClassAnalysisReport.class_id.in_(list(class_ids)))
    if subject:
        report_q = report_q.filter(ClassAnalysisReport.subject == subject)
    report_rows = report_q.all()

    # 学校名缓存（schools 锚表，表不存在时静默降级）
    school_ids = {str(getattr(c, "school_id", "")) for c in class_rows if getattr(c, "school_id", None)}
    school_names = _school_name_map(db, school_ids)

    warnings: list[dict] = []
    for row in report_rows:
        cls = cls_by_id.get(str(row.class_id))
        if cls is None:
            continue  # grade 过滤或 scope 外，跳过
        try:
            source_summary = json.loads(row.source_summary_json or "{}")
        except Exception:
            continue
        if not isinstance(source_summary, dict):
            continue
        metrics = _class_metrics(source_summary)
        candidates = _derive_candidates(metrics)
        if not candidates:
            continue

        school_id = str(getattr(cls, "school_id", "")) or ""
        school_name = school_names.get(school_id) if school_id else None
        created_at = row.generated_at.strftime("%Y-%m-%d") if row.generated_at else ""
        report_uuid = row.report_uuid or row.id

        for cand in candidates:
            warnings.append({
                "id": f"{report_uuid}:{cand['metric']}",
                "schoolName": school_name,
                "grade": cls.grade,
                "className": row.class_name,
                "subject": row.subject,
                "metric": cand["metric"],
                "value": cand["value"],
                "threshold": cand["threshold"],
                "level": cand["level"],
                "createdAt": created_at,
                "status": "active",
            })

    # 全局排序：red → yellow → green，同级按 createdAt 新→旧（稳定排序，先按时间倒序再按级别）
    warnings.sort(key=lambda w: w["createdAt"], reverse=True)
    warnings.sort(key=lambda w: _LEVEL_RANK[w["level"]])

    red = sum(1 for w in warnings if w["level"] == "red")
    yellow = sum(1 for w in warnings if w["level"] == "yellow")
    green = sum(1 for w in warnings if w["level"] == "green")

    # 统一学校名（前端头部展示）：取调用者归属学校，其次取首个预警班级所属学校
    user_school_id = get_user_school_id(db, caller)
    unified_school_name = school_names.get(str(user_school_id)) if user_school_id else None
    if not unified_school_name and warnings:
        unified_school_name = warnings[0].get("schoolName")

    return ApiResponse(data={
        "summary": {"total": len(warnings), "red": red, "yellow": yellow, "green": green},
        "warnings": warnings,
        "schoolName": unified_school_name,
    })
