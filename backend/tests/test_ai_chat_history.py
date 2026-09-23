# -*- coding: utf-8 -*-
"""G4-B AI 助教对话落库 + 历史查询测试（in-memory SQLite，无需 MySQL）。

覆盖：
  1. ai_chat() 落库接线：会话创建（title 截断 ≤50 / context_snapshot / message_count）、
     消息落库（role/content/seq）、流式结束后 assistant 内容 flush、统计更新
  2. 落库异常不阻断对话：conv 创建失败仍可流式；on_done 抛错不穿透
  3. 历史三端点：列表（空数据 / 分页倒序 / 含新建会话）、详情（含消息、他人会话 404）、
     删除（级联删消息、他人会话 404、删除后列表不含）
  4. 权限：无角色用户 require_ai_access 403

模式参照 tests/test_ai_conversation_models.py（SQLite 编译补丁）+ tests/test_dossier.py（直调函数）。
"""
from __future__ import annotations

import asyncio
import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.mysql import JSON, LONGTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


async def _collect_async(body_iterator):
    return [c async for c in body_iterator]

# 让 mysql.LONGTEXT / mysql.JSON 在 SQLite 下可编译（仅测试进程内 SQLite 渲染生效）
@compiles(LONGTEXT, "sqlite")
def _compile_longtext_sqlite(type_, compiler, **kw):
    return "TEXT"


@compiles(JSON, "sqlite")
def _compile_json_sqlite(type_, compiler, **kw):
    return "TEXT"


from app.database import Base
from app.models import AiConversation, AiConversationMessage
from app.models.user import User
from app.routers import ai_chat as ai_chat_mod
from app.routers import ai_chat_history
from app.routers.ai_chat import AiChatRequest, ChatMessage


# ── 夹具 ────────────────────────────────────────────────


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[User.__table__, AiConversation.__table__, AiConversationMessage.__table__],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _add_user(db, uid="u-1", roles="任课教师") -> User:
    u = User(id=uid, email=f"{uid}@t.local", password_hash="x", roles=roles)
    db.add(u)
    db.commit()
    return u


def _add_conv(db, user_id="u-1", title="会话", updated_at=None) -> AiConversation:
    c = AiConversation(
        user_id=user_id,
        title=title,
        summary=None,
        status="active",
        message_count=0,
        created_at=updated_at,
        updated_at=updated_at,
    )
    db.add(c)
    db.commit()
    return c


def _add_msg(db, conversation_id, role, content, seq) -> AiConversationMessage:
    m = AiConversationMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        seq=seq,
    )
    db.add(m)
    db.commit()
    return m


class _FakeQwenResponse:
    """_call_qwen 的非流式首轮响应：无 tool_calls，走一般闲聊直出。"""

    status_code = 200

    def json(self):
        return {"choices": [{"message": {"content": "好的", "role": "assistant"}}]}


class _FakeStream:
    """monkeypatch _stream_from_messages 的假流：迭代时回调 on_content / on_done。"""

    def __init__(self, on_content=None, on_done=None, chunks=("你好，这是回答", "的第二段")):
        self.on_content = on_content
        self.on_done = on_done
        self.chunks = chunks

    def __iter__(self):
        for c in self.chunks:
            if self.on_content is not None:
                self.on_content(c)
            yield c
        if self.on_done is not None:
            self.on_done()


def _fake_stream_factory(captured: dict):
    """返回一个 _stream_from_messages 替身，记录 kwargs 并返回 _FakeStream。"""

    def _fake(api_key, model, messages, **kwargs):
        captured.update(
            {
                "api_key": api_key,
                "model": model,
                "messages": messages,
                "on_content": kwargs.get("on_content"),
                "on_done": kwargs.get("on_done"),
            }
        )
        return _FakeStream(
            on_content=kwargs.get("on_content"),
            on_done=kwargs.get("on_done"),
        )

    return _fake


# ── ai_chat() 落库接线 ──────────────────────────────────


def _wire_ai_chat_monkeypatch(monkeypatch, captured: dict):
    monkeypatch.setattr(ai_chat_mod, "get_qwen_config", lambda *a, **k: ("sk-test", "qwen3.7-plus"))
    monkeypatch.setattr(ai_chat_mod, "get_ai_chat_tools", lambda *a, **k: [])
    monkeypatch.setattr(ai_chat_mod, "build_system_prompt", lambda *a, **k: "system prompt")
    monkeypatch.setattr(ai_chat_mod, "_call_qwen", lambda *a, **k: _FakeQwenResponse())
    monkeypatch.setattr(ai_chat_mod, "_stream_from_messages", _fake_stream_factory(captured))


