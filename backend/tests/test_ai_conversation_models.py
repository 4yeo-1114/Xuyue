"""G4-A AI 对话落库 · 数据模型验收测试（纯 schema，不连真库）。

验证：
  1. 三模型表名/字段与 docs/contracts/00-data-layer-baseline.md §3.3.2/§3.4.1 预留 DDL 对齐
  2. 外键 / 索引 / 默认值关键点抽查
  3. in-memory SQLite create_all 可建表 + 最小 roundtrip（mysql.LONGTEXT 在 sqlite 下编译为 TEXT）
"""
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

# 让 mysql.LONGTEXT 在 SQLite 下可编译（仅本进程内 SQLite 渲染生效，不影响 MySQL 编译）
@compiles(LONGTEXT, "sqlite")
def _compile_mysql_longtext_sqlite(type_, compiler, **kw):
    return "TEXT"


from app.database import Base
from app.models import AiAuditLog, AiConversation, AiConversationMessage
from app.models.user import User

# 文档 DDL 字段全集（与 docs/contracts/00-data-layer-baseline.md 对齐）
_CONVERSATION_COLS = {
    "id", "user_id", "agent_role_id", "title", "summary", "context_snapshot",
    "message_count", "total_tokens", "total_cost_cent", "status",
    "created_at", "updated_at",
}
_MESSAGE_COLS = {
    "id", "conversation_id", "role", "content", "tool_name", "tool_call_id",
    "tool_result_json", "model", "tokens_used", "cost_cent", "seq", "created_at",
}
_AUDIT_LOG_COLS = {
    "id", "user_id", "conversation_id", "event_type", "event_subtype",
    "tool_name", "tool_args_json", "tool_result_summary", "tool_success",
    "model", "tokens_used", "cost_cent", "latency_ms", "approval_status",
    "approval_reason", "ip_address", "user_agent", "created_at",
}


# ── 表名 / metadata 注册 ────────────────────────────────


def test_table_names_registered_in_metadata():
    assert AiConversation.__tablename__ == "agent_conversations"
    assert AiConversationMessage.__tablename__ == "agent_conversation_messages"
    assert AiAuditLog.__tablename__ == "agent_audit_logs"
    assert "agent_conversations" in Base.metadata.tables
    assert "agent_conversation_messages" in Base.metadata.tables
    assert "agent_audit_logs" in Base.metadata.tables


def test_models_exported_from_package():
    import app.models as m
    assert hasattr(m, "AiConversation")
    assert hasattr(m, "AiConversationMessage")
    assert hasattr(m, "AiAuditLog")


# ── 字段与 DDL 对齐 ─────────────────────────────────────


def test_ai_conversation_columns_match_ddl():
    cols = set(AiConversation.__table__.columns.keys())
    assert cols == _CONVERSATION_COLS


def test_ai_conversation_message_columns_match_ddl():
    cols = set(AiConversationMessage.__table__.columns.keys())
    assert cols == _MESSAGE_COLS


def test_ai_audit_log_columns_match_ddl():
    cols = set(AiAuditLog.__table__.columns.keys())
    assert cols == _AUDIT_LOG_COLS


def test_ai_conversation_message_key_fields_present():
    """任务验收点：AiConversationMessage 有 conversation_id/role/content/seq。"""
    t = AiConversationMessage.__table__
    for col in ("conversation_id", "role", "content", "seq"):
        assert col in t.c
    assert t.c.conversation_id.nullable is False
    assert t.c.role.nullable is False
    assert t.c.content.nullable is False
    assert t.c.seq.nullable is False
    assert t.c.seq.default is not None


# ── 外键 ────────────────────────────────────────────────


def _fk_targets(table):
    targets = set()
    for fk in table.foreign_key_constraints:
        parent = fk.columns[0].name
        referred_table = fk.referred_table.name
        ondelete = fk.elements[0].ondelete
        targets.add((parent, referred_table, ondelete))
    return targets


def test_ai_conversation_user_fk():
    fks = _fk_targets(AiConversation.__table__)
    assert ("user_id", "users", "CASCADE") in fks


def test_ai_conversation_message_conversation_fk_cascade():
    fks = _fk_targets(AiConversationMessage.__table__)
    assert ("conversation_id", "agent_conversations", "CASCADE") in fks


def test_ai_audit_log_user_fk():
    fks = _fk_targets(AiAuditLog.__table__)
    assert ("user_id", "users", "CASCADE") in fks
    # 文档 DDL：audit_logs.conversation_id 仅建索引、无外键约束
    assert not any(fk[0] == "conversation_id" for fk in fks)


# ── 索引 ────────────────────────────────────────────────


def _index_names(table):
    return {ix.name for ix in table.indexes}


def test_ai_conversation_indexes():
    idx = _index_names(AiConversation.__table__)
    assert {"idx_aconv_user_id", "idx_aconv_status", "idx_aconv_created_at"} <= idx


def test_ai_conversation_message_indexes():
    idx = _index_names(AiConversationMessage.__table__)
    assert {"idx_acmsg_conversation_id", "idx_acmsg_seq"} <= idx


def test_ai_audit_log_indexes():
    idx = _index_names(AiAuditLog.__table__)
    assert {"idx_aaal_user_id", "idx_aaal_event_type", "idx_aaal_conversation_id", "idx_aaal_created_at"} <= idx


# ── in-memory SQLite 建表 + roundtrip ──────────────────


@pytest.fixture()
def sqlite_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            AiConversation.__table__,
            AiConversationMessage.__table__,
            AiAuditLog.__table__,
        ],
    )
    return engine


def test_sqlite_create_all_creates_three_tables(sqlite_engine):
    insp = inspect(sqlite_engine)
    tables = set(insp.get_table_names())
    assert {"agent_conversations", "agent_conversation_messages", "agent_audit_logs"} <= tables


def test_sqlite_roundtrip(sqlite_engine):
    Session = sessionmaker(bind=sqlite_engine)
    db = Session()
    try:
        u = User(email="t@test.local", password_hash="x")
        db.add(u)
        db.flush()
        conv = AiConversation(user_id=u.id, title="t", status="active")
        db.add(conv)
        db.flush()
        msg = AiConversationMessage(
            conversation_id=conv.id,
            role="assistant",
            content="hi",
            seq=0,
            tokens_used=10,
            cost_cent=1,
        )
        db.add(msg)
        log = AiAuditLog(user_id=u.id, conversation_id=conv.id, event_type="llm_request", model="qwen")
        db.add(log)
        db.commit()

        got = db.query(AiConversation).one()
        assert got.title == "t"
        assert got.message_count == 0  # 默认值
        assert got.status == "active"
        got_msg = db.query(AiConversationMessage).one()
        assert got_msg.role == "assistant" and got_msg.content == "hi" and got_msg.seq == 0
        got_log = db.query(AiAuditLog).one()
        assert got_log.event_type == "llm_request"
    finally:
        db.close()
