"""Phase 09B — TeacherAnnotation and signal-status persistence."""
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.models.observation import AttentionSignal, TeacherAnnotation


def lock_signal(db: Session, signal_id: uuid.UUID) -> Optional[AttentionSignal]:
    """Row lock so concurrent status changes serialize and each audit row has the correct old status."""
    return db.scalar(
        select(AttentionSignal).where(AttentionSignal.id == signal_id)
        .with_for_update().execution_options(populate_existing=True)
    )


def create(db: Session, annotation: TeacherAnnotation) -> TeacherAnnotation:
    db.add(annotation)
    db.flush()
    return annotation


def get_active(db: Session, annotation_id: uuid.UUID) -> Optional[TeacherAnnotation]:
    return db.scalar(select(TeacherAnnotation).where(and_(
        TeacherAnnotation.id == annotation_id, TeacherAnnotation.deleted_at.is_(None),
    )))


def list_for_teacher(
    db: Session, teacher_id: uuid.UUID, student_id: Optional[uuid.UUID], session_id: Optional[uuid.UUID],
    signal_id: Optional[uuid.UUID], created_from: Optional[datetime], created_to: Optional[datetime], skip: int, limit: int,
) -> Tuple[List[TeacherAnnotation], int]:
    conditions = [TeacherAnnotation.teacher_id == teacher_id, TeacherAnnotation.deleted_at.is_(None)]
    if student_id:
        conditions.append(TeacherAnnotation.student_id == student_id)
    if session_id:
        conditions.append(TeacherAnnotation.session_id == session_id)
    if signal_id:
        conditions.append(TeacherAnnotation.signal_id == signal_id)
    if created_from:
        conditions.append(TeacherAnnotation.created_at >= created_from)
    if created_to:
        conditions.append(TeacherAnnotation.created_at <= created_to)
    where = and_(*conditions)
    total = db.scalar(select(func.count(TeacherAnnotation.id)).where(where)) or 0
    items = db.scalars(
        select(TeacherAnnotation).where(where)
        .order_by(desc(TeacherAnnotation.created_at), desc(TeacherAnnotation.id))
        .offset(skip).limit(limit)
    ).all()
    return list(items), total
