"""
千问 LLM 网关封装（非流式）—— 复用叙阅现有 qwen_settings 配置。

AI 评语生成走本模块。网关不可用/未配 Key → 返回 ok=False，调用方按 ai_failed 兜底，
绝不阻塞报告主流程（A0 §6.7 网关失败场景）。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import requests
from sqlalchemy.orm import Session

from app.services.redline_filter import filter_text
from app.utils.qwen_settings import (
    DEFAULT_QWEN_MODEL,
    QWEN_CHAT_EXTRA_BODY,
    get_llm_config,
)

logger = logging.getLogger(__name__)

COMMENT_TEMPERATURE = 0.7


def generate_comment(db: Session, messages: list[dict], max_tokens: int = 800) -> dict:
    """调用千问生成评语。

    返回: {ok, content, model, tokens_used, cost_cent, error}
      - ok=False 表示网关失败（含未配置 API Key），content 为空，调用方落 ai_failed 兜底。
    """
    base_url, api_key, model = get_llm_config(db)
    if not api_key:
        logger.warning("[portfolio.llm] 未配置文本大模型 API Key，评语生成降级为 ai_failed")
        return {"ok": False, "content": "", "model": model or DEFAULT_QWEN_MODEL,
                "tokens_used": 0, "cost_cent": 0, "error": "LLM_API_KEY 未配置"}

    final_model = (model or DEFAULT_QWEN_MODEL).strip()
    body: dict = {
        "model": final_model,
        "messages": messages,
        "temperature": COMMENT_TEMPERATURE,
        "max_tokens": max_tokens,
        **QWEN_CHAT_EXTRA_BODY,
    }
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[portfolio.llm] 调用千问失败: %s", exc)
        return {"ok": False, "content": "", "model": final_model,
                "tokens_used": 0, "cost_cent": 0, "error": str(exc)}

    if resp.status_code != 200:
        logger.warning("[portfolio.llm] 千问返回非 200: %s %s", resp.status_code, resp.text[:300])
        return {"ok": False, "content": "", "model": final_model,
                "tokens_used": 0, "cost_cent": 0, "error": f"HTTP {resp.status_code}"}

    try:
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        # AI 输出红线词过滤：返回前整段过滤（best-effort，异常不阻断评语生成）
        try:
            content = filter_text(content)
        except Exception:  # noqa: BLE001 - best-effort，过滤器异常不阻断主流程
            logger.warning("[portfolio.llm] 红线过滤失败，放行原文", exc_info=True)
        usage = data.get("usage") or {}
        tokens_used = int(usage.get("total_tokens") or 0)
        return {"ok": True, "content": content, "model": final_model,
                "tokens_used": tokens_used,
                "cost_cent": _estimate_cost(final_model, tokens_used), "error": ""}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[portfolio.llm] 解析千问响应失败: %s", exc)
        return {"ok": False, "content": "", "model": final_model,
                "tokens_used": 0, "cost_cent": 0, "error": str(exc)}


def _estimate_cost(model: str, tokens: int) -> int:
    """估算成本（分）。qwen-plus 约 0.004 元/千 token → 0.4 分/千 token。"""
    if not tokens:
        return 0
    return max(0, int(round(tokens / 1000.0 * 0.4)))
