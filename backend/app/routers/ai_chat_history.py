# -*- coding: utf-8 -*-
"""AI 助教 · 对话历史查询（G4-B，P1 阶段）。

与 ai_chat 对话入口共用 /ai-chat 前缀：历史三端点挂在 /ai-chat/history 下，
权限沿用 require_ai_access / get_current_user_id，只允许访问自己的会话。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.models.ai_conversation import AiConversation, AiConversationMessage
from app.schemas.common import ApiResponse
from app.services.ai_policy import require_ai_access

router = APIRouter(
    prefix="/ai-chat/history",
    tags=["ai_chat_history"],
    dependencies=[Depends(bind_grading_user_context)],
)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _iso(v) -> Optional[str]:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _conversation_brief(row: AiConversation) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "summary": row.summary,
        "message_count": row.message_count,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _message_dict(row: AiConversationMessage) -> dict:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "role": row.role,
        "content": row.content,
        "tool_name": row.tool_name,
        "tool_call_id": row.tool_call_id,
        "model": row.model,
        "tokens_used": row.tokens_used,
        "cost_cent": row.cost_cent,
        "seq": row.seq,
        "created_at": _iso(row.created_at),
    }


def _get_own_conversation(db: Session, user_id: str, conversation_id: str) -> AiConversation:
    """仅允许查/删自己的会话，他人会话一律 404（不泄露存在性）。"""
    row = (
        db.query(AiConversation)
        .filter(
            AiConversation.id == conversation_id,
            AiConversation.user_id == user_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    return row


@router.get("")
def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """当前 user 的会话列表，按 updated_at 倒序分页。"""
    require_ai_access(db, user_id, "ai_chat")
    q = db.query(AiConversation).filter(
        AiConversation.user_id == user_id,
        AiConversation.status == "active",
    )
    total = q.count()
    rows = (
        q.order_by(AiConversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ApiResponse(
        data={
            "items": [_conversation_brief(r) for r in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }
    )


@router.get("/{conversation_id}")
def get_conversation_detail(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """会话详情：含全部 AiConversationMessage，按 seq 升序。"""
    require_ai_access(db, user_id, "ai_chat")
    conv = _get_own_conversation(db, user_id, conversation_id)
    messages = (
        db.query(AiConversationMessage)
        .filter(AiConversationMessage.conversation_id == conv.id)
        .order_by(AiConversationMessage.seq.asc())
        .all()
    )
    data = _conversation_brief(conv)
    data["messages"] = [_message_dict(m) for m in messages]
    return ApiResponse(data=data)


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """删除会话（级联删消息，仅限自己的会话）。"""
    require_ai_access(db, user_id, "ai_chat")
    conv = _get_own_conversation(db, user_id, conversation_id)
    # 显式删消息（SQLite 测试不默认开 FK cascade；MySQL 外键 CASCADE 为兜底）
    db.query(AiConversationMessage).filter(
        AiConversationMessage.conversation_id == conv.id
    ).delete(synchronize_session=False)
    db.delete(conv)
    db.commit()
    return ApiResponse(message="会话已删除", data={"id": conversation_id})
