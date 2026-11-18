# -*- coding: utf-8 -*-
"""0924 需求：批改额度闸门（105% 硬停 403，可选同步计面）。

从 `grading/router.py::_quota_gate` 抽出，供各「大模型批改发起」端点复用：

- `quota_gate()`            —— 只拦不扣（上传侧已计面的入口，防双扣）
- `quota_gate(charge_pages=n)` —— 拦 + 扣 n 面（无独立上传侧计面的入口，
  不扣则「已用」不涨、105% 永不到来，文档 2.4「用完及止」失效）

闸门（20261111 起只剩一道；钱包闸/扣费随「余额/充值/支付整体移除」一并删掉）：

1. **面数闸（403，105% 硬停）**：`quota_service.ensure_user_available`，
   超限（used × 100 >= total × 105）⇒ 403 中文提示。total<=0 视为无限额（is_locked 口径）。

公共语义：
- ⛔ 只挡「发起新批改」，进度/结果/取消端点永不挂 ⇒ 已在跑的任务不中断
- 身份上下文缺失、查库/判据异常 ⇒ 放行 + 留痕（绝不把故障变成 500 挡教学）
- 手动批改端点不调用本闸（不花模型钱，按 0924 口径不拦）
"""
import logging
import os

from fastapi import HTTPException

from app.grading.user_paths import get_grading_user_id

logger = logging.getLogger(__name__)


def _gates_disabled() -> bool:
    """本地安装包开关（20261110 用户拍板「安装包不需要设置免费额度」）：
    1/true/yes/on = 闸门全关（不拦、不计面）。环境变量优先，.env 走 config.settings。
    生产不配置 ⇒ 闸门照旧生效。"""
    raw = os.environ.get("QUOTA_GATES_DISABLED", "")
    if not str(raw).strip():
        try:
            from app.config import settings

            raw = getattr(settings, "QUOTA_GATES_DISABLED", "") or ""
        except Exception:
            raw = ""
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def quota_gate(*, charge_pages: int = 0) -> None:
    if _gates_disabled():
        # 本地安装包：不设免费额度、不拦不扣（钱在用户自己的百度/阿里云账户里）
        return
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

    # 面数闸：105% 硬停（403）
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