def test_ai_chat_persists_conversation_and_messages(db, monkeypatch):
    u = _add_user(db)
    captured: dict = {}
    _wire_ai_chat_monkeypatch(monkeypatch, captured)

    long_user_text = (
        "你好，介绍一下叙阅这个产品吧，它有哪些功能呢？"
        "这是一段非常长的消息用来测试标题截断逻辑是否正常工作超出五十个字"
    )
    body = AiChatRequest(
        messages=[
            ChatMessage(role="user", content=long_user_text),
            ChatMessage(role="assistant", content="好的，我先简单介绍。"),
            ChatMessage(role="user", content="它能帮我做什么？"),
        ],
        currentModule="dashboard",
    )
    resp = ai_chat_mod.ai_chat(body, user_id=u.id, db=db)

    # 会话创建：title 截断 ≤50、context_snapshot、message_count=body 内 user/assistant 数
    conv = db.query(AiConversation).one()
    assert conv.user_id == u.id
    assert conv.title and len(conv.title) <= 50
    assert conv.title.startswith("你好，介绍一下叙阅")
    assert conv.context_snapshot == {"currentModule": "dashboard"}
    assert conv.message_count == 3

    # 消息落库：role/content/seq 顺序
    msgs = db.query(AiConversationMessage).order_by(AiConversationMessage.seq).all()
    assert [(m.role, m.seq) for m in msgs] == [("user", 0), ("assistant", 1), ("user", 2)]
    assert msgs[0].content == long_user_text
    assert msgs[1].content == "好的，我先简单介绍。"
    assert msgs[2].content == "它能帮我做什么？"

    # 消费流 → 触发 on_content / on_done
    list(resp)
    assert captured.get("on_content") is not None
    assert captured.get("on_done") is not None

    # assistant 追加落库 + message_count 更新
    db.expire_all()
    msgs = db.query(AiConversationMessage).order_by(AiConversationMessage.seq).all()
    assert len(msgs) == 4
    assert msgs[3].role == "assistant"
    assert msgs[3].seq == 3
    assert msgs[3].content == "你好，这是回答的第二段"
    conv = db.query(AiConversation).one()
    assert conv.message_count == 4


def test_ai_chat_without_current_module_snapshot_null(db, monkeypatch):
    u = _add_user(db)
    captured: dict = {}
    _wire_ai_chat_monkeypatch(monkeypatch, captured)

    body = AiChatRequest(
        messages=[ChatMessage(role="user", content="你好")],
        currentModule=None,
    )
    resp = ai_chat_mod.ai_chat(body, user_id=u.id, db=db)
    list(resp)
    conv = db.query(AiConversation).one()
    assert conv.context_snapshot is None
    assert conv.title == "你好"


def test_ai_chat_conversation_start_failure_does_not_block_stream(db, monkeypatch):
    """落库失败（conv 创建返回 None）不阻断对话，流式照常可用。"""
    u = _add_user(db)
    captured: dict = {}
    _wire_ai_chat_monkeypatch(monkeypatch, captured)
    monkeypatch.setattr(ai_chat_mod, "_persist_conversation_start", lambda *a, **k: None)

    body = AiChatRequest(messages=[ChatMessage(role="user", content="你好")])
    resp = ai_chat_mod.ai_chat(body, user_id=u.id, db=db)
    chunks = list(resp)
    assert chunks == ["你好，这是回答", "的第二段"]
    # 未创建任何会话/消息
    assert db.query(AiConversation).count() == 0
    assert db.query(AiConversationMessage).count() == 0


def test_stream_done_callback_error_is_swallowed(monkeypatch):
    """on_done 落库抛错被 _stream_from_messages 吞掉，流式收尾不报错。"""

    class _FakeLineResp:
        status_code = 200

        def iter_lines(self, decode_unicode=True):
            yield 'data: {"choices": [{"delta": {"content": "hi"}}]}'
            yield "data: [DONE]"

        def close(self):
            pass

    monkeypatch.setattr(ai_chat_mod, "_call_qwen", lambda *a, **k: _FakeLineResp())

    def _boom():
        raise RuntimeError("db down")

    sr = ai_chat_mod._stream_from_messages("k", "m", [], on_content=lambda c: None, on_done=_boom)
    chunks = asyncio.run(_collect_async(sr.body_iterator))
    assert chunks  # 流正常产出，on_done 异常被吞
    assert any("hi" in c for c in chunks)


def test_flush_assistant_message_updates_stats(db):
    """_flush_assistant_message 单测：追加 assistant + message_count +1。"""
    u = _add_user(db)
    conv = _add_conv(db, user_id=u.id, title="t")
    conv.message_count = 1
    db.commit()

    ai_chat_mod._flush_assistant_message(db, conv, "完整回答", seq=1)
    db.expire_all()
    msgs = db.query(AiConversationMessage).order_by(AiConversationMessage.seq).all()
    assert len(msgs) == 1
    assert msgs[0].role == "assistant"
    assert msgs[0].content == "完整回答"
    assert msgs[0].seq == 1
    assert db.query(AiConversation).one().message_count == 2


# ── 历史查询：列表 ──────────────────────────────────────


def test_history_list_empty(db):
    u = _add_user(db)
    resp = ai_chat_history.list_conversations(page=1, page_size=20, user_id=u.id, db=db)
    assert resp.data["items"] == []
    assert resp.data["total"] == 0


