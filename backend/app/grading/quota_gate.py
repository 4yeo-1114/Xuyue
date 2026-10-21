# -*- coding: utf-8 -*-
"""0924 需求：批改额度闸门（钱包没钱 402 + 105% 硬停 403，可选同步计面）。

从 `grading/router.py::_quota_gate` 抽出，供各「大模型批改发起」端点复用：

- `quota_gate()`            —— 只拦不扣（上传侧已计面的入口，防双扣）
- `quota_gate(charge_pages=n)` —— 拦 + 扣 n 面（无独立上传侧计面的入口，
  不扣则「已用」不涨、105% 永不到来，文档 2.4「用完及止」失效）

两道闸，按序判定：

1. **钱包闸（402，没钱不能批改）**：无额度的账号，非管理员且可服务余额 ≤ 0 ⇒ 402
   「余额/额度已用完，请充值或续订」。口径 = 用户 2026-09-30 拍板「除了管理员都拦」，
   ⚠️ 比支付设计稿 §8.2「只拦仅任课教师」更宽 —— 豁免面只有平台管理员
   （系统管理员/子系统管理员）。判据复用 `ledger.serviceable_balance_fen`
   （Phase 0 套餐折算恒 0，单一接缝）；充值回调会同时给钱包加钱 + 按档位加面。
   ⚠️ **有额度豁免**（2026-10-08 用户拍板「赠额本来就送给客户用」）：只要
   `GradingQuota.total_pages>0`（已分配赠额 / 已购档位）就直接放行、跳过钱包闸，
   改走面数闸（105%）兜底 —— 白送额度的账号钱包恒 0，若仍查钱包会 402 挡死、
   赠额形同虚设。这类账号批改扣费时余额不足会走 `_post_net_diff` 捕获留痕、
   不阻塞（免费批改到 105% 停），语义正好吻合。
2. **面数闸（403，105% 硬停）**：`quota_service.ensure_user_available`，
   超限（used × 100 >= total × 105）⇒ 403 中文提示。

公共语义：
- ⛔ 只挡「发起新批改」，进度/结果/取消端点永不挂 ⇒ 已在跑的任务不中断
- 身份上下文缺失、查库/判据异常 ⇒ 放行 + 留痕（绝不把故障变成 500 挡教学）
- 手动批改端点不调用本闸（不花模型钱，按 0924 口径不拦）
"""
import logging

from fastapi import HTTPException

from app.grading.user_paths import get_grading_user_id

logger = logging.getLogger(__name__)


def _money_gate(user_id: str) -> None:
    """钱包闸：无额度账号，非管理员且可服务余额 ≤ 0 ⇒ 402。故障放行 + 留痕。

    豁免顺序：管理员 → 有额度（total_pages>0，赠额/已购档位）→ 余额 > 0。
    有额度账号跳过钱包闸、走面数闸（105%），白送额度不被钱包 ¥0 挡死。

    ⛔ 不在 try 内抛 HTTPException（会被 except Exception 吞掉）——
    判定完成后在 finally 关库之后再抛。
    """
    from app.database import SessionLocal
    from app.models.user import User
    from app.utils.school_access import PLATFORM_ADMIN_ROLES, get_user_roles

    db = None
    try:
        db = SessionLocal()
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            # 有效 token 却查不到 users 行属异常态 ⇒ 判据不可得，放行（与额度闸同侧）
            logger.error("钱包闸门：查不到用户，本次放行 user_id=%s", user_id)
            return
        if get_user_roles(user) & PLATFORM_ADMIN_ROLES:
            return  # 管理员豁免（用户口径「除了管理员都拦」）

        # 有额度（赠额/已购档位）⇒ 放行、改走面数闸（105%）。白送额度账号钱包恒 0，
        # 若仍查钱包会 402 挡死、赠额形同虚设（2026-10-08 用户拍板）。
        from app.services import quota_service

        quota = quota_service.get_quota(db, user_id)
        if quota is not None and int(quota.total_pages or 0) > 0:
            return

        from app.services.payment import ledger as ledger_svc

        if ledger_svc.serviceable_balance_fen(db, user_id) > 0:
            return
    except Exception:
        logger.error("钱包闸门判定失败，本次放行（不阻塞批改）", exc_info=True)
        return
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
    raise HTTPException(status_code=402, detail="余额/额度已用完，请充值或续订")


def quota_gate(*, charge_pages: int = 0) -> None:
    from app.services import quota_service

    # ⚠️ 身份上下文由 async 中间件（main.py::grading_user_context_middleware）写入；
    #    取不到 uid 属异常态 ⇒ 放行 + 留痕，⛔ 绝不 500 挡老师批改。
    try:
        uid = get_grading_user_id()
    except Exception:
        logger.error(
            "批改额度闸门：grading 用户上下文未绑定，本次放行（不阻塞批改）", exc_info=True
        )
        return

    # ① 钱包闸：没钱不能批（402；管理员豁免）
    _money_gate(uid)

    # ② 面数闸：105% 硬停（403）
    try:
        quota_service.ensure_user_available(uid)
    except HTTPException:
        raise
    except Exception:
        logger.error("批改额度闸门判定失败，本次放行（不阻塞批改）", exc_info=True)
        return

    # 闸门通过后才计面（403/402 时不扣）。add_usage 内部 pages=max(1, ·)，
    # 所以 charge_pages<=0 必须完全不调用，否则 0 会被当成 1 扣。
    if charge_pages and charge_pages > 0:
        try:
            quota_service.add_usage(uid, int(charge_pages))
        except Exception:
            logger.error("批改额度计面失败（不影响本次批改）", exc_info=True)
