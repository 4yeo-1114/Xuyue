# -*- coding: utf-8 -*-
"""口径 B · 账本核心服务（账户 / 流水 / 幂等 / 净额记账 / 闸门）。

设计依据：docs/payment/payment-design.md §3（账本模型与不变量 I1–I6）、§3.4（行锁）、
§3.5（net-diff 记账法）、§4.1（前置闸门）、§8.1（账户惰性创建）、§8.2（适用人群判据）。

不变量落点：
  I1 同一笔用量不能扣两次      → `ledger_entries.uk_ledger_idempotency` 唯一索引（DB 层）
  I2 余额不可为负              → `post_entry` 在同一事务内 `SELECT ... FOR UPDATE` 后校验
  I3 每笔变动可追溯、余额可复算 → 每行落 `balance_after_fen`；`verify_invariant_e1()` 可复算
  I4 流水只增不改              → 本模块**只有 INSERT**，无任何 UPDATE/DELETE
  I5 冲正 = 反向分录           → `entry_type='consume'` + `amount_fen > 0`，`description='冲正：…'`
  I6 口径 A 用量变动不直接改账本 → 本模块只被 `metering.py`（读 `usage_events`）调用

⚠️ 本模块**永不 import 任何通道 SDK**（§2.3）：资金入口隔离在单一方法后面。
   两个资金入口：
     · `grant_manual(...)` —— 人工入账（§9：后台补开 / 对公转账人工核销），完全绕开通道；
     · `apply_payment_confirmed(...)` —— §2.3 的**唯一**通道侧入口
       （Phase 2 起由 `routers/payment.py` 的回调路由调用；通道层⛔ 不许自己写账本）。
"""
from __future__ import annotations

import datetime
import hashlib
import logging
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.ledger_entry import LedgerEntry
from app.models.payment_account import PaymentAccount
from app.models.payment_order import PaymentOrder
from app.models.usage_event import UsageEvent

logger = logging.getLogger(__name__)

ENTRY_RECHARGE = "recharge"
ENTRY_CONSUME = "consume"
ENTRY_REFUND = "refund"
ENTRY_GRANT = "grant"
ENTRY_EXPIRE = "expire"
ENTRY_ADJUST = "adjust"

STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"

# 订单状态（`payment_orders.status`，§7.2 P2-1）
ORDER_PENDING = "pending"
ORDER_PAID = "paid"
ORDER_FAILED = "failed"
ORDER_CANCELLED = "cancelled"
ORDER_REFUNDED = "refunded"

# 「独立老师」所绑定的既有角色名（与前端 constants/systemRoles.ts 同源，⛔ 不新增角色）
TEACHER_ROLE = "任课教师"

# §7.3：余额/额度不足用 402（闸门拒绝）
HTTP_402_INSUFFICIENT = 402


class InsufficientBalanceError(Exception):
    """I2：余额不足以完成本次扣减（写路径拒绝，绝不扣成负数）。"""


class AccountSuspendedError(Exception):
    """账户被风控冻结，禁止任何新的扣减。"""


class OrderNotFoundError(Exception):
    """订单不存在 ⇒ 路由映射为 404。"""

    http_status = 404


class OrderStateError(Exception):
    """订单状态不允许本次入账（已退款/已取消）⇒ 路由映射为 409。"""

    http_status = 409


# ────────────────────────── 账户 ──────────────────────────

def get_or_create_account(db: Session, user_id: str) -> PaymentAccount:
    """§8.1 账户惰性创建：首个用量事件 / 首个充值 / 首个订阅时创建。

    ⛔ 不做一次性 backfill 脚本（独立老师全是零用量新账号，没有数据要填）。
    """
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("user_id 不能为空")
    acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == uid).first()
    if acct is not None:
        return acct
    acct = PaymentAccount(user_id=uid, balance_fen=0, total_recharged_fen=0,
                          total_consumed_fen=0, status=STATUS_ACTIVE)
    db.add(acct)
    try:
        db.commit()
    except IntegrityError:
        # 并发下 uk_payment_account_user 冲突 ⇒ 取既有行（幂等）
        db.rollback()
        acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == uid).first()
        if acct is None:
            raise
        return acct
    db.refresh(acct)
    return acct


