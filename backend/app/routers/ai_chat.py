# -*- coding: utf-8 -*-
"""AI 助教：千问 qwen3.7-plus + Schema 驱动 SQL 查询 + SSE 流式输出。"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterator, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.models.ai_conversation import AiConversation, AiConversationMessage
from app.services.ai_chat_access import looks_like_concrete_data_request, looks_like_data_question, looks_like_grading_exam_stats_question
from app.services.ai_chat_privacy import (
    build_privacy_refusal_messages,
    looks_like_user_account_privacy_question,
)
from app.services.ai_chat_auto_tools import run_auto_tool_calls
from app.services.ai_chat_feature_knowledge import build_tutorial_system_prompt
from app.services.redline_filter import RedlineFilter
from app.services.ai_chat_guard import format_prefetch_block
from app.services.ai_chat_intent_queries import build_intent_sql_hint
from app.services.ai_chat_prompt import build_system_prompt, get_ai_chat_tools
from app.services.ai_chat_tutorial_semantics import looks_like_goal_or_howto_question
from app.services.ai_chat_tutorials import (
    _NAV_ID_TO_LABEL,
    looks_like_tutorial_question,
)
from app.services.ai_chat_tools import execute_ai_chat_tool, parse_tool_arguments
from app.services.ai_policy import require_ai_access
from app.utils.qwen_settings import DEFAULT_QWEN_MODEL, QWEN_CHAT_EXTRA_BODY, get_llm_base_url, get_llm_config

router = APIRouter(
    prefix="/ai-chat",
    tags=["ai_chat"],
    dependencies=[Depends(bind_grading_user_context)],
)

AI_CHAT_MODEL = DEFAULT_QWEN_MODEL
MAX_TOOL_ROUNDS = 5

DATA_ANSWER_TEMPERATURE = 0.35


class ChatMessage(BaseModel):
    role: str
    content: str


class AiChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    currentModule: Optional[str] = None


def _last_user_message(body: AiChatRequest) -> str:
    for msg in reversed(body.messages):
        if msg.role == "user" and (msg.content or "").strip():
            return msg.content.strip()
    return ""


# ── AI 对话落库（G4-B，P1 阶段 · 旁路写入，失败不阻断对话）──────────────────


def _title_from_body(body: AiChatRequest) -> str:
    """标题取第一条 user 消息（截断 ≤50 字符），无则用默认标题。"""
    for msg in body.messages:
        if msg.role == "user" and (msg.content or "").strip():
            title = msg.content.strip().replace("\n", " ").replace("\r", " ")
            if len(title) > 50:
                return title[:49] + "…"
            return title
    return "AI 对话"


def _persist_conversation_start(
    db: Session,
    user_id: str,
    body: AiChatRequest,
) -> Optional[AiConversation]:
    """请求开始时落库：新建会话 + 逐条落 user/assistant 消息（含 seq）。

    旁路写入：任何 DB 异常都 rollback 并返回 None，绝不让落库错误中断对话流。
    """
    try:
        conv = AiConversation(
            user_id=user_id,
            title=_title_from_body(body),
            summary=None,
            context_snapshot={"currentModule": body.currentModule} if body.currentModule else None,
            status="active",
        )
        db.add(conv)
        db.flush()  # 拿到 conv.id
        seq = 0
        for msg in body.messages:
            if msg.role not in ("user", "assistant"):
                continue
            db.add(
                AiConversationMessage(
                    conversation_id=conv.id,
                    role=msg.role,
                    content=msg.content or "",
                    seq=seq,
                )
            )
            seq += 1
        conv.message_count = seq
        db.commit()
        return conv
    except Exception:  # noqa: BLE001 - 落库是旁路，DB 错误不阻断对话
        db.rollback()
        return None


def _flush_assistant_message(
    db: Session,
    conv: AiConversation,
    assistant_content: str,
    seq: int,
) -> None:
    """SSE 结束后把本次流式生成的 assistant 内容追加落库并更新会话统计。

    旁路写入：失败仅 rollback，不抛异常（不阻断流式响应收尾）。
    """
    try:
        if not assistant_content:
            return
        db.add(
            AiConversationMessage(
                conversation_id=conv.id,
                role="assistant",
                content=assistant_content,
                seq=seq,
                model=AI_CHAT_MODEL,
            )
        )
        conv.message_count = (conv.message_count or 0) + 1
        db.commit()
    except Exception:  # noqa: BLE001 - 旁路写入
        db.rollback()


def _persist_callbacks(
    db: Session,
    conv: Optional[AiConversation],
    seq: int,
) -> tuple[Optional[Callable[[str], None]], Optional[Callable[[], None]]]:
    """构造流式观察回调：on_content 累积内容块，on_done 收尾落库。

    会话创建失败（conv is None）时返回 (None, None)，流式逻辑原样走。
    """
    if conv is None:
        return None, None
    chunks: list[str] = []

    def on_content(content: str) -> None:
        chunks.append(content)

    def on_done() -> None:
        _flush_assistant_message(db, conv, "".join(chunks), seq)

    return on_content, on_done


def _module_hint(current_module: Optional[str]) -> str:
    if not current_module:
        return ""
    label = _NAV_ID_TO_LABEL.get(current_module, current_module)
    return f"\n\n用户当前正在使用「{label}」模块。"


def _is_feature_usage_question(text: str) -> bool:
    if looks_like_concrete_data_request(text):
        return False
    if looks_like_grading_exam_stats_question(text):
        return False
    return looks_like_tutorial_question(text) or looks_like_goal_or_howto_question(text)


def _sse_content_chunk(content: str) -> str:
    payload = json.dumps({"choices": [{"delta": {"content": content}}]}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


def _call_qwen(
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: Optional[list[dict[str, Any]]] = None,
    stream: bool = False,
    timeout: int = 120,
    temperature: float = 0.1,
) -> requests.Response:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        **QWEN_CHAT_EXTRA_BODY,
    }
    if tools is not None:
        payload["tools"] = tools
    if stream:
        payload["stream"] = True
    return requests.post(
        f"{get_llm_base_url()}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=timeout,
        stream=stream,
    )


def _parse_qwen_error(response: requests.Response, body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if body.get("message"):
            return str(body["message"])
    return response.text[:200] or f"HTTP {response.status_code}"


def _iter_qwen_sse(
    response: requests.Response,
    *,
    on_content: Optional[Callable[[str], None]] = None,
) -> Iterator[str]:
    # AI 输出红线词过滤：单实例跨迭代器生命周期复用（feed 逐段 + 结尾 flush），
    # 与 C 端 ai_tutor 流式接入模式对齐。best-effort：过滤器异常不阻断主流程。
    redline = RedlineFilter()
    done = False
    for raw in response.iter_lines(decode_unicode=True):
        if not raw:
            continue
        line = raw.strip()
        if line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            done = True
            break
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        content = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
        if content:
            try:
                fragment = redline.feed(content)
            except Exception:  # noqa: BLE001 - best-effort，过滤器异常不阻断流式
                fragment = content
            if fragment:
                if on_content is not None:
                    on_content(fragment)
                yield _sse_content_chunk(fragment)
    # 流结束：释放缓冲残留（在 [DONE] 之前发出，保持 SSE 事件顺序正确）
    try:
        tail = redline.flush()
    except Exception:  # noqa: BLE001 - best-effort
        tail = ""
    if tail:
        if on_content is not None:
            on_content(tail)
        yield _sse_content_chunk(tail)
    if done:
        yield _sse_done()


def _run_tool_rounds(
    db: Session,
    user_id: str,
    api_key: str,
    model: str,
    conversation: list[dict[str, Any]],
    first_choice: dict[str, Any],
) -> list[dict[str, Any]]:
    current_choice = first_choice
    for round_idx in range(MAX_TOOL_ROUNDS):
        tool_calls = (current_choice.get("message") or {}).get("tool_calls") or []
        if not tool_calls:
            break

        tool_results: list[dict[str, Any]] = []
        for tc in tool_calls:
            fn = tc.get("function") or {}
            tool_name = fn.get("name") or ""
            args = parse_tool_arguments(fn.get("arguments"))
            result = execute_ai_chat_tool(db, tool_name, args, user_id)
            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

        conversation = [
            *conversation,
            current_choice.get("message") or {},
            *tool_results,
        ]

        if round_idx >= MAX_TOOL_ROUNDS - 1:
            break

        next_resp = _call_qwen(api_key, model, conversation, tools=get_ai_chat_tools(db, user_id), stream=False)
        try:
            next_body = next_resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"千问模型返回异常: {e}")
        if next_resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"千问模型返回错误: {_parse_qwen_error(next_resp, next_body)}")

        current_choice = (next_body.get("choices") or [{}])[0]
        next_tool_calls = (current_choice.get("message") or {}).get("tool_calls") or []
        if not next_tool_calls:
            content = (current_choice.get("message") or {}).get("content") or ""
            if content:
                return [*conversation, {"role": "assistant", "content": content}]
            break

    return conversation


def _stream_from_messages(
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.1,
    on_content: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[], None]] = None,
) -> StreamingResponse:
    """流式生成 + 可选落库观察回调（G4-B 接线，不改流式本体）。

    on_content：每个内容块到达时回调（累积 assistant 内容）。
    on_done：流结束/中断（finally）时回调（flush assistant 消息落库）。
    """
    stream_resp = _call_qwen(api_key, model, messages, stream=True, timeout=180, temperature=temperature)
    if stream_resp.status_code != 200:
        try:
            err_body = stream_resp.json()
        except Exception:
            err_body = stream_resp.text
        raise HTTPException(status_code=500, detail=f"千问流式输出失败: {_parse_qwen_error(stream_resp, err_body)}")

    def _gen() -> Iterator[str]:
        try:
            yield from _iter_qwen_sse(stream_resp, on_content=on_content)
        finally:
            stream_resp.close()
            if on_done is not None:
                try:
                    on_done()
                except Exception:  # noqa: BLE001 - 旁路落库，绝不阻断流式收尾
                    pass

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_text(content: str) -> StreamingResponse:
    def _gen() -> Iterator[str]:
        yield _sse_content_chunk(content)
        yield _sse_done()

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _finish_conversation_stream(
    api_key: str,
    model: str,
    conversation: list[dict[str, Any]],
    *,
    on_content: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[], None]] = None,
) -> StreamingResponse:
    """工具轮次结束后由千问流式生成最终回答。"""
    return _stream_from_messages(
        api_key,
        model,
        conversation,
        temperature=DATA_ANSWER_TEMPERATURE,
        on_content=on_content,
        on_done=on_done,
    )


@router.post("")
def ai_chat(
    body: AiChatRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # E08 · 学校级 AI 管控：AI 助教开关关闭时一律 403（先于任何 LLM 调用）
    require_ai_access(db, user_id, "ai_chat")

    # G4-B · 对话落库接线：请求时全量落库（旁路写入，DB 失败不阻断对话）
    conv = _persist_conversation_start(db, user_id, body)
    persist_seq = sum(1 for m in body.messages if m.role in ("user", "assistant"))
    on_content, on_done = _persist_callbacks(db, conv, persist_seq)

    _, api_key, model = get_llm_config(db)
    if not api_key:
        raise HTTPException(status_code=500, detail="系统设置中未配置文本大模型 API Key，无法使用 AI 助教")
    tools = get_ai_chat_tools(db, user_id)
    last_text = _last_user_message(body)
    current_label = _NAV_ID_TO_LABEL.get(body.currentModule or "", body.currentModule or "")

    # —— 登录账号 / 个人隐私：一律拒查 ——
    if looks_like_user_account_privacy_question(last_text):
        return _stream_from_messages(
            api_key,
            model,
            build_privacy_refusal_messages(body.messages),
            temperature=0.3,
            on_content=on_content,
            on_done=on_done,
        )

    is_feature_q = _is_feature_usage_question(last_text)
    is_data_q = looks_like_data_question(last_text) and not is_feature_q

    # —— 功能使用问答：知识库注入 + 千问流式生成（禁止模板直出）——
    if is_feature_q:
        tutorial_system = build_tutorial_system_prompt(
            last_text,
            current_module_label=current_label,
        )
        feature_messages: list[dict[str, Any]] = [
            {"role": "system", "content": tutorial_system},
            *[m.model_dump() for m in body.messages],
        ]
        return _stream_from_messages(
            api_key,
            model,
            feature_messages,
            temperature=0.55,
            on_content=on_content,
            on_done=on_done,
        )

    # —— 数据查询：预查 + 千问流式生成（禁止模板直出）——
    prefetch = run_auto_tool_calls(db, user_id, last_text) if is_data_q else []
    intent_hint = build_intent_sql_hint(db, user_id, last_text) if is_data_q else ""
    system_prompt = (
        build_system_prompt(db, user_id)
        + _module_hint(body.currentModule)
        + format_prefetch_block(prefetch)
        + (f"\n\n{intent_hint}" if intent_hint else "")
    )
    base_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *[m.model_dump() for m in body.messages],
    ]

    # 已有预查结果时直接流式生成，避免假流式与跨班误答
    if is_data_q and prefetch:
        return _stream_from_messages(
            api_key,
            model,
            base_messages,
            temperature=DATA_ANSWER_TEMPERATURE,
            on_content=on_content,
            on_done=on_done,
        )

    first_resp = _call_qwen(api_key, model, base_messages, tools=tools, stream=False)
    try:
        first_body = first_resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"千问模型返回异常: {e}")

    if first_resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"千问模型返回错误: {_parse_qwen_error(first_resp, first_body)}")

    first_choice = (first_body.get("choices") or [{}])[0]
    tool_calls = (first_choice.get("message") or {}).get("tool_calls") or []

    if tool_calls:
        conversation = _run_tool_rounds(db, user_id, api_key, model, base_messages, first_choice)
        return _finish_conversation_stream(
            api_key,
            model,
            conversation,
            on_content=on_content,
            on_done=on_done,
        )

    if is_data_q:
        retry_hint = build_intent_sql_hint(db, user_id, last_text)
        retry_messages = [
            *base_messages,
            {
                "role": "user",
                "content": (
                    "【系统要求】这是数据查询问题。若上方预查无结果，"
                    "请调用 execute_mysql_query 或 execute_local_data_query 编写 SELECT 查询；"
                    "若仍无数据，用自然语言如实说明未查到，禁止编造。"
                    + (f"\n{retry_hint}" if retry_hint else "")
                ),
            },
        ]
        retry_resp = _call_qwen(api_key, model, retry_messages, tools=tools, stream=False)
        try:
            retry_body = retry_resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"千问模型返回异常: {e}")
        if retry_resp.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail=f"千问模型返回错误: {_parse_qwen_error(retry_resp, retry_body)}",
            )
        retry_choice = (retry_body.get("choices") or [{}])[0]
        retry_tool_calls = (retry_choice.get("message") or {}).get("tool_calls") or []
        if retry_tool_calls:
            conversation = _run_tool_rounds(db, user_id, api_key, model, retry_messages, retry_choice)
            return _finish_conversation_stream(
                api_key,
                model,
                conversation,
                on_content=on_content,
                on_done=on_done,
            )
        return _stream_from_messages(
            api_key,
            model,
            retry_messages,
            temperature=DATA_ANSWER_TEMPERATURE,
            on_content=on_content,
            on_done=on_done,
        )

    # 一般闲聊：直接流式生成
    return _stream_from_messages(
        api_key,
        model,
        base_messages,
        on_content=on_content,
        on_done=on_done,
    )
