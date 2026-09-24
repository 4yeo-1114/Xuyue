# -*- coding: utf-8 -*-
"""扫描用量接口 · 账号隔离（独立老师只看自己）验收测试。

背景：scan_billing.py 的 9 个端点原先是只读 GET 且**全无用户隔离** ——
`user_id: Optional[str] = Query(None)` 不传即全平台，/user-ranking 更是直接
返回全体教师排名。任课教师（独立老师）因此能看到全平台用量/账单/全体排名。

本文件覆盖带用户维度的 8 个端点：
  /consumption /trends /breakdown /monthly /estimate /bill /usage-stats /user-ranking

判据（口径与 frontend/src/constants/systemRoles.ts 的 isTeacherOnlyAccount 同源）：
  1. 仅任课教师（角色集合恰为 {任课教师}）⇒ 只返回自己的数据
  2. 显式传入的 user_id **不可信** ⇒ 传别人的 id 结果仍是自己的（核心安全断言）
  3. 其他角色（校级管理者/系统管理员/任课教师+班主任）⇒ 行为与改动前逐字一致

测试方式：**真 SQLite 内存库**（真执行 SQL，WHERE 过滤真实生效 —— 不用「filter 透传」
的假 db，否则「只含自己」这类断言会被假 db 蒙混过关）+ 真实 FastAPI TestClient 走路由，
`get_db` / `get_current_user_id` 用 dependency_overrides 注入。
存储目录扫描（correct_docs）指向空临时目录，保证不读也不写真数据。
"""
import calendar
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.dependencies import get_current_user_id
from app.models.grading_daily_stat import GradingDailyStat
from app.models.user import User
from app.routers import scan_billing

# ── 账号 / 角色 ───────────────────────────────────────────
TEACHER = "u-teacher"          # 独立老师：角色集合恰为 {任课教师}
OTHER = "u-other"              # 另一个任课教师（教师视角里「别人的数据」）
COMBO = "u-combo"              # 任课教师 + 班主任（多角色 ⇒ 不受收敛约束）
SCHOOL_ADMIN = "u-school"      # 校级管理者
SYS_ADMIN = "u-sysadmin"       # 系统管理员
GHOST = "u-ghost"              # 验签通过但 users 表里没有该行（异常态）

# ── 用量种子（today 当天）───────────────────────────────
TODAY = date.today()
PREV_LAST = TODAY.replace(day=1) - timedelta(days=1)  # 上个月最后一天

SEED_TODAY = {
    TEACHER: (11, 22),
    OTHER: (33, 44),
    COMBO: (55, 66),
    SCHOOL_ADMIN: (77, 88),
    SYS_ADMIN: (99, 100),
}
ALL_UPLOAD = sum(u for u, _ in SEED_TODAY.values())      # 275
ALL_GRADE = sum(g for _, g in SEED_TODAY.values())       # 320

# 上个月（/bill 默认月）：全体 14/14，任课教师本人 5/5
SEED_PREV = {TEACHER: (5, 5), OTHER: (9, 9)}
PREV_ALL_UPLOAD = sum(u for u, _ in SEED_PREV.values())  # 14
PREV_ALL_GRADE = sum(g for _, g in SEED_PREV.values())   # 14


@pytest.fixture(autouse=True)
def _empty_storage_root(monkeypatch, tmp_path):
    """存储扫描指向空目录：/consumption、/estimate、/bill 会 stat correct_docs。

    这两个调用点都是「函数内 from app.grading.user_paths import ...」，
    故打在模块属性上即可同时覆盖 _estimate_storage_mb 与 billing_pricing.daily_storage_gb。
    """
    import app.grading.user_paths as up

    empty: Path = tmp_path / "grading_data_all"
    empty.mkdir()
    monkeypatch.setattr(up, "grading_data_all_root", lambda: empty)


