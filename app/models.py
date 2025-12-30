import enum
import uuid
from datetime import datetime, date

from sqlalchemy import (
    String,
    Text,
    DateTime,
    Date,
    ForeignKey,
    Enum,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Channel(str, enum.Enum):
    gmail = "gmail"
    json = "json"


class MessageStatus(str, enum.Enum):
    inbox = "inbox"
    archived = "archived"
    snoozed = "snoozed"
    deleted = "deleted"


class SuggestionStatus(str, enum.Enum):
    proposed = "proposed"
    accepted = "accepted"
    rejected = "rejected"


class ActionType(str, enum.Enum):
    archive_all = "archive_all"
    snooze = "snooze"
    reply_with_template = "reply_with_template"
    label_add = "label_add"
    label_remove = "label_remove"


class Urgency(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # App identity
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)

    # Your rule: 1 app user == 1 gmail account
    gmail_account_email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)

    # For incremental Gmail sync later (History API start point)
    gmail_last_history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    threads: Mapped[list["Thread"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    clusters: Mapped[list["Cluster"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[Channel] = mapped_column(Enum(Channel, name="channel_enum"), nullable=False)

    # Gmail threadId
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)

    subject: Mapped[str | None] = mapped_column(String(998), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="threads")
    messages: Mapped[list["Message"]] = relationship(back_populates="thread")

    __table_args__ = (
        UniqueConstraint("user_id", "channel", "external_id", name="uq_thread_user_channel_external"),
        Index("ix_thread_user_channel", "user_id", "channel"),
    )


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    algo_version: Mapped[str] = mapped_column(String(64), nullable=False, default="clustering_v1")

    title: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Day 5 summary contract can live here later
    summary_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="clusters")
    messages: Mapped[list["Message"]] = relationship(back_populates="cluster")

    __table_args__ = (
        Index("ix_cluster_user_day", "user_id", "digest_date"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("threads.id", ondelete="SET NULL"), nullable=True)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True)

    channel: Mapped[Channel] = mapped_column(Enum(Channel, name="channel_enum"), nullable=False)

    # Gmail message id
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # Gmail threadId (duplicate for importer convenience)
    thread_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # internalDate mapped to datetime (we’ll convert when importing)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sender: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    snippet: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Gmail labelIds list
    labels: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # Gmail historyId (optional, useful later)
    history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, name="message_status_enum"),
        nullable=False,
        default=MessageStatus.inbox,
    )

    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="messages")
    thread: Mapped["Thread"] = relationship(back_populates="messages")
    cluster: Mapped["Cluster"] = relationship(back_populates="messages")

    __table_args__ = (
        UniqueConstraint("user_id", "channel", "external_id", name="uq_message_user_channel_external"),
        Index("ix_message_user_status", "user_id", "status"),
        Index("ix_message_user_timestamp", "user_id", "timestamp"),
    )


class SuggestedAction(Base):
    __tablename__ = "suggested_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cluster_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)

    action_type: Mapped[ActionType] = mapped_column(Enum(ActionType, name="action_type_enum"), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    urgency: Mapped[Urgency] = mapped_column(Enum(Urgency, name="urgency_enum"), nullable=False, default=Urgency.low)
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    status: Mapped[SuggestionStatus] = mapped_column(
        Enum(SuggestionStatus, name="suggestion_status_enum"),
        nullable=False,
        default=SuggestionStatus.proposed,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_suggested_actions_user_cluster", "user_id", "cluster_id"),
    )
