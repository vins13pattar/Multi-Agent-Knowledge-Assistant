from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, Integer,
    ForeignKey, JSON, Enum as SAEnum, Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    admin = "admin"
    employee = "employee"


class UserStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.employee)
    status = Column(SAEnum(UserStatus), nullable=False, default=UserStatus.active)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    conversations = relationship("Conversation", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="actor")
    feedback = relationship("Feedback", back_populates="user")


class ConversationStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    status = Column(SAEnum(ConversationStatus), default=ConversationStatus.active)
    summary = Column(Text, nullable=True)
    thread_id = Column(String(255), unique=True, nullable=True)  # LangGraph thread ID
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at")
    approval_requests = relationship("ApprovalRequest", back_populates="conversation")


class SenderType(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)
    sender_type = Column(SAEnum(SenderType), nullable=False)
    content = Column(Text, nullable=False)
    structured_content = Column(JSON, nullable=True)  # citations, tool results, etc.
    model_provider = Column(String(100), nullable=True)
    model_name = Column(String(100), nullable=True)
    prompt_version = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
    feedback = relationship("Feedback", back_populates="message")


class KnowledgeSourceType(str, enum.Enum):
    local_folder = "local_folder"
    s3 = "s3"
    sharepoint = "sharepoint"
    confluence = "confluence"
    upload = "upload"


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    source_type = Column(SAEnum(KnowledgeSourceType), nullable=False)
    source_config = Column(JSON, nullable=True)
    access_scope = Column(String(100), default="shared")
    status = Column(String(50), default="active")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    documents = relationship("Document", back_populates="source")


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    ingesting = "ingesting"
    ingested = "ingested"
    failed = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_sources.id"), nullable=True)
    name = Column(String(500), nullable=False)
    version = Column(String(50), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    status = Column(SAEnum(DocumentStatus), default=DocumentStatus.pending)
    doc_metadata = Column(JSON, nullable=True)
    access_scope = Column(String(100), default="shared")
    chunk_count = Column(Integer, default=0)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source = relationship("KnowledgeSource", back_populates="documents")


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action_type = Column(String(200), nullable=False)
    action_payload = Column(JSON, nullable=True)
    risk_level = Column(SAEnum(RiskLevel), nullable=False, default=RiskLevel.high)
    status = Column(SAEnum(ApprovalStatus), default=ApprovalStatus.pending)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approver_comment = Column(Text, nullable=True)
    thread_id = Column(String(255), nullable=True)  # LangGraph thread to resume
    expires_at = Column(DateTime, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="approval_requests")


class ToolExecutionStatus(str, enum.Enum):
    success = "success"
    failed = "failed"
    timeout = "timeout"
    retried = "retried"


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    tool_name = Column(String(200), nullable=False)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    status = Column(SAEnum(ToolExecutionStatus), nullable=False)
    retry_count = Column(Integer, default=0)
    error_code = Column(String(100), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    idempotency_key = Column(String(255), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PromptStatus(str, enum.Enum):
    active = "active"
    draft = "draft"
    deprecated = "deprecated"


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_key = Column(String(200), nullable=False, index=True)
    version = Column(String(50), nullable=False)
    agent_name = Column(String(200), nullable=True)
    template = Column(Text, nullable=False)
    variables = Column(JSON, nullable=True)
    output_schema = Column(String(200), nullable=True)
    model_config_data = Column(JSON, nullable=True)
    status = Column(SAEnum(PromptStatus), default=PromptStatus.draft)
    evaluation_score = Column(Float, nullable=True)
    change_notes = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(200), nullable=False)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(255), nullable=True)
    request_id = Column(String(255), nullable=True)
    event_metadata = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    actor = relationship("User", back_populates="audit_logs")


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=True)  # 1-5
    category = Column(String(100), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("Message", back_populates="feedback")
    user = relationship("User", back_populates="feedback")