def lock_account(db: Session, user_id: str) -> PaymentAccount:
    """§3.4：`SELECT ... FOR UPDATE` 锁账户行（MySQL InnoDB 行锁）。

    锁粒度 = 单个老师的账户行 ⇒ 同一老师的并发扣费被序列化，
    「读余额 → 校验非负 → 写流水 → 更新余额」无需重试逻辑。
    ⚠️ 行锁只解决「同一老师并发」；「同一事件重复投递」由 I1 的唯一索引兜底（缺一不可）。
    ⚠️ SQLite 方言下 `FOR UPDATE` 是空操作（测试用），生产走 MySQL 时是真行锁。
    """
    get_or_create_account(db, user_id)
    return (
        db.query(PaymentAccount)
        .filter(PaymentAccount.user_id == str(user_id).strip())
        .with_for_update()
        .one()
    )


# ────────────────────────── 记账 ──────────────────────────

def post_entry(
    db: Session,
    *,
    user_id: str,
    entry_type: str,
    amount_fen: int,
    idempotency_key: str,
    description: Optional[str] = None,
    usage_event_id: Optional[str] = None,
    order_id: Optional[str] = None,
    operator_id: Optional[str] = None,
    allow_suspended: bool = False,
) -> tuple[LedgerEntry, bool]:
    """落一条分录（单事务 + 行锁）。

    返回 `(分录, 是否新建)`。**同幂等键重复调用不报错**，返回既有分录
    （§3.4：捕获 `IntegrityError on uk_ledger_idempotency` ⇒ 视为已处理，幂等语义）。

    raise `InsufficientBalanceError`（I2）/ `AccountSuspendedError`。
    """
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("idempotency_key 不能为空")
    if len(key) > 191:
        raise ValueError("idempotency_key 超长（VARCHAR(191)）")

    amount = int(amount_fen)

    # 先查既有键（快路径；真正的兜底是下面 insert 时的唯一索引冲突）
    existing = db.query(LedgerEntry).filter(LedgerEntry.idempotency_key == key).first()
    if existing is not None:
        return existing, False

    acct = lock_account(db, user_id)
    if acct.status == STATUS_SUSPENDED and not allow_suspended:
        db.rollback()
        raise AccountSuspendedError("账户已被冻结，无法记账")
    if amount < 0 and int(acct.balance_fen or 0) + amount < 0:
        db.rollback()
        raise InsufficientBalanceError(
            f"余额不足：当前 {int(acct.balance_fen or 0)} 分，本次需扣 {-amount} 分"
        )

    balance_after = int(acct.balance_fen or 0) + amount
    entry = LedgerEntry(
        account_id=acct.id,
        entry_type=entry_type,
        amount_fen=amount,
        balance_after_fen=balance_after,
        idempotency_key=key,
        usage_event_id=usage_event_id,
        order_id=order_id,
        operator_id=operator_id,
        description=description,
    )
    db.add(entry)
    acct.balance_fen = balance_after
    if amount > 0 and entry_type in (ENTRY_RECHARGE, ENTRY_GRANT):
        acct.total_recharged_fen = int(acct.total_recharged_fen or 0) + amount
    if amount < 0:
        acct.total_consumed_fen = int(acct.total_consumed_fen or 0) + (-amount)

    try:
        db.commit()
    except IntegrityError:
        # I1 兜底：唯一键冲突 ⇒ 已处理，返回既有分录（不抛错）
        db.rollback()
        existing = db.query(LedgerEntry).filter(LedgerEntry.idempotency_key == key).first()
        if existing is None:
            raise
        return existing, False
    db.refresh(entry)
    return entry, True


