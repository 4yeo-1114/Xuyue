# -*- coding: utf-8 -*-
"""扫描消耗、用量汇总 · 统计 API

参照七牛云计费用量页，提供：
  1. GET /scan-billing/consumption   — 消耗概览（总上传/总批改/存储/折线趋势）
  2. GET /scan-billing/trends        — 日/周/月粒度趋势明细（前端图表用）
  3. GET /scan-billing/breakdown     — 按文件夹维度的消耗明细
  4. GET /scan-billing/monthly       — 月度用量汇总
  5. GET /scan-billing/user-ranking  — 教师用量排名
  6. GET /scan-billing/pricing       — 计费规则与价格表（计费项/单位/免费额度/累进阶梯/抵扣顺序）
  7. GET /scan-billing/estimate      — 按量计费预估（本月至今，含免费额度抵扣与阶梯分段）
  8. GET /scan-billing/bill          — 月度账单（指定月份完整用量与费用）
  9. GET /scan-billing/usage-stats   — 用量统计（汇总 + 序列 + 维度明细）

数据源：grading_daily_stats（app/models/grading_daily_stat.py），
由 app/grading/grading_stats.py 在批改主流程旁路累加，无需新增表。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.grading_daily_stat import GradingDailyStat
from app.models.user import User
from app.schemas.common import ApiResponse
from app.utils.school_access import get_user_roles

router = APIRouter(prefix="/scan-billing", tags=["scan_billing"])

# 「独立老师」所绑定的既有角色名（与前端 constants/systemRoles.ts 同源，⛔ 不新增角色）
TEACHER_ROLE = "任课教师"


def _roles_are_teacher_only(roles: set[str]) -> bool:
    """角色集合是否恰为「仅任课教师」。

    与 frontend/src/constants/systemRoles.ts 的 isTeacherOnlyAccount 同口径：
    **非空、且每一项都是「任课教师」**。多出任何一个其他角色
    （含「测试账号」「班主任」）即 false ⇒ 不受本收敛约束。
    """
    return bool(roles) and all(r == TEACHER_ROLE for r in roles)


def _is_teacher_only_account(db: Session, user_id: str) -> bool:
    """调用者是否为「仅任课教师」账号（独立老师）。"""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        # 验签通过的 token 却查不到 users 行属异常态：判据不可得时按最保守一侧收窄到本人。
        # 宁可让管理员少看全平台，也不让任课教师看到全平台。
        return True
    return _roles_are_teacher_only(get_user_roles(user))


def resolve_scope_user_id(
    db: Session, current_user_id: str, requested_user_id: Optional[str]
) -> Optional[str]:
    """把「请求里声明的 user_id」收敛为「调用者有权查看的 user_id」。

    - **仅任课教师**账号（独立老师）：query 参数不可信，**忽略**显式传入的 user_id，
      强制回落为调用者本人 —— 传别人的 id 也仍然只能拿到自己的数据。
    - 其他角色（系统管理员 / 子系统管理员 / 校级管理者 / 年级组长 / 班主任 / 测试账号）：
      原样透传，None 仍表示全平台 —— 行为与改动前逐字一致。
    """
    if _is_teacher_only_account(db, current_user_id):
        return current_user_id
    return requested_user_id


def _today() -> date:
    return date.today()


def _date_range(start: date, end: date) -> list[date]:
    """生成 [start, end] 日期列表"""
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


# ──────────────────────────────────────────────
# 1. 消耗概览（总上传/总批改/存储量/趋势）
# ──────────────────────────────────────────────

@router.get("/consumption", response_model=ApiResponse[dict])
def get_consumption(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    user_id: Optional[str] = Query(None, description="筛选教师 ID；为空则查全部"),
    db: Session = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    """消耗概览：类比七牛云计费用量首页。"""
    end = _today()
    start = end - timedelta(days=days - 1)

    scope_user_id = resolve_scope_user_id(db, _uid, user_id)

    # 基础查询条件
    base_filter = [GradingDailyStat.stat_date >= start, GradingDailyStat.stat_date <= end]
    if scope_user_id:
        base_filter.append(GradingDailyStat.user_id == scope_user_id)

    rows = (
        db.query(GradingDailyStat)
        .filter(*base_filter)
        .all()
    )

    total_upload = 0
    total_grade = 0
    daily_map: dict[str, dict[str, int]] = {}

    for r in rows:
        d_str = r.stat_date.isoformat()
        upload = int(r.upload_count or 0)
        grade = int(r.grade_count or 0)
        total_upload += upload
        total_grade += grade

        if d_str not in daily_map:
            daily_map[d_str] = {"upload": 0, "grade": 0}
        daily_map[d_str]["upload"] += upload
        daily_map[d_str]["grade"] += grade

    # 补全天数（无数据的天填 0）
    daily_trend: list[dict[str, Any]] = []
    for d in _date_range(start, end):
        d_str = d.isoformat()
        row = daily_map.get(d_str, {"upload": 0, "grade": 0})
        daily_trend.append({
            "date": d_str,
            "upload": row["upload"],
            "grade": row["grade"],
        })

    return ApiResponse(data={
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "total_upload": total_upload,
        "total_grade": total_grade,
        "total_operations": total_upload + total_grade,
        "daily_trend": daily_trend,
        "estimated_storage_mb": _estimate_storage_mb(scope_user_id),
    })


def _estimate_storage_mb(user_id: Optional[str] = None) -> float:
    """估算存储用量（MB）：扫描各用户 correct_docs（试卷原图）目录大小。

    目录布局见 app/grading/user_paths.py：
      grading_data_all/grading_data_<safe_uid>/correct_documents/test_paper
    """
    from app.grading.user_paths import get_user_grading_paths, grading_data_all_root

    base = grading_data_all_root()

    if user_id:
        docs_dirs = [get_user_grading_paths(user_id).correct_docs]
    else:
        if not base.is_dir():
            return 0.0
        docs_dirs = [
            d / "correct_documents" / "test_paper"
            for d in base.iterdir()
            if d.is_dir()
        ]

    total_bytes = 0
    for docs_dir in docs_dirs:
        try:
            if not docs_dir.is_dir():
                continue
            for f in docs_dir.rglob("*"):
                if f.is_file():
                    total_bytes += f.stat().st_size
        except OSError:
            # 单个用户目录不可读时跳过，不影响整体估算
            continue

    return round(total_bytes / (1024 * 1024), 2)


# ──────────────────────────────────────────────
# 2. 日粒度趋势明细（前端图表用）
# ──────────────────────────────────────────────

@router.get("/trends", response_model=ApiResponse[list])
def get_trends(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    user_id: Optional[str] = Query(None, description="筛选教师"),
    granularity: str = Query("day", pattern="^(day|week|month)$"),
    db: Session = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    """趋势明细：日/周/月粒度，供 ECharts / Recharts 折线图。"""
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    scope_user_id = resolve_scope_user_id(db, _uid, user_id)

    base_filter = [
        GradingDailyStat.stat_date >= start_date,
        GradingDailyStat.stat_date <= end_date,
    ]
    if scope_user_id:
        base_filter.append(GradingDailyStat.user_id == scope_user_id)

    rows = (
        db.query(GradingDailyStat)
        .filter(*base_filter)
        .order_by(GradingDailyStat.stat_date)
        .all()
    )

    daily_map: dict[str, dict[str, int]] = {}
    for r in rows:
        d_str = r.stat_date.isoformat()
        if d_str not in daily_map:
            daily_map[d_str] = {"upload": 0, "grade": 0}
        daily_map[d_str]["upload"] += int(r.upload_count or 0)
        daily_map[d_str]["grade"] += int(r.grade_count or 0)

    if granularity == "day":
        result = []
        for d in _date_range(start_date, end_date):
            d_str = d.isoformat()
            row = daily_map.get(d_str, {"upload": 0, "grade": 0})
            result.append({
                "period": d_str,
                "label": d_str,
                "upload": row["upload"],
                "grade": row["grade"],
            })
        return ApiResponse(data=result)

    # 周/月聚合
    period_map: dict[str, dict[str, Any]] = {}

    for d in _date_range(start_date, end_date):
        d_str = d.isoformat()
        if granularity == "week":
            iso = d.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
            label = f"{iso[0]} 第{iso[1]}周"
        else:
            key = f"{d.year}-{d.month:02d}"
            label = f"{d.year}年{d.month}月"

        if key not in period_map:
            period_map[key] = {"period": key, "label": label, "upload": 0, "grade": 0}
        row = daily_map.get(d_str, {"upload": 0, "grade": 0})
        period_map[key]["upload"] += row["upload"]
        period_map[key]["grade"] += row["grade"]

    result = sorted(period_map.values(), key=lambda x: x["period"])
    return ApiResponse(data=result)


# ──────────────────────────────────────────────
# 3. 按文件夹 / 资源维度消耗明细
# ──────────────────────────────────────────────

@router.get("/breakdown", response_model=ApiResponse[list])
def get_breakdown(
    days: int = Query(30, ge=1, le=365),
    user_id: Optional[str] = Query(None, description="筛选教师"),
    sort_by: str = Query("upload", pattern="^(upload|grade|total)$"),
    db: Session = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    """资源消耗明细：按文件夹聚合，类比七牛云「空间-文件」列表。"""
    end = _today()
    start = end - timedelta(days=days - 1)

    scope_user_id = resolve_scope_user_id(db, _uid, user_id)

    base_filter = [
        GradingDailyStat.stat_date >= start,
        GradingDailyStat.stat_date <= end,
    ]
    if scope_user_id:
        base_filter.append(GradingDailyStat.user_id == scope_user_id)

    rows = (
        db.query(
            GradingDailyStat.folder_safe,
            func.sum(GradingDailyStat.upload_count).label("upload"),
            func.sum(GradingDailyStat.grade_count).label("grade"),
        )
        .filter(*base_filter)
        .group_by(GradingDailyStat.folder_safe)
        .all()
    )

    from app.grading.grading_stats import display_folder_name

    result = []
    for r in rows:
        folder = r.folder_safe or "_default"
        upload = int(r.upload or 0)
        grade = int(r.grade or 0)
        result.append({
            "folder_safe": folder,
            "folder_name": display_folder_name(folder),
            "upload": upload,
            "grade": grade,
            "total": upload + grade,
        })

    # 排序
    sort_key = {"upload": lambda x: x["upload"], "grade": lambda x: x["grade"], "total": lambda x: x["total"]}
    result.sort(key=sort_key.get(sort_by, sort_key["upload"]), reverse=True)
    return ApiResponse(data=result)


# ──────────────────────────────────────────────
# 4. 月度汇总
# ──────────────────────────────────────────────

@router.get("/monthly", response_model=ApiResponse[list])
def get_monthly_summary(
    months: int = Query(6, ge=1, le=24, description="回溯月数"),
    user_id: Optional[str] = Query(None, description="筛选教师"),
    db: Session = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    """月度用量汇总（类比七牛云月度账单）。"""
    scope_user_id = resolve_scope_user_id(db, _uid, user_id)
    end = _today()
    # 回溯到 months 个月前的 1 号
    start_month = end.month - (months - 1)
    start_year = end.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start = date(start_year, start_month, 1)

    base_filter = [
        GradingDailyStat.stat_date >= start,
        GradingDailyStat.stat_date <= end,
    ]
    if scope_user_id:
        base_filter.append(GradingDailyStat.user_id == scope_user_id)

    rows = (
        db.query(GradingDailyStat)
        .filter(*base_filter)
        .all()
    )

    monthly_map: dict[str, dict[str, Any]] = {}

    for r in rows:
        key = f"{r.stat_date.year}-{r.stat_date.month:02d}"
        label = f"{r.stat_date.year}年{r.stat_date.month}月"
        if key not in monthly_map:
            monthly_map[key] = {
                "month": key,
                "label": label,
                "upload": 0,
                "grade": 0,
                "active_users": set(),
            }
        monthly_map[key]["upload"] += int(r.upload_count or 0)
        monthly_map[key]["grade"] += int(r.grade_count or 0)
        monthly_map[key]["active_users"].add(r.user_id)

    result = []
    for key, v in sorted(monthly_map.items()):
        result.append({
            "month": v["month"],
            "label": v["label"],
            "upload": v["upload"],
            "grade": v["grade"],
            "total": v["upload"] + v["grade"],
            "active_users": len(v["active_users"]),
        })

    return ApiResponse(data=result)


# ──────────────────────────────────────────────
# 5. 教师用量排名（管理员用）
# ──────────────────────────────────────────────

@router.get("/user-ranking", response_model=ApiResponse[list])
def get_user_ranking(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    """教师用量排名：按操作总量降序。

    仅任课教师账号（独立老师）：收窄为「只有自己一人」的名单
    （返回本人用量，rank 恒为 1），⛔ 不返回全体教师排名、⛔ 不 403 ——
    与其余 8 个端点「只返回自己的数据」保持同一口径，前端的「按教师」视图不落空。
    """
    scope_user_id = resolve_scope_user_id(db, _uid, None)
    end = _today()
    start = end - timedelta(days=days - 1)

    ranking_filter = [
        GradingDailyStat.stat_date >= start,
        GradingDailyStat.stat_date <= end,
    ]
    if scope_user_id:
        ranking_filter.append(GradingDailyStat.user_id == scope_user_id)

    rows = (
        db.query(
            GradingDailyStat.user_id,
            func.sum(GradingDailyStat.upload_count).label("upload"),
            func.sum(GradingDailyStat.grade_count).label("grade"),
        )
        .filter(*ranking_filter)
        .group_by(GradingDailyStat.user_id)
        .order_by(text("upload + grade DESC"))
        .limit(limit)
        .all()
    )

    user_ids = [r.user_id for r in rows]
    user_map = {}
    if user_ids:
        users = (
            db.query(User.id, User.display_name, User.email)
            .filter(User.id.in_(user_ids))
            .all()
        )
        user_map = {u.id: u for u in users}

    result = []
    for i, r in enumerate(rows, 1):
        u = user_map.get(r.user_id)
        upload = int(r.upload or 0)
        grade = int(r.grade or 0)
        result.append({
            "rank": i,
            "user_id": r.user_id,
            "display_name": u.display_name if u else None,
            "email": u.email if u else None,
            "upload": upload,
            "grade": grade,
            "total": upload + grade,
        })

    return ApiResponse(data=result)


# ──────────────────────────────────────────────
# 计费用量（对齐七牛云计费模型）
# ──────────────────────────────────────────────


def _sum_counts(db: Session, start: date, end: date, user_id: Optional[str]) -> tuple[int, int]:
    """区间内上传/批改总量。"""
    q = db.query(
        func.coalesce(func.sum(GradingDailyStat.upload_count), 0),
        func.coalesce(func.sum(GradingDailyStat.grade_count), 0),
    ).filter(
        GradingDailyStat.stat_date >= start,
        GradingDailyStat.stat_date <= end,
    )
    if user_id:
        q = q.filter(GradingDailyStat.user_id == user_id)
    upload, grade = q.one()
    return int(upload or 0), int(grade or 0)


@router.get("/pricing", response_model=ApiResponse[dict])
def get_pricing(
    _uid: str = Depends(get_current_user_id),
):
    """计费规则与价格表（计费项、单位、免费额度、累进阶梯、抵扣顺序）。"""
    from app.services import billing_pricing as bp

    cfg = bp.load_config()
    items = []
    for key, item in cfg["items"].items():
        items.append({
            "key": key,
            "label": item.get("label"),
            "category": item.get("category"),
            "unit": item.get("unit"),
            "basis": item.get("basis"),
            "basis_label": "月度日均值" if item.get("basis") == "monthly_avg" else "新增累积",
            "round_up": bool(item.get("round_up")),
            "round_up_label": "不足 1 单位按 1 单位计" if item.get("round_up") else "按实际值计",
            "free_quota": item.get("free_quota", 0),
            "resource_pack": item.get("resource_pack", 0),
            "tiers": item.get("tiers", []),
        })
    return ApiResponse(data={
        "currency": cfg.get("currency", "CNY"),
        "note": cfg.get("note", ""),
        "deduction_order": cfg.get("deduction_order", []),
        "deduction_order_label": "免费额度 → 资源包 → 阶梯价格",
        "items": items,
    })


def _build_estimate(
    db: Session,
    start: date,
    end: date,
    user_id: Optional[str],
    *,
    proration: float,
    period_label: str,
) -> dict[str, Any]:
    """构造按量计费预估（存储按月度日均，其余按新增累积）。"""
    from app.services import billing_pricing as bp

    upload, grade = _sum_counts(db, start, end, user_id)

    # 存储：取结束日所在月份的日均值
    storage_info = bp.monthly_avg_storage_gb(
        end.year, end.month, user_id, up_to_today=(end >= _today())
    )

    raw = {
        "storage": storage_info["avg_gb"],
        "upload": upload,
        "grading": grade,
        "download": 0.0,  # 预留：当前无导出流量埋点
    }
    result = bp.calc_total(raw)

    # 存储类按月折算：金额 × (当月已发生天数 / 当月总天数)
    for row in result["items"]:
        if row.get("basis") == "monthly_avg":
            row["proration"] = proration
            row["amount"] = round((row.get("amount") or 0.0) * proration, 4)
    result["total_amount"] = round(sum(r.get("amount") or 0.0 for r in result["items"]), 4)

    result.update({
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "period_label": period_label,
        "storage": {
            "avg_gb": storage_info["avg_gb"],
            "elapsed_days": storage_info["elapsed_days"],
            "days_in_month": storage_info["days_in_month"],
        },
        "usage": {"upload": upload, "grade": grade},
        "is_estimate": True,
    })
    return result


@router.get("/estimate", response_model=ApiResponse[dict])
def get_estimate(
    user_id: Optional[str] = Query(None, description="筛选教师"),
    db: Session = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    """按量计费预估：本月 1 号 0:00 至今天，含免费额度抵扣与阶梯分段。

    对齐七牛「按量计费预估」——未出账，仅供参考，非最终账单。
    """
    from app.services import billing_pricing as bp

    scope_user_id = resolve_scope_user_id(db, _uid, user_id)
    today = _today()
    first = today.replace(day=1)
    info = bp.monthly_avg_storage_gb(today.year, today.month, scope_user_id, up_to_today=True)
    return ApiResponse(data=_build_estimate(
        db, first, today, scope_user_id,
        proration=info["proration"],
        period_label=f"{today.year}年{today.month}月（截至 {today.isoformat()}）",
    ))


@router.get("/bill", response_model=ApiResponse[dict])
def get_bill(
    month: Optional[str] = Query(None, description="账单月份 YYYY-MM，默认上个月"),
    user_id: Optional[str] = Query(None, description="筛选教师"),
    db: Session = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    """月度账单：指定月份完整用量与费用（类比七牛月账单）。

    对齐七牛结算口径：存储取该月**整月日均值**，折价系数为 1.0。
    """
    import calendar
    from app.services import billing_pricing as bp

    scope_user_id = resolve_scope_user_id(db, _uid, user_id)
    today = _today()
    if month:
        try:
            y_str, m_str = month.split("-")
            year, mon = int(y_str), int(m_str)
            if not 1 <= mon <= 12:
                raise ValueError
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")
    else:
        # 默认上个月
        first_this = today.replace(day=1)
        prev = first_this - timedelta(days=1)
        year, mon = prev.year, prev.month

    first = date(year, mon, 1)
    last = date(year, mon, calendar.monthrange(year, mon)[1])
    # 当月未结束则截到今天（此时为预估值）
    is_settled = last < today
    end = last if is_settled else min(last, today)

    if end < first:
        end = first

    data = _build_estimate(
        db, first, end, scope_user_id,
        proration=1.0 if is_settled else bp.monthly_avg_storage_gb(year, mon, scope_user_id)["proration"],
        period_label=f"{year}年{mon}月",
    )
    data.update({
        "month": f"{year}-{mon:02d}",
        "is_estimate": not is_settled,
        "settled": is_settled,
        "settle_note": (
            "账单已出（当月已结束）" if is_settled
            else "当月未结束，为预估值；七牛口径为次月 5 号出账"
        ),
    })
    return ApiResponse(data=data)


@router.get("/usage-stats", response_model=ApiResponse[dict])
def get_usage_stats(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    granularity: str = Query("day", pattern="^(day|week|month)$"),
    dimension: str = Query("all", pattern="^(all|folder|user)$", description="统计维度"),
    metric: str = Query("all", pattern="^(all|upload|grade)$"),
    user_id: Optional[str] = Query(None, description="筛选教师"),
    db: Session = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    """用量统计：汇总（总计/日均/峰值）+ 序列 + 维度明细。

    对齐七牛「用量统计」页：时间范围 / 粒度 / 维度筛选，图表按维度堆叠，支持导出 CSV。
    """
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    scope_user_id = resolve_scope_user_id(db, _uid, user_id)

    base = [
        GradingDailyStat.stat_date >= start_date,
        GradingDailyStat.stat_date <= end_date,
    ]
    if scope_user_id:
        base.append(GradingDailyStat.user_id == scope_user_id)

    rows = db.query(GradingDailyStat).filter(*base).all()

    daily: dict[str, dict[str, int]] = {}
    by_dim: dict[str, dict[str, int]] = {}
    for r in rows:
        d = r.stat_date.isoformat()
        up, gr = int(r.upload_count or 0), int(r.grade_count or 0)

        slot = daily.setdefault(d, {"upload": 0, "grade": 0})
        slot["upload"] += up
        slot["grade"] += gr

        if dimension == "folder":
            key = r.folder_safe or "_default"
        elif dimension == "user":
            key = r.user_id
        else:
            key = None
        if key is not None:
            dim = by_dim.setdefault(key, {"upload": 0, "grade": 0})
            dim["upload"] += up
            dim["grade"] += gr

    # 序列（按粒度聚合）
    series: list[dict[str, Any]] = []
    if granularity == "day":
        for d in _date_range(start_date, end_date):
            k = d.isoformat()
            v = daily.get(k, {"upload": 0, "grade": 0})
            series.append({"period": k, "label": k, "upload": v["upload"], "grade": v["grade"]})
    else:
        bucket: dict[str, dict[str, Any]] = {}
        for d in _date_range(start_date, end_date):
            if granularity == "week":
                iso = d.isocalendar()
                key, label = f"{iso[0]}-W{iso[1]:02d}", f"{iso[0]} 第{iso[1]}周"
            else:
                key, label = f"{d.year}-{d.month:02d}", f"{d.year}年{d.month}月"
            b = bucket.setdefault(key, {"period": key, "label": label, "upload": 0, "grade": 0})
            v = daily.get(d.isoformat(), {"upload": 0, "grade": 0})
            b["upload"] += v["upload"]
            b["grade"] += v["grade"]
        series = sorted(bucket.values(), key=lambda x: x["period"])

    # 汇总：总计 / 日均 / 峰值
    total_upload = sum(v["upload"] for v in daily.values())
    total_grade = sum(v["grade"] for v in daily.values())
    days = max(1, len(_date_range(start_date, end_date)))

    peak_day, peak_val = None, 0
    for k, v in daily.items():
        t = v["upload"] + v["grade"]
        if t > peak_val:
            peak_day, peak_val = k, t

    # 维度明细补名称
    dim_rows: list[dict[str, Any]] = []
    if dimension != "all" and by_dim:
        if dimension == "user":
            uids = list(by_dim.keys())
            users = db.query(User.id, User.display_name, User.email).filter(User.id.in_(uids)).all()
            umap = {u.id: u for u in users}
        else:
            umap = {}
        from app.grading.grading_stats import display_folder_name

        for key, v in sorted(by_dim.items(), key=lambda kv: kv[1]["upload"] + kv[1]["grade"], reverse=True):
            if dimension == "folder":
                name = display_folder_name(key)
            else:
                u = umap.get(key)
                name = (getattr(u, "display_name", None) or getattr(u, "email", None) or key) if u else key
            dim_rows.append({
                "key": key,
                "name": name,
                "upload": v["upload"],
                "grade": v["grade"],
                "total": v["upload"] + v["grade"],
            })

    return ApiResponse(data={
        "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "granularity": granularity,
        "dimension": dimension,
        "metric": metric,
        "summary": {
            "total_upload": total_upload,
            "total_grade": total_grade,
            "total": total_upload + total_grade,
            "avg_daily_upload": round(total_upload / days, 2),
            "avg_daily_grade": round(total_grade / days, 2),
            "avg_daily_total": round((total_upload + total_grade) / days, 2),
            "peak_day": peak_day,
            "peak_value": peak_val,
            "days": days,
        },
        "series": series,
        "breakdown": dim_rows,
    })