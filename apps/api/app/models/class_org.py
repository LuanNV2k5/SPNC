import secrets
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, TimestampMixin

# docs/38 D1: 8 characters, no 0/O/1/I/L
INVITE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
INVITE_LENGTH = 8


def generate_invite_code() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH))


class Class(Base, TimestampMixin):
    __tablename__ = "classes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    academic_year: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # REQ-CLASS-001; shown to the owner only
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, default=generate_invite_code)

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    owner: Mapped["User"] = relationship("User")
    memberships: Mapped[List["ClassMembership"]] = relationship("ClassMembership", back_populates="class_org")

class ClassMembership(Base, TimestampMixin):
    __tablename__ = "class_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    class_org: Mapped["Class"] = relationship("Class", back_populates="memberships")
    student: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint('class_id', 'student_id', name='uq_class_memberships_class_id_student_id'),
    )