def grant_manual(
    db: Session,
    *,
    user_id: str,
    amount_fen: int,
    operator_id: str,
    description: str = "",
    idempotency_key: Optional[str] = None,
) -> tuple[LedgerEntry, bool]:
    """人工入账（§9 末尾：Phase 0/1 的资金入口用「手工插入一笔 grant 分录」验收）。

    `entry_type='grant'` + `operator_id` ⇒ 完全绕开支付通道（Phase 2 才接 `apply_payment_confirmed`）。
    幂等键默认 `manual-grant|{user}|{amount}|{operator}|{description}`，
    人工重复点击「开通」不会重复入账。
    """
    amount = int(amount_fen)
    if amount == 0:
        raise ValueError("入账金额不能为 0")
    key = idempotency_key or (
        "manual-grant|{}|{}|{}|{}".format(
            str(user_id).strip(), amount, str(operator_id or "").strip(), str(description or "")
        )
    )
    return post_entry(
        db,
        user_id=user_id,
        entry_type=ENTRY_GRANT if amount > 0 else ENTRY_ADJUST,
        amount_fen=amount,
        idempotency_key=key,
        description=description or "人工入账",
        operator_id=operator_id,
        allow_suspended=True,
    )


# ────────────────────────── 通道确认入账（§2.3 · 账本对通道的唯一依赖）──────────────────────────

def payment_confirm_key(order_id: str) -> str:
    """回调/充值入账的幂等键：**只由我方订单 id 决定**。

    ⛔ **不得**掺入时间戳 / 随机数 / 通道交易号（§3.5「反例」逐字：掺入即等于每次重试都扣一次）。
    ⛔ **不得**改成 `(user, …)` 之类会随业务变化的组合 —— 一笔订单只能充值一次。
    ⇒ 本函数的**确定性**就是 I1 的判据本身，有回归用例钉住
      （`tests/test_payment_p2.py`：把本函数换成非确定版本 ⇒ 「同一回调投两次只有 1 条分录」立刻变红）。
    """
    return "pay-confirm|{}".format(str(order_id or "").strip())


