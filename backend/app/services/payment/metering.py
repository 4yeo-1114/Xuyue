# -*- coding: utf-8 -*-
"""口径 B · 用量计量写入（设计稿 §7.1 —— 本批唯一最关键的新增接缝）。

⛔⛔ **禁忌（§7.1 本节最重要的一条）**：本模块**绝不**把写入塞进
   `grading_stats._increment` 的 `try`（`grading_stats.py:161-162` 吞异常）或
   `record_graded_state_change` 的 `try/except: pass`（`:304`/`:324-325`）。
   理由：**计费事件被静默吞掉 = 静默少收钱**，且没有任何错误日志。
⇒ 计量写入**走自己的 session ＋ 自己的异常处理**：失败 `logging.error` 留痕，
   但**不阻塞批改主流程**（不向调用方抛异常）。

两条幂等层次（§4.3）：
  L1 事件层 —— `usage_events.uk_usage_event_uid`（`event_uid` 相同 ⇒ 重复投递被吞掉，不落新行）
  L2 记账层 —— `ledger_entries.uk_ledger_idempotency`（`business_key|net=N`，见 `ledger.apply_net_diff`）
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.usage_event import UsageEvent
from app.services.payment import ledger as ledger_svc
from app.services.payment import pricing

logger = logging.getLogger(__name__)

# 同一 (user, kind, folder, subject) 上允许的净额上限（份）。
# kind='grade' ：「1 份」由 §3.1 定义为一次 0→1 跃迁 ⇒ 同一学生同一文件夹最多同时「已批改 1 次」。
NET_UPPER_BOUND = 1


def make_event_uid(
    user_id: str,
    kind: str,
    folder_safe: str,
    subject_key: str,
    delta: int,
    occurrence: str = "",
) -> str:
    """上游事件的稳定标识（§7.1）。

    设计稿给的字面例子是 `sha1(f"{user_id}|{kind}|{folder_safe}|{subject_key}|{delta_sign}")`
    —— 但那是「形如」的示例，且**它单独用不能同时满足 §9 的两条验收**（见下方 ⚠️）。
    本实现取该指纹 **+ 上游载荷指纹 `occurrence`**：

    ⚠️ 如实申报的偏离与理由：
    - 只用「跃迁指纹」⇒ 「删除→再批改」的第二次 +1 与第一次 +1 **指纹相同** ⇒ 被 L1 吞掉
      ⇒ 净额停在 0 ⇒ **少扣 1 份**。这正是 §3.5「反例 2」明文要避免的行为。
    - 只用「时间戳/随机」⇒ 重试每次产生新 uid ⇒ **重复扣费**（§3.5「反例」）。
    - ⇒ 取载荷指纹：**重试**（同一份批改结果被重复持久化）载荷相同 ⇒ uid 相同 ⇒ 被吞掉（幂等 ✅）；
      **删除后重新批改**（新一次批改的新结果）载荷不同 ⇒ uid 不同 ⇒ 正确二次计费 ✅。
      代价（已登记）：若重批产出与首次**逐字相同**的载荷，会退化为「少扣 1 份」（对老师有利的一侧）。
    """
    sign = "+" if int(delta) > 0 else "-"
    raw = "{}|{}|{}|{}|{}|{}".format(
        str(user_id or "").strip(),
        str(kind or "").strip(),
        str(folder_safe or "").strip(),
        str(subject_key or "").strip(),
        sign,
        str(occurrence or ""),
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def payload_occurrence(payload: Any) -> str:
    """上游载荷的稳定指纹（`sorted` JSON ⇒ 键序无关；不可序列化对象走 `default=str`）。"""
    if payload is None:
        return ""
    try:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        return ""
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _current_net(db: Session, user_id: str, kind: str, folder_safe: str, subject_key: str) -> int:
    return ledger_svc.current_net(db, user_id, kind, folder_safe, subject_key)


def _insert_event(
    db: Session,
    *,
    user_id: str,
    kind: str,
    folder_safe: str,
    subject_key: str,
    delta: int,
    event_uid: str,
    occurred_at: datetime,
) -> Optional[str]:
    """插一条事件；返回事件 id（新建）或 None（被 uk_usage_event_uid 吞掉）。"""
    ev = UsageEvent(
        user_id=user_id,
        kind=kind,
        folder_safe=folder_safe,
        subject_key=subject_key,
        delta=int(delta),
        event_uid=event_uid,
        occurred_at=occurred_at,
    )
    db.add(ev)
    try:
        db.commit()
    except IntegrityError:
        # L1 幂等：同一 event_uid 已存在 ⇒ 视为已处理（不报错、不落新行）
        db.rollback()
        return None
    return ev.id


def emit_usage_event(
    *,
    user_id: str,
    kind: str,
    folder_safe: str,
    subject_key: str,
    delta: int,
    occurrence: str = "",
    occurred_at: Optional[datetime] = None,
    run_ledger: bool = True,
) -> bool:
    """旁路写入一条用量事件；并按 §3.5 触发 net-diff 记账。

    返回 `True` = 落了新事件；`False` = 重复投递被吞 / 被净额边界挡住 / 写入失败（已 logging.error）。
    ⛔ **本函数不抛异常**（调用点位于批改主流程旁路，且⛔ 不得进吞异常区）。
    """
    uid = str(user_id or "").strip()
    subj = str(subject_key or "").strip()
    if not uid or not subj or int(delta) == 0:
        return False

    k = str(kind or "").strip()
    folder = str(folder_safe or "").strip() or "_default"
    occurred = occurred_at or datetime.now(timezone.utc)
    event_id: Optional[str] = None

    # ── 段 1：事件写入（自己的 session ＋ 自己的异常处理）──
    # ⚠️ `SessionLocal()` 本身也必须在 try 内：连不上库同样是「计量写入失败」，
    #    也必须留痕而不是把异常抛回批改主流程（P0-3.e 红实验抓到的真实缺陷）。
    db = None
    try:
        db = SessionLocal()
        # 净额边界（I0）：kind='grade' 的净额恒在 [0, 1]
        net = _current_net(db, uid, k, folder, subj)
        d = int(delta)
        if d > 0 and k == pricing.KIND_GRADE and net >= NET_UPPER_BOUND:
            return False
        if d < 0 and net <= 0:
            return False
        event_id = _insert_event(
            db,
            user_id=uid,
            kind=k,
            folder_safe=folder,
            subject_key=subj,
            delta=d,
            event_uid=make_event_uid(uid, k, folder, subj, d, occurrence),
            occurred_at=occurred,
        )
    except Exception:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        # ⛔ 不阻塞批改主流程，但**必须留痕**（否则 = 静默少收钱）
        logger.error(
            "计费用量事件写入失败：user_id=%s kind=%s folder=%s subject=%s delta=%s",
            uid, k, folder, subj, delta, exc_info=True,
        )
        return False
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    if event_id is None:
        return False

    # ── 段 2：net-diff 记账（独立 session，独立异常处理）──
    if run_ledger and pricing.is_billable(k):
        _post_net_diff(uid, k, folder, subj, event_id)
    return True


def _post_net_diff(user_id: str, kind: str, folder_safe: str, subject_key: str, event_id: str) -> None:
    db = None
    try:
        db = SessionLocal()
        ledger_svc.apply_net_diff(
            db,
            user_id=user_id,
            kind=kind,
            folder_safe=folder_safe,
            subject_key=subject_key,
            usage_event_id=event_id,
        )
    except Exception:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        # 余额不足 / 写库失败：同样留痕但不阻塞批改（§4.1 闸门在前，此处属异常态）
        logger.error(
            "计费 net-diff 记账失败：user_id=%s kind=%s folder=%s subject=%s",
            user_id, kind, folder_safe, subject_key, exc_info=True,
        )
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def emit_usage_events(
    *,
    user_id: str,
    kind: str,
    folder_safe: str,
    subject_key: str,
    count: int = 1,
    delta: int = 1,
    occurrence: str = "",
) -> int:
    """批量投递 count 次跃迁（`count>1` 时按序号加后缀，保证重试稳定）。"""
    n = max(1, int(count or 1))
    ok = 0
    for i in range(n):
        occ = occurrence if n == 1 else f"{occurrence}#{i}"
        if emit_usage_event(
            user_id=user_id, kind=kind, folder_safe=folder_safe,
            subject_key=subject_key, delta=delta, occurrence=occ,
        ):
            ok += 1
    return ok


def emit_folder_removed(user_id: str, folder_safe: str) -> int:
    """§1.3 陷阱 3 / I6：口径 A 的 `remove_folder_stats` **清零**统计行，但账本**不得**被抹掉。

    对策：对「该用户 + 该文件夹下净额为 +1」的每个 (kind, subject) 补投一条 `delta=-1` 冲正事件，
    使净额回到 0 ⇒ net-diff 自动产生反向分录（§3.3 I5），而**历史事件与历史分录一行不动**。
    """
    uid = str(user_id or "").strip()
    folder = str(folder_safe or "").strip() or "_default"
    if not uid:
        return 0
    db = None
    try:
        db = SessionLocal()
        rows = (
            db.query(UsageEvent.kind, UsageEvent.subject_key, func.sum(UsageEvent.delta))
            .filter(UsageEvent.user_id == uid, UsageEvent.folder_safe == folder)
            .group_by(UsageEvent.kind, UsageEvent.subject_key)
            .having(func.sum(UsageEvent.delta) > 0)
            .all()
        )
    except Exception:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        logger.error("读取待冲正用量事件失败：user_id=%s folder=%s", uid, folder, exc_info=True)
        return 0
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    n = 0
    for kind, subject_key, _net in rows:
        if emit_usage_event(
            user_id=uid, kind=str(kind), folder_safe=folder,
            subject_key=str(subject_key), delta=-1, occurrence="folder-removed",
        ):
            n += 1
    return n
