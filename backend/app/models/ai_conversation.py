"""AI 对话落库 · 数据模型（G4-A，P0 纯 schema）。

对应 docs/contracts/00-data-layer-baseline.md §3.3.2 / §3.4.1 预留 DDL：
  - agent_conversations          （AiConversation）
  - agent_conversation_messages  （AiConversationMessage）
  - agent_audit_logs             （AiAuditLog，P3 预留一并落地 schema，不接业务逻辑）

字段严格照抄文档 DDL；不做任何业务逻辑接线（落库接线在下一 dispatch）。
"""
from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from app.database import Base
from app.models.user import gen_uuid


class AiConversation(Base):
    """智能体对话会话表（agent_conversations，预留）。"""

    __tablename__ = "agent_conversations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="对话所属教师")
    agent_role_id = Column(String(36), nullable=True, comment="智能体角色（未来 agent_roles 表）")
    title = Column(String(255), nullable=True, comment="对话标题（可由 LLM 自动生成）")
    summary = Column(Text, nullable=True, comment="对话摘要（L2 记忆，定期更新）")
    context_snapshot = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="对话上下文快照（当前关联的学生/班级/考试等）")
    message_count = Column(Integer, nullable=False, default=0, server_default="0", comment="消息数")
    total_tokens = Column(Integer, nullable=False, default=0, server_default="0", comment="累计 token 消耗")
    total_cost_cent = Column(Integer, nullable=False, default=0, server_default="0", comment="累计成本(分)")
    status = Column(String(16), nullable=False, default="active", server_default="active", comment="active|archived")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_aconv_user_id", "user_id"),
        Index("idx_aconv_status", "status"),
        Index("idx_aconv_created_at", "created_at"),
    )


class AiConversationMessage(Base):
    """智能体对话消息表（agent_conversation_messages，一条消息 = 一行）。

    支持 user/assistant/tool/system 角色。
    """

    __tablename__ = "agent_conversation_messages"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    conversation_id = Column(
        String(36),
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属对话",
    )
    role = Column(String(16), nullable=False, comment="user|assistant|tool|system")
    content = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False, comment="消息内容")
    tool_name = Column(String(64), nullable=True, comment="如果是 tool 消息，记录工具名")
    tool_call_id = Column(String(64), nullable=True, comment="如果是 tool 消息，关联 tool_call id")
    tool_result_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True, comment="工具执行结果（JSON 原文）")
    model = Column(String(64), nullable=True, comment="使用的模型（assistant 消息）")
    tokens_used = Column(Integer, nullable=True, comment="该轮消耗 token 数")
    cost_cent = Column(Integer, nullable=True, comment="该轮成本(分)")
    seq = Column(Integer, nullable=False, default=0, server_default="0", comment="消息序号（会话内自增）")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_acmsg_conversation_id", "conversation_id"),
        Index("idx_acmsg_seq", "conversation_id", "seq"),
    )


class AiAuditLog(Base):
    """智能体审计日志表（agent_audit_logs，预留，全程留痕）。

    每一条工具调用/模型调用/人工确认都记录；字段照抄文档 DDL。
    注：conversation_id 在 DDL 中仅建索引、无外键约束（审计日志需在对话删除后留存）。
    """

    __tablename__ = "agent_audit_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="操作教师")
    conversation_id = Column(String(36), nullable=True, comment="关联对话")
    event_type = Column(String(32), nullable=False, comment="tool_call|tool_result|llm_request|llm_response|human_approval|error")
    event_subtype = Column(String(64), nullable=True, comment="细分: execute_mysql_query|send_notification|...")
    tool_name = Column(String(64), nullable=True, comment="工具名（tool_call/tool_result 时）")
    tool_args_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True, comment="工具入参（脱敏后）")
    tool_result_summary = Column(Text, nullable=True, comment="工具结果摘要（完整结果太大时不存）")
    tool_success = Column(Boolean, nullable=True, comment="工具执行是否成功")
    model = Column(String(64), nullable=True, comment="使用的模型（llm_request/response 时）")
    tokens_used = Column(Integer, nullable=True, comment="token 消耗")
    cost_cent = Column(Integer, nullable=True, comment="成本(分)")
    latency_ms = Column(Integer, nullable=True, comment="耗时(毫秒)")
    approval_status = Column(String(16), nullable=True, comment="pending|approved|rejected（human_approval 时）")
    approval_reason = Column(Text, nullable=True, comment="审批备注")
    ip_address = Column(String(45), nullable=True, comment="操作 IP")
    user_agent = Column(String(512), nullable=True, comment="User-Agent")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_aaal_user_id", "user_id"),
        Index("idx_aaal_event_type", "event_type"),
        Index("idx_aaal_conversation_id", "conversation_id"),
        Index("idx_aaal_created_at", "created_at"),
    )