def apply_payment_confirmed(
    db: Session,
    *,
    order_id: str,
    channel_trade_no: str,
    paid_amount_fen: int,
    paid_at: Optional[datetime.datetime] = None,
) -> tuple[LedgerEntry, bool]:
    """§2.3：账本侧**唯一**的资金入口 —— 「订单 X 已被通道确认收款」。

    由通道 adapter 的回调解析器（`routers/payment.py`）或人工核销入口调用。
    ⛔ 本模块**永不 import 任何通道 SDK**；通道侧也**永不**直接写 `ledger_entries`（§2.3 边界）。

    **幂等**：幂等键 = `payment_confirm_key(order_id)`（只由订单决定）⇒ 同一订单重复确认
    只会落 1 条分录，第二次返回既有分录且 `created=False`（I1，最后由
    `ledger_entries.uk_ledger_idempotency` 唯一索引兜底，⛔ 不只靠应用层 `if`）。

    **金额**：§6.3 D3「以**通道实收**入账」⇒ 按 `paid_amount_fen` 入账；
    与订单 `amount_fen` 不符时**记 error 留痕**（需人工核查），但不阻断入账。

    raise `OrderNotFoundError`（404）/ `OrderStateError`（409）。
    """
    oid = str(order_id or "").strip()
    if not oid:
        raise ValueError("order_id 不能为空")

    order = db.query(PaymentOrder).filter(PaymentOrder.id == oid).first()
    if order is None:
        raise OrderNotFoundError(f"订单不存在：{oid}")
    if order.status == ORDER_REFUNDED:
        raise OrderStateError(f"订单 {oid} 已退款，不能再确认收款")
    if order.status == ORDER_CANCELLED:
        raise OrderStateError(f"订单 {oid} 已取消，不能确认收款")

    amount = int(paid_amount_fen)
    if amount <= 0:
        raise ValueError(f"通道实收金额必须为正，实得 {amount}")

    expected = int(order.amount_fen or 0)
    if amount != expected:
        # ⛔ 留痕，不静默：金额不符是收错钱/伪造/优惠三类问题的共同表征，必须可查。
        logger.error(
            "支付确认金额与订单不符（按通道实收入账，需人工核查）：order_id=%s 订单=%s 实收=%s "
            "channel=%s trade_no=%s",
            oid, expected, amount, order.channel, channel_trade_no,
        )

    if order.status != ORDER_PAID:
        if order.status != ORDER_PENDING:
            logger.warning("订单 %s 处于非 pending 状态（%s）却收到收款确认，按已收款处理", oid, order.status)
        order.status = ORDER_PAID
        order.paid_amount_fen = amount
        order.paid_at = paid_at or datetime.datetime.now(datetime.timezone.utc)
        if str(channel_trade_no or "").strip():
            order.channel_trade_no = str(channel_trade_no).strip()

    # ⚠️ 上面订单字段的修改与下面这笔分录**同一个 session、同一次 commit** ⇒ 原子
    #    （`post_entry` 末尾 `db.commit()` 会把脏订单一起 flush）。
    #    唯一索引冲突时 `post_entry` 内部 `db.rollback()` 会把订单改动一并回滚 ——
    #    那种情形说明「首投已成功写库」，订单此刻已经是 paid，无需再改。
    entry, created = post_entry(
        db,
        user_id=order.user_id,
        entry_type=ENTRY_RECHARGE,
        amount_fen=amount,
        idempotency_key=payment_confirm_key(oid),
        description="{} 收款确认（通道交易号 {}）".format(order.channel, channel_trade_no or "-"),
        order_id=oid,
    )
    return entry, created


# ────────────────────────── net-diff 记账（§3.5）──────────────────────────

def business_key(user_id: str, kind: str, folder_safe: str, subject_key: str) -> str:
    """§3.5 的 `business_key = (user_id, kind, folder_safe, subject_key)`。"""
    return "{}|{}|{}|{}".format(
        str(user_id or "").strip(),
        str(kind or "").strip(),
        str(folder_safe or "").strip(),
        str(subject_key or "").strip(),
    )


def business_digest(user_id: str, kind: str, folder_safe: str, subject_key: str) -> str:
    """`business_key` 的 sha1 指纹（40 hex）。

    ⚠️ 偏离设计稿 §3.5 的**字面**写法（`f"{business_key}|net=N"`），理由是长度：
    `folder_safe`(255) + `subject_key`(255) 使 business_key 最长可达 ~554 字符，
    而 `ledger_entries.idempotency_key` 是 `VARCHAR(191)`（§3.2 表 3，为 utf8mb4 唯一索引键长留余量）。
    取指纹**不改变语义**：同一 business_key ⇒ 同一指纹，不同 business_key ⇒ 不同指纹（碰撞概率可忽略）。
    """
    return hashlib.sha1(business_key(user_id, kind, folder_safe, subject_key).encode("utf-8")).hexdigest()


def current_net(db: Session, user_id: str, kind: str, folder_safe: str, subject_key: str) -> int:
    """`net_now = SUM(delta)`（§3.5 第 2 步）。"""
    total = (
        db.query(func.coalesce(func.sum(UsageEvent.delta), 0))
        .filter(
            UsageEvent.user_id == str(user_id or "").strip(),
            UsageEvent.kind == str(kind or "").strip(),
            UsageEvent.folder_safe == str(folder_safe or "").strip(),
            UsageEvent.subject_key == str(subject_key or "").strip(),
        )
        .scalar()
    )
    return int(total or 0)


