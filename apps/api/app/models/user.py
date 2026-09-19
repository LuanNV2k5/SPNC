import enum
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import String, Boolean, text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base, TimestampMixin

class RoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"

class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    PENDING = "PENDING"

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[RoleEnum] = mapped_column(String(20), index=True)
    status: Mapped[AccountStatus] = mapped_column(String(20), default=AccountStatus.ACTIVE, index=True)
    force_password_change: Mapped[bool] = mapped_column(Boolean, default=False)

    refresh_sessions: Mapped[List["RefreshSession"]] = relationship("RefreshSession", back_populates="user", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="actor")

class RefreshSession(Base, TimestampMixin):
    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    device_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="refresh_sessions")

class SystemSetting(Base, TimestampMixin):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    metadata_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    actor: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")