def test_history_list_contains_created_conversation(db):
    u = _add_user(db)
    c = _add_conv(db, user_id=u.id, title="我的会话")
    _add_msg(db, c.id, "user", "你好", 0)
    _add_msg(db, c.id, "assistant", "你好呀", 1)
    c.message_count = 2
    db.commit()

    resp = ai_chat_history.list_conversations(page=1, page_size=20, user_id=u.id, db=db)
    assert resp.data["total"] == 1
    item = resp.data["items"][0]
    assert item["id"] == c.id
    assert item["title"] == "我的会话"
    assert item["message_count"] == 2


def test_history_list_paginated_order_by_updated_at(db):
    u = _add_user(db)
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    c1 = _add_conv(db, user_id=u.id, title="旧", updated_at=base)
    c2 = _add_conv(db, user_id=u.id, title="新", updated_at=base + datetime.timedelta(minutes=5))
    c3 = _add_conv(db, user_id=u.id, title="最新", updated_at=base + datetime.timedelta(minutes=10))

    resp = ai_chat_history.list_conversations(page=1, page_size=2, user_id=u.id, db=db)
    assert resp.data["total"] == 3
    assert [i["id"] for i in resp.data["items"]] == [c3.id, c2.id]

    resp2 = ai_chat_history.list_conversations(page=2, page_size=2, user_id=u.id, db=db)
    assert [i["id"] for i in resp2.data["items"]] == [c1.id]
    assert c1.updated_at.isoformat() == resp2.data["items"][0]["updated_at"]  # ISO 字符串


def test_history_list_only_own_conversations(db):
    _add_user(db, uid="u-1")
    _add_user(db, uid="u-2")
    mine = _add_conv(db, user_id="u-1", title="我的")
    _add_conv(db, user_id="u-2", title="他人的")

    resp = ai_chat_history.list_conversations(page=1, page_size=20, user_id="u-1", db=db)
    ids = [i["id"] for i in resp.data["items"]]
    assert mine.id in ids
    assert len(ids) == 1


# ── 历史查询：详情 / 删除 ───────────────────────────────


def test_history_detail_contains_messages_sorted_by_seq(db):
    u = _add_user(db)
    c = _add_conv(db, user_id=u.id, title="详情")
    _add_msg(db, c.id, "user", "第一条", 0)
    _add_msg(db, c.id, "assistant", "第二条", 1)
    _add_msg(db, c.id, "user", "第三条", 2)

    resp = ai_chat_history.get_conversation_detail(c.id, user_id=u.id, db=db)
    data = resp.data
    assert data["id"] == c.id
    assert data["title"] == "详情"
    msgs = data["messages"]
    assert [m["seq"] for m in msgs] == [0, 1, 2]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "第一条"


def test_history_detail_other_users_conversation_404(db):
    _add_user(db, uid="u-1")
    _add_user(db, uid="u-2")
    c = _add_conv(db, user_id="u-2", title="他人的")

    with pytest.raises(HTTPException) as exc:
        ai_chat_history.get_conversation_detail(c.id, user_id="u-1", db=db)
    assert exc.value.status_code == 404


def test_history_delete_removes_conversation_and_messages(db):
    u = _add_user(db)
    c = _add_conv(db, user_id=u.id, title="待删")
    _add_msg(db, c.id, "user", "你好", 0)
    _add_msg(db, c.id, "assistant", "你好呀", 1)

    resp = ai_chat_history.delete_conversation(c.id, user_id=u.id, db=db)
    assert resp.data["id"] == c.id
    assert db.query(AiConversation).count() == 0
    assert db.query(AiConversationMessage).count() == 0


def test_history_delete_other_users_conversation_404(db):
    _add_user(db, uid="u-1")
    _add_user(db, uid="u-2")
    c = _add_conv(db, user_id="u-2", title="他人的")

    with pytest.raises(HTTPException) as exc:
        ai_chat_history.delete_conversation(c.id, user_id="u-1", db=db)
    assert exc.value.status_code == 404
    # 他人的会话仍存在
    assert db.query(AiConversation).count() == 1


def test_history_detail_and_delete_not_found(db):
    u = _add_user(db)
    with pytest.raises(HTTPException) as exc:
        ai_chat_history.get_conversation_detail("no-such-id", user_id=u.id, db=db)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        ai_chat_history.delete_conversation("no-such-id", user_id=u.id, db=db)
    assert exc.value.status_code == 404


# ── 权限：require_ai_access ─────────────────────────────


def test_history_requires_ai_access_role(db):
    """无角色用户 → require_ai_access 403，列表/详情/删除都不可用。"""
    u = _add_user(db, uid="u-no-role", roles="")
    with pytest.raises(HTTPException) as exc:
        ai_chat_history.list_conversations(user_id=u.id, db=db)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        ai_chat_history.get_conversation_detail("whatever", user_id=u.id, db=db)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        ai_chat_history.delete_conversation("whatever", user_id=u.id, db=db)
    assert exc.value.status_code == 403


def test_history_routes_registered():
    from app.routers.ai_chat_history import router

    paths = {r.path for r in router.routes}
    assert "/ai-chat/history" in paths
    assert "/ai-chat/history/{conversation_id}" in paths