def apply_net_diff(
    db: Session,
    *,
    user_id: str,
    kind: str,
    folder_safe: str,
    subject_key: str,
    unit_price_fen_: Optional[int] = None,
    usage_event_id: Optional[str] = None,
) -> Optional[LedgerEntry]:
    """§3.5 net-diff 记账：只在**净额发生变化**时产生分录。

    分录键 = `"{business_digest}|net={net_now}|r={已结清次数}"`。

    ⚠️ 与 §3.5 字面式的**唯一**差异是末尾的 `|r=N`（已结清次数）。理由（如实申报）：
    设计稿 §3.5 第 4 步声称「再批改 ⇒ 净额 1 ⇒ 键 `…|net=1` 与第一次不同」，
    但按它自己给出的字面式 `f"{business_key}|net={net_now}"`，**两次 `net=1` 的键完全相同**
    ⇒ 第三次跃迁会被幂等吞掉 ⇒ 与 §9 P0-4 的验收「批改→删除→再批改」直接矛盾。
    加 `|r=N` 后两侧同时成立：**同一次跃迁重复投递**（净额不变 ⇒ 差额 0 ⇒ 压根不产生分录）
    仍然幂等；**删除后再批改**（净额回到 1、但已结清次数已变）产生新键 ⇒ 正确二次扣费。
    `r` 在**账户行锁内**读取，并发下不会算出同一个 `r`。
    """
    from app.services.payment import pricing

    price = pricing.unit_price_fen(kind) if unit_price_fen_ is None else int(unit_price_fen_)
    if price <= 0:
        return None

    digest = business_digest(user_id, kind, folder_safe, subject_key)

    # ⚠️ 先取行锁，再算净额与已结清次数：三者必须在同一序列化区间内（§3.4 L3）
    lock_account(db, user_id)

    net_now = current_net(db, user_id, kind, folder_safe, subject_key)
    rows = (
        db.query(LedgerEntry).filter(LedgerEntry.idempotency_key.like(f"{digest}|net=%")).all()
    )
    # 已结清份数 = -SUM(amount_fen) / 单价（单价在 Phase 0 是常数 ⇒ 可精确整除）
    sum_amount = sum(int(r.amount_fen or 0) for r in rows)
    billed_qty = (-sum_amount) // price

    delta_qty = net_now - billed_qty
    if delta_qty == 0:
        db.rollback()
        return None

    key = f"{digest}|net={net_now}|r={len(rows)}"
    amount_fen = -delta_qty * price
    desc = (
        f"冲正：{kind} 净额 {billed_qty} → {net_now}（{folder_safe} / {subject_key}）"
        if amount_fen > 0
        else f"{kind} 净额 {billed_qty} → {net_now}（{folder_safe} / {subject_key}）"
    )

    try:
        entry, created = post_entry(
            db,
            user_id=user_id,
            entry_type=ENTRY_CONSUME,
            amount_fen=amount_fen,
            idempotency_key=key,
            description=desc,
            usage_event_id=usage_event_id,
        )
    except InsufficientBalanceError:
        db.rollback()
        raise
    return entry if created else entry


def has_unsettled(db: Session, user_id: str) -> bool:
    """是否还有「已计用量、未结清（或已冲正）」的分录 —— 供账单投影用。"""
    return (
        db.query(func.count(LedgerEntry.id))
        .filter(LedgerEntry.account_id.in_(
            db.query(PaymentAccount.id).filter(PaymentAccount.user_id == str(user_id).strip())
        ))
        .scalar()
        or 0
    ) > 0


# ────────────────────────── 对账（§6.2 E1）──────────────────────────