@pytest.fixture
def db():
    """真 SQLite 内存库 + 种子数据（只建本用例需要的两张表）。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine, tables=[User.__table__, GradingDailyStat.__table__]
    )
    session = sessionmaker(bind=engine)()
    _seed(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(session):
    users = [
        (TEACHER, "任课教师"),
        (OTHER, "任课教师"),
        (COMBO, "任课教师,班主任"),
        (SCHOOL_ADMIN, "校级管理者"),
        (SYS_ADMIN, "系统管理员"),
    ]
    for uid, roles in users:
        session.add(
            User(id=uid, email=f"{uid}@example.com", password_hash="x",
                 display_name=uid, roles=roles)
        )
    for uid, (up, gr) in SEED_TODAY.items():
        session.add(GradingDailyStat(
            id=f"s-{uid}-today", user_id=uid, folder_safe="f1",
            stat_date=TODAY, upload_count=up, grade_count=gr,
        ))
    for uid, (up, gr) in SEED_PREV.items():
        session.add(GradingDailyStat(
            id=f"s-{uid}-prev", user_id=uid, folder_safe="f1",
            stat_date=PREV_LAST, upload_count=up, grade_count=gr,
        ))
    session.commit()


def _client(db, viewer):
    """走真实路由的 TestClient（注：本机 with 上下文会挂起，故直接 new 出来用）。

    `viewer` = 当前登录账号（注入 get_current_user_id），与 query 参数 user_id 无关。
    """
    app = FastAPI()
    app.include_router(scan_billing.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user_id] = lambda: viewer
    return TestClient(app)


def _get(db, viewer, path, **params):
    resp = _client(db, viewer).get(path, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _prev_month_param():
    return f"{PREV_LAST.year}-{PREV_LAST.month:02d}"


# ══════════════════════════════════════════════════════════
# 1. /consumption
# ══════════════════════════════════════════════════════════


def test_teacher_consumption_without_user_id_only_own(db):
    """任课教师不传 user_id ⇒ 只含自己（改动前：全平台 275/320）。"""
    data = _get(db, TEACHER, "/scan-billing/consumption", days=1)
    assert data["total_upload"] == SEED_TODAY[TEACHER][0]
    assert data["total_grade"] == SEED_TODAY[TEACHER][1]


def test_teacher_consumption_ignores_foreign_user_id(db):
    """★核心安全断言★ 任课教师传 user_id=<别人> ⇒ 结果仍是自己的，不是别人的、也不报错。"""
    data = _get(db, TEACHER, "/scan-billing/consumption", days=1, user_id=OTHER)
    assert data["total_upload"] == SEED_TODAY[TEACHER][0]
    assert data["total_grade"] == SEED_TODAY[TEACHER][1]
    assert data["total_upload"] != SEED_TODAY[OTHER][0]


def test_school_admin_consumption_sees_platform(db):
    """回归闸：校级管理者不传 user_id ⇒ 仍看全平台（与改动前一致）。"""
    data = _get(db, SCHOOL_ADMIN, "/scan-billing/consumption", days=1)
    assert data["total_upload"] == ALL_UPLOAD
    assert data["total_grade"] == ALL_GRADE


def test_system_admin_consumption_sees_platform(db):
    """回归闸：系统管理员不传 user_id ⇒ 仍看全平台。"""
    data = _get(db, SYS_ADMIN, "/scan-billing/consumption", days=1)
    assert data["total_upload"] == ALL_UPLOAD
    assert data["total_grade"] == ALL_GRADE


def test_admin_explicit_user_id_still_honored(db):
    """回归闸：管理员显式传 user_id ⇒ 仍按该 user_id 过滤（这层筛选用法未被收窄）。"""
    data = _get(db, SCHOOL_ADMIN, "/scan-billing/consumption", days=1, user_id=OTHER)
    assert data["total_upload"] == SEED_TODAY[OTHER][0]
    assert data["total_grade"] == SEED_TODAY[OTHER][1]


def test_multi_role_teacher_not_scoped(db):
    """回归闸：任课教师+班主任 ⇒ **不是**「仅任课教师」，行为不变（仍全平台）。"""
    data = _get(db, COMBO, "/scan-billing/consumption", days=1)
    assert data["total_upload"] == ALL_UPLOAD
    assert data["total_grade"] == ALL_GRADE


def test_teacher_consumption_counts_match_admin_querying_that_teacher(db):
    """差分断言：教师自视图 == 管理员显式按该教师过滤的视图（与日期无关，恒成立）。"""
    own = _get(db, TEACHER, "/scan-billing/consumption", days=1)
    by_admin = _get(db, SCHOOL_ADMIN, "/scan-billing/consumption", days=1, user_id=TEACHER)
    assert own["total_upload"] == by_admin["total_upload"]
    assert own["total_grade"] == by_admin["total_grade"]


def test_ghost_user_fail_closed(db):
    """异常态兜底：token 有效但 users 表无此行 ⇒ 按最保守收窄到本人（无数据），不泄露全平台。"""
    data = _get(db, GHOST, "/scan-billing/consumption", days=1)
    assert data["total_upload"] == 0
    assert data["total_grade"] == 0


# ══════════════════════════════════════════════════════════
# 2. /usage-stats
# ══════════════════════════════════════════════════════════


def _usage_stats(db, viewer, **extra):
    return _get(
        db, viewer, "/scan-billing/usage-stats",
        start_date=TODAY.isoformat(), end_date=TODAY.isoformat(), **extra
    )


def test_teacher_usage_stats_without_user_id_only_own(db):
    data = _usage_stats(db, TEACHER)
    assert data["summary"]["total_upload"] == SEED_TODAY[TEACHER][0]
    assert data["summary"]["total_grade"] == SEED_TODAY[TEACHER][1]


def test_teacher_usage_stats_ignores_foreign_user_id(db):
    """★核心安全断言★ user_id=<别人> 仍返回自己的汇总。"""
    data = _usage_stats(db, TEACHER, user_id=OTHER)
    assert data["summary"]["total_upload"] == SEED_TODAY[TEACHER][0]
    assert data["summary"]["total_grade"] == SEED_TODAY[TEACHER][1]


def test_teacher_usage_stats_user_dimension_hides_other_teachers(db):
    """维度=按教师：明细里不得出现其他教师（改动前会列出全体教师用量）。"""
    data = _usage_stats(db, TEACHER, dimension="user")
    assert [row["key"] for row in data["breakdown"]] == [TEACHER]


def test_admin_usage_stats_user_dimension_lists_all(db):
    """回归闸：管理员的「按教师」维度仍列出全体教师。"""
    data = _usage_stats(db, SCHOOL_ADMIN, dimension="user")
    assert {row["key"] for row in data["breakdown"]} == set(SEED_TODAY)
    assert data["summary"]["total_upload"] == ALL_UPLOAD


def test_admin_usage_stats_explicit_user_id_still_honored(db):
    data = _usage_stats(db, SYS_ADMIN, user_id=OTHER)
    assert data["summary"]["total_upload"] == SEED_TODAY[OTHER][0]


# ══════════════════════════════════════════════════════════
# 3. /trends
# ══════════════════════════════════════════════════════════


def _trends(db, viewer, **extra):
    return _get(
        db, viewer, "/scan-billing/trends",
        start_date=TODAY.isoformat(), end_date=TODAY.isoformat(), **extra
    )


def test_teacher_trends_without_user_id_only_own(db):
    data = _trends(db, TEACHER)
    assert data[0]["upload"] == SEED_TODAY[TEACHER][0]
    assert data[0]["grade"] == SEED_TODAY[TEACHER][1]


def test_teacher_trends_ignores_foreign_user_id(db):
    data = _trends(db, TEACHER, user_id=OTHER)
    assert data[0]["upload"] == SEED_TODAY[TEACHER][0]


def test_admin_trends_sees_platform(db):
    """回归闸：管理员的趋势仍是全平台合计。"""
    assert _trends(db, SCHOOL_ADMIN)[0]["upload"] == ALL_UPLOAD


# ══════════════════════════════════════════════════════════
# 4. /breakdown
# ══════════════════════════════════════════════════════════


def test_teacher_breakdown_without_user_id_only_own(db):
    data = _get(db, TEACHER, "/scan-billing/breakdown", days=1)
    assert sum(row["upload"] for row in data) == SEED_TODAY[TEACHER][0]
    assert sum(row["grade"] for row in data) == SEED_TODAY[TEACHER][1]


def test_teacher_breakdown_ignores_foreign_user_id(db):
    data = _get(db, TEACHER, "/scan-billing/breakdown", days=1, user_id=OTHER)
    assert sum(row["upload"] for row in data) == SEED_TODAY[TEACHER][0]


def test_admin_breakdown_sees_platform(db):
    data = _get(db, SCHOOL_ADMIN, "/scan-billing/breakdown", days=1)
    assert sum(row["upload"] for row in data) == ALL_UPLOAD


# ══════════════════════════════════════════════════════════
# 5. /monthly
# ══════════════════════════════════════════════════════════


def test_teacher_monthly_without_user_id_only_own(db):
    data = _get(db, TEACHER, "/scan-billing/monthly", months=1)
    assert len(data) == 1
    assert data[0]["upload"] == SEED_TODAY[TEACHER][0]
    assert data[0]["grade"] == SEED_TODAY[TEACHER][1]
    # active_users 也不再暴露「上个月平台上活跃过几个账号」
    assert data[0]["active_users"] == 1


def test_teacher_monthly_ignores_foreign_user_id(db):
    data = _get(db, TEACHER, "/scan-billing/monthly", months=1, user_id=OTHER)
    assert data[0]["upload"] == SEED_TODAY[TEACHER][0]


def test_admin_monthly_sees_platform(db):
    data = _get(db, SCHOOL_ADMIN, "/scan-billing/monthly", months=1)
    assert data[0]["upload"] == ALL_UPLOAD
    assert data[0]["active_users"] == len(SEED_TODAY)


# ══════════════════════════════════════════════════════════
# 6. /estimate
# ══════════════════════════════════════════════════════════


def test_teacher_estimate_without_user_id_only_own(db):
    data = _get(db, TEACHER, "/scan-billing/estimate")
    assert data["usage"]["upload"] == SEED_TODAY[TEACHER][0]
    assert data["usage"]["grade"] == SEED_TODAY[TEACHER][1]


def test_teacher_estimate_ignores_foreign_user_id(db):
    """★核心安全断言★ 传别人的 user_id ⇒ 账单口径的用量仍是自己的。"""
    data = _get(db, TEACHER, "/scan-billing/estimate", user_id=OTHER)
    assert data["usage"]["upload"] == SEED_TODAY[TEACHER][0]
    assert data["usage"]["grade"] == SEED_TODAY[TEACHER][1]


def test_admin_estimate_sees_platform(db):
    data = _get(db, SCHOOL_ADMIN, "/scan-billing/estimate")
    assert data["usage"]["upload"] == ALL_UPLOAD


# ══════════════════════════════════════════════════════════
# 7. /bill
# ══════════════════════════════════════════════════════════


def test_teacher_bill_without_user_id_only_own(db):
    data = _get(db, TEACHER, "/scan-billing/bill", month=_prev_month_param())
    assert data["usage"]["upload"] == SEED_PREV[TEACHER][0]
    assert data["usage"]["grade"] == SEED_PREV[TEACHER][1]


def test_teacher_bill_ignores_foreign_user_id(db):
    data = _get(
        db, TEACHER, "/scan-billing/bill",
        month=_prev_month_param(), user_id=OTHER,
    )
    assert data["usage"]["upload"] == SEED_PREV[TEACHER][0]


def test_admin_bill_sees_platform(db):
    data = _get(db, SCHOOL_ADMIN, "/scan-billing/bill", month=_prev_month_param())
    assert data["usage"]["upload"] == PREV_ALL_UPLOAD
    assert data["usage"]["grade"] == PREV_ALL_GRADE


def test_admin_bill_explicit_user_id_still_honored(db):
    data = _get(
        db, SYS_ADMIN, "/scan-billing/bill",
        month=_prev_month_param(), user_id=OTHER,
    )
    assert data["usage"]["upload"] == SEED_PREV[OTHER][0]


# ══════════════════════════════════════════════════════════
# 8. /user-ranking（④ 的处置：收窄为「只有自己一人」，不 403）
# ══════════════════════════════════════════════════════════


def test_teacher_user_ranking_returns_self_only(db):
    """任课教师 ⇒ 只返回自己一人（rank=1），⛔ 不返回全体教师排名、⛔ 不报错。"""
    data = _get(db, TEACHER, "/scan-billing/user-ranking", days=1)
    assert len(data) == 1
    assert data[0]["user_id"] == TEACHER
    assert data[0]["rank"] == 1
    assert data[0]["upload"] == SEED_TODAY[TEACHER][0]
    assert data[0]["grade"] == SEED_TODAY[TEACHER][1]


def test_admin_user_ranking_still_lists_everyone(db):
    """回归闸：管理员的教师排名仍是全体教师、按总量降序（行为与改动前一致）。"""
    data = _get(db, SCHOOL_ADMIN, "/scan-billing/user-ranking", days=1)
    assert [row["user_id"] for row in data] == sorted(
        SEED_TODAY, key=lambda u: -(SEED_TODAY[u][0] + SEED_TODAY[u][1])
    )
    assert data[0]["rank"] == 1


def test_multi_role_teacher_user_ranking_still_lists_everyone(db):
    """回归闸：任课教师+班主任 ⇒ 不受收敛约束，排名仍是全体。"""
    data = _get(db, COMBO, "/scan-billing/user-ranking", days=1)
    assert len(data) == len(SEED_TODAY)


# ══════════════════════════════════════════════════════════
# 9. 判据本身（与前端 isTeacherOnlyAccount 同口径）
# ══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "roles,expected",
    [
        ({"任课教师"}, True),
        ({"任课教师", "班主任"}, False),
        ({"班主任"}, False),
        ({"系统管理员"}, False),
        ({"测试账号"}, False),
        (set(), False),
    ],
)
def test_roles_are_teacher_only_matches_frontend(roles, expected):
    assert scan_billing._roles_are_teacher_only(roles) is expected


def test_resolve_scope_user_id_transparent_for_non_teacher(db):
    """非任课教师：显式 user_id 原样透传，None 仍为 None（=全平台）。"""
    assert scan_billing.resolve_scope_user_id(db, SCHOOL_ADMIN, None) is None
    assert scan_billing.resolve_scope_user_id(db, SCHOOL_ADMIN, OTHER) == OTHER


def test_resolve_scope_user_id_forces_self_for_teacher(db):
    """任课教师：无论传什么（含 None）都回落为调用者本人。"""
    assert scan_billing.resolve_scope_user_id(db, TEACHER, None) == TEACHER
    assert scan_billing.resolve_scope_user_id(db, TEACHER, OTHER) == TEACHER


def test_calendar_helper_sanity():
    """守卫：种子用的「上个月最后一天」确实不在本月（/bill 与 /monthly 的窗口才不会串）。"""
    assert PREV_LAST.month != TODAY.month or PREV_LAST.year != TODAY.year
    assert calendar.monthrange(PREV_LAST.year, PREV_LAST.month)[1] == PREV_LAST.day
