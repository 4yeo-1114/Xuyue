# -*- coding: utf-8 -*-
"""账号总览（0924 需求三 · 最牛管理页）：平台管理员一次性看全所有账号的
操作用量 / 面数额度 / 花销 / 充值 / 钱包 / 支付 / 存储。

数据源（口径不合并，各栏位分别如实标注口径）：
  · 操作用量      grading_daily_stats（upload_count / grade_count，口径 A）
  · 面数额度      grading_quota（total_pages / used_pages，面数口径）
  · 充值（面数）  grading_quota_recharge_logs（amount_yuan / total_pages，面数口径）
  · 花销（平台成本） billing_pricing 按「批改面数 × 单价」折价（口径 A，参考值）
  · 钱包（分余额） payment_accounts（balance / recharged / consumed，口径 B）
  · 存储占用      grading_data_all 各用户试卷目录大小（参考值，不参与计费）

仅系统管理员 / 子系统管理员可访问。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.grading_daily_stat import GradingDailyStat
from app.models.grading_quota import GradingQuota, GradingQuotaRechargeLog
from app.models.payment_account import PaymentAccount
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services import quota_service as qs
from app.utils.school_access import is_platform_admin

router = APIRouter(tags=["admin_accounts_overview"])

# 累计口径的统计起点：只统计 2026-09-01 起（不含 6 月起的旧数据）
STAT_START = date(2026, 9, 1)

# 账号范围（2026-09-28 用户澄清·反转）：
#   ① 邮箱含 @pgj.com 的账号一律不进总览（那是人家项目的账号）；
#   ② 叙阅 9 月才独立出来，2026-09-01 之前注册的账号也不进总览。
EXCLUDED_EMAIL_DOMAIN = "@pgj.com"


def _require_platform_admin(db: Session, user_id: str) -> User:
    u = db.query(User).filter(User.id == user_id).first()
    if not u or not is_platform_admin(u):
        raise HTTPException(status_code=403, detail="仅系统管理员/子系统管理员可操作")
    return u


def _roles_list(u: User) -> Optional[list[str]]:
    roles = [r.strip() for r in (u.roles or "").split(",") if r.strip()]
    return roles or None


def _account_group(u: User) -> str:
    """账号分组（前端「文件夹」筛选）= 邮箱域名（@ 之后部分）。

    同一批批量创建的账号用同一域名，总览页即可按文件夹点进去只看这批，
    与其他账号不混淆。无邮箱归入「未分组」。
    """
    email = (u.email or "").strip()
    if "@" not in email:
        return "未分组"
    return email.rsplit("@", 1)[1].lower() or "未分组"


def _grading_price_per_face() -> float:
    """批改单价（元/面）。默认 0.5，可被 billing_config.json 覆盖。"""
    try:
        from app.services import billing_pricing as bp

        cfg = bp.load_config()
        tiers = (cfg.get("items", {}).get("grading", {}) or {}).get("tiers") or []
        if tiers:
            return float(tiers[0].get("price") or 0.5)
    except Exception:
        pass
    return 0.5


def _storage_bytes_by_dir() -> dict[str, int]:
    """单次扫描 grading_data_all，返回 {目录名: 试卷原图字节数}。

    ⛔ 只读不建目录（不调用 get_user_grading_paths / ensure_user_grading_layout，
       避免为每个账号触发目录创建副作用）。
    """
    from app.grading.user_paths import grading_data_all_root

    base = grading_data_all_root()
    result: dict[str, int] = {}
    if not base.is_dir():
        return result
    for d in base.iterdir():
        try:
            if not d.is_dir():
                continue
            docs = d / "correct_documents" / "test_paper"
            if not docs.is_dir():
                continue
            total = 0
            for f in docs.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
            result[d.name] = total
        except OSError:
            continue
    return result


def _today() -> date:
    return date.today()


@router.get("/admin/accounts/overview", response_model=ApiResponse[dict])
def admin_accounts_overview(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365, description="近 N 天用量窗口"),
):
    """账号总览：按账号聚合全维度用量/额度/花销/充值/钱包/支付。"""
    _require_platform_admin(db, user_id)

    today = _today()
    recent_start = today - timedelta(days=days - 1)

    users = (
        db.query(User)
        .filter(
            or_(
                User.email.is_(None),
                User.email.notlike(f"%{EXCLUDED_EMAIL_DOMAIN}"),
            ),
            User.created_at >= datetime(2026, 9, 1),
        )
        .order_by(User.created_at, User.email)
        .all()
    )

    # ── 面数额度 ──
    quota_map = {q.user_id: q for q in db.query(GradingQuota).all()}

    # ── 操作用量（一次 SQL 聚合：累计 / 近 N 天 / 今日）──
    daily_rows = (
        db.query(
            GradingDailyStat.user_id,
            func.sum(GradingDailyStat.upload_count).label("up_life"),
            func.sum(GradingDailyStat.grade_count).label("gr_life"),
            func.sum(
                case(
                    (GradingDailyStat.stat_date >= recent_start, GradingDailyStat.upload_count),
                    else_=0,
                )
            ).label("up_recent"),
            func.sum(
                case(
                    (GradingDailyStat.stat_date >= recent_start, GradingDailyStat.grade_count),
                    else_=0,
                )
            ).label("gr_recent"),
            func.sum(
                case(
                    (GradingDailyStat.stat_date == today, GradingDailyStat.upload_count),
                    else_=0,
                )
            ).label("up_today"),
            func.sum(
                case(
                    (GradingDailyStat.stat_date == today, GradingDailyStat.grade_count),
                    else_=0,
                )
            ).label("gr_today"),
        )
        .filter(GradingDailyStat.stat_date >= STAT_START)
        .group_by(GradingDailyStat.user_id)
        .all()
    )
    daily_map: dict[str, dict[str, int]] = {}
    for r in daily_rows:
        daily_map[r.user_id] = {
            "upload_lifetime": int(r.up_life or 0),
            "grade_lifetime": int(r.gr_life or 0),
            "upload_recent": int(r.up_recent or 0),
            "grade_recent": int(r.gr_recent or 0),
            "upload_today": int(r.up_today or 0),
            "grade_today": int(r.gr_today or 0),
        }

    # ── 充值（面数口径）──
    recharge_rows = (
        db.query(
            GradingQuotaRechargeLog.user_id,
            func.coalesce(func.sum(GradingQuotaRechargeLog.amount_yuan), 0).label("amt"),
            func.coalesce(func.sum(GradingQuotaRechargeLog.total_pages), 0).label("pages"),
            func.count(GradingQuotaRechargeLog.id).label("cnt"),
            func.max(GradingQuotaRechargeLog.created_at).label("last"),
        )
        .group_by(GradingQuotaRechargeLog.user_id)
        .all()
    )
    recharge_map: dict[str, dict[str, Any]] = {}
    for r in recharge_rows:
        recharge_map[r.user_id] = {
            "amount_yuan_total": int(r.amt or 0),
            "pages_total": int(r.pages or 0),
            "count": int(r.cnt or 0),
            "last_at": r.last.isoformat() if r.last else None,
        }

    # ── 钱包（口径 B 分余额）──
    wallet_map = {p.user_id: p for p in db.query(PaymentAccount).all()}

    # ── 存储占用 ──
    from app.grading.user_paths import user_grading_dir_name

    storage_by_dir = _storage_bytes_by_dir()
    grading_price = _grading_price_per_face()

    items: list[dict[str, Any]] = []
    # 平台汇总
    s_total_upload = 0
    s_total_grade = 0
    s_recharge_yuan = 0
    s_recharge_pages = 0
    s_grading_cost = 0.0
    s_wallet_balance = 0
    s_wallet_recharged = 0
    s_wallet_consumed = 0

    for u in users:
        q = quota_map.get(u.id)
        total_pages = int(q.total_pages or 0) if q else 0
        used_pages = int(q.used_pages or 0) if q else 0
        usage = daily_map.get(u.id, {
            "upload_lifetime": 0, "grade_lifetime": 0,
            "upload_recent": 0, "grade_recent": 0,
            "upload_today": 0, "grade_today": 0,
        })
        recharge = recharge_map.get(u.id, {
            "amount_yuan_total": 0, "pages_total": 0, "count": 0, "last_at": None,
        })
        w = wallet_map.get(u.id)

        grade_lifetime = usage["grade_lifetime"]
        grading_cost = round(grade_lifetime * grading_price, 2)
        storage_bytes = storage_by_dir.get(user_grading_dir_name(u.id), 0)

        upload_lifetime = usage["upload_lifetime"]
        s_total_upload += upload_lifetime
        s_total_grade += grade_lifetime
        s_recharge_yuan += recharge["amount_yuan_total"]
        s_recharge_pages += recharge["pages_total"]
        s_grading_cost += grading_cost
        s_wallet_balance += int(w.balance_fen or 0) if w else 0
        s_wallet_recharged += int(w.total_recharged_fen or 0) if w else 0
        s_wallet_consumed += int(w.total_consumed_fen or 0) if w else 0

        items.append(
            {
                "user_id": str(u.id),
                "display_name": u.display_name,
                "email": u.email,
                "phone": u.phone,
                "group": _account_group(u),
                "roles": _roles_list(u),
                "teaching_subject": u.teaching_subject,
                "teaching_grade": u.teaching_grade,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "usage": {
                    **usage,
                    "total_lifetime": upload_lifetime + grade_lifetime,
                    "total_recent": usage["upload_recent"] + usage["grade_recent"],
                    "total_today": usage["upload_today"] + usage["grade_today"],
                    "storage_mb": round(storage_bytes / (1024 * 1024), 2),
                },
                "quota": {
                    "total_pages": total_pages,
                    "used_pages": used_pages,
                    "available": total_pages - used_pages,
                    "used_pct": qs.to_usage(q)["used_pct"],
                    "today_pages": qs.today_pages_of(q),
                    "locked": qs.is_locked(total_pages, used_pages),
                },
                "recharge": recharge,
                "cost": {
                    "grading_price_per_face": grading_price,
                    "grading_cost_yuan": grading_cost,
                    "note": "口径 A · 批改面数 × 单价（参考值，存储/请求另计）",
                },
                "wallet": {
                    "balance_yuan": round(int(w.balance_fen or 0) / 100, 2) if w else 0.0,
                    "total_recharged_yuan": round(int(w.total_recharged_fen or 0) / 100, 2) if w else 0.0,
                    "total_consumed_yuan": round(int(w.total_consumed_fen or 0) / 100, 2) if w else 0.0,
                },
            }
        )

    return ApiResponse(
        data={
            "window_days": days,
            "stat_start": STAT_START.isoformat(),
            "scope_note": f"已排除邮箱含 {EXCLUDED_EMAIL_DOMAIN} 的账号及 2026-09-01 前注册的账号",
            "grading_price_per_face": grading_price,
            "total_accounts": len(items),
            "summary": {
                "total_upload_lifetime": s_total_upload,
                "total_grade_lifetime": s_total_grade,
                "total_operations_lifetime": s_total_upload + s_total_grade,
                "recharge_yuan_total": s_recharge_yuan,
                "recharge_pages_total": s_recharge_pages,
                "grading_cost_yuan_total": round(s_grading_cost, 2),
                "wallet_balance_yuan_total": round(s_wallet_balance / 100, 2),
                "wallet_recharged_yuan_total": round(s_wallet_recharged / 100, 2),
                "wallet_consumed_yuan_total": round(s_wallet_consumed / 100, 2),
            },
            "items": items,
        }
    )