def verify_invariant_e1(db: Session, user_id: str) -> dict[str, Any]:
    """E1（内部自洽）：`SUM(ledger_entries.amount_fen) == payment_accounts.balance_fen`，逐账户。

    §6.4：对账 = 一条只读查询 + 可复算的读数，⛔ 不新建对账脚本/常驻服务。
    """
    acct = db.query(PaymentAccount).filter(PaymentAccount.user_id == str(user_id).strip()).first()
    if acct is None:
        return {"user_id": user_id, "ok": True, "balance_fen": 0, "sum_amount_fen": 0,
                "latest_balance_after_fen": None, "entry_count": 0}
    sum_amount = int(
        db.query(func.coalesce(func.sum(LedgerEntry.amount_fen), 0))
        .filter(LedgerEntry.account_id == acct.id)
        .scalar()
        or 0
    )
    latest = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.account_id == acct.id)
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .first()
    )
    count = int(
        db.query(func.count(LedgerEntry.id)).filter(LedgerEntry.account_id == acct.id).scalar() or 0
    )
    latest_after = int(latest.balance_after_fen) if latest is not None else 0
    ok = sum_amount == int(acct.balance_fen or 0) and latest_after == int(acct.balance_fen or 0)
    return {
        "user_id": user_id,
        "ok": ok,
        "balance_fen": int(acct.balance_fen or 0),
        "sum_amount_fen": sum_amount,
        "latest_balance_after_fen": latest_after,
        "entry_count": count,
    }


# ────────────────────────── 闸门（§4.1 / §8.2）──────────────────────────

def _roles_of(db: Session, user_id: str) -> set[str]:
    from app.models.user import User
    from app.utils.school_access import get_user_roles

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return set()
    return get_user_roles(user)


def is_teacher_only_account(db: Session, user_id: str) -> bool:
    """是否「仅任课教师」账号（= 口径 B 适用人群，§8.2）。

    ✅ **复用** `routers/scan_billing.py` 的既有同口径实现，⛔ 不抄第三份
    （§8.2 明文：与前端 `constants/systemRoles.ts` 的 `isTeacherOnlyAccount` 同源）。
    """
    from app.routers.scan_billing import _roles_are_teacher_only

    return _roles_are_teacher_only(_roles_of(db, user_id))


def serviceable_balance_fen(db: Session, user_id: str) -> int:
    """可服务余额 = 钱包余额 + 套餐剩余额度折算值（§4.1）。

    ⚠️ Phase 0 **套餐部分恒为 0**：`subscriptions` 只建表，抵扣顺序/额度折算留 Phase 1
    （本批不做，见 brief「本批不做」）。此处留单一接缝，Phase 1 只需改这一个函数。
    """
    acct = get_or_create_account(db, user_id)
    return int(acct.balance_fen or 0) + _subscription_quota_value_fen(db, user_id)


def _subscription_quota_value_fen(db: Session, user_id: str) -> int:
    """套餐剩余额度的折算值。Phase 0：恒 0（Phase 1 在此实现抵扣顺序 §5.3）。"""
    return 0


def grading_gate_denied(db: Session, user_id: str) -> Optional[str]:
    """批改前置闸门（§4.1）：返回拒绝原因（中文），或 None 表示放行。

    - ⛔ **只挡「发起新批改」**，绝不中途打断已在跑的批改（判据由调用点位置保证：
      闸门只挂在「发起」端点上，不挂在进度/结果端点上）。
    - ⛔ **只对「仅任课教师」账号生效**（§8.2：校内老师先不纳入口径 B）⇒
      其他角色的行为与改动前**逐字一致**。
    """
    try:
        if not is_teacher_only_account(db, user_id):
            return None
        if serviceable_balance_fen(db, user_id) > 0:
            return None
    except Exception:
        # 闸门自身故障时放行（可用性优先；⛔ 不因闸门故障阻断教学），但必须留痕
        logger.error("支付闸门判定失败，已放行本次批改：user_id=%s", user_id, exc_info=True)
        return None
    return "余额/额度已用完，请充值或续订"


def assert_grading_allowed(db: Session, user_id: str) -> None:
    """闸门拒绝 ⇒ `HTTPException(402)`（§7.3：402 = 余额/额度不足）。"""
    reason = grading_gate_denied(db, user_id)
    if reason:
        raise HTTPException(status_code=HTTP_402_INSUFFICIENT, detail=reason)
