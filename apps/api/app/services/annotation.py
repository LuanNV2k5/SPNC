"""Phase 09B — Signal status transitions and TeacherAnnotation CRUD (docs/35 §4 09B, D1/D7/D8)."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.observation import AttentionSignal, SignalStatus, TeacherAnnotation
from app.models.user import AuditLog, User
from app.repositories import annotation as repo
from app.repositories import academic as academic_repo
from app.services import observation_auth as auth

# D1: NEW -> ACKNOWLEDGED | DISMISSED, and either back to NEW
ALLOWED_TRANSITIONS = {
    SignalStatus.NEW.value: {SignalStatus.ACKNOWLEDGED.value, SignalStatus.DISMISSED.value},
    SignalStatus.ACKNOWLEDGED.value: {SignalStatus.NEW.value},
    SignalStatus.DISMISSED.value: {SignalStatus.NEW.value},
}


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def change_signal_status(
    db: Session, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID, signal_id: uuid.UUID,
    new_status: SignalStatus, request_id: Optional[str],
) -> AttentionSignal:
    auth.authorize_student(db, teacher, class_id, student_id)
    signal = repo.lock_signal(db, signal_id)
    if not signal or signal.student_id != student_id:
        raise HTTPException(status_code=404, detail=_error("SIGNAL_NOT_FOUND", "Signal not found for student"))
    # The signal's session must be visible in this class context (docs/35 §3)
    auth.authorize_session(db, teacher, class_id, student_id, signal.session_id)

    old = getattr(signal.status, "value", signal.status)
    if new_status.value not in ALLOWED_TRANSITIONS.get(old, set()):
        raise HTTPException(status_code=422, detail=_error(
            "INVALID_SIGNAL_TRANSITION", f"Cannot change signal status from {old} to {new_status.value}"))

    # Status only; evidence stays immutable (DTI-08). Audit row is written in the same transaction.
    signal.status = new_status.value
    db.add(AuditLog(
        actor_id=teacher.id, action="SIGNAL_STATUS_CHANGED", target_type="ATTENTION_SIGNAL",
        target_id=str(signal.id), request_id=request_id,
        metadata_payload={"old_status": old, "new_status": new_status.value, "class_id": str(class_id)},
    ))
    db.commit()
    db.refresh(signal)
    return signal


def create_annotation(
    db: Session, teacher: User, student_id: uuid.UUID, session_id: Optional[uuid.UUID],
    signal_id: Optional[uuid.UUID], content: str,
) -> TeacherAnnotation:
    if not auth.teacher_can_observe_student(db, teacher, student_id):
        raise HTTPException(status_code=403, detail=_error("FORBIDDEN_RESOURCE", "Student not in your classes"))

    session = None
    if session_id:
        session = academic_repo.get_session_by_id(db, session_id)
        if not session or session.student_id != student_id:
            raise HTTPException(status_code=422, detail=_error("ANNOTATION_CONTEXT_MISMATCH", "Session does not belong to the student"))
    signal = None
    if signal_id:
        signal = db.get(AttentionSignal, signal_id)
        if not signal or signal.student_id != student_id:
            raise HTTPException(status_code=422, detail=_error("ANNOTATION_CONTEXT_MISMATCH", "Signal does not belong to the student"))
        if session_id and signal.session_id != session_id:
            raise HTTPException(status_code=422, detail=_error("ANNOTATION_CONTEXT_MISMATCH", "Signal does not belong to the session"))
        if session is None:
            session = academic_repo.get_session_by_id(db, signal.session_id)
    if session and not auth.teacher_can_observe_session(db, teacher, session):
        raise HTTPException(status_code=403, detail=_error("FORBIDDEN_RESOURCE", "Session not visible in your classes"))

    annotation = repo.create(db, TeacherAnnotation(
        teacher_id=teacher.id, student_id=student_id, session_id=session_id, signal_id=signal_id, content=content,
    ))
    db.commit()
    db.refresh(annotation)
    return annotation


def list_annotations(
    db: Session, teacher: User, student_id: Optional[uuid.UUID], session_id: Optional[uuid.UUID],
    signal_id: Optional[uuid.UUID], created_from: Optional[datetime], created_to: Optional[datetime], skip: int, limit: int,
):
    return repo.list_for_teacher(db, teacher.id, student_id, session_id, signal_id, created_from, created_to, skip, limit)


def _owned_annotation(db: Session, teacher: User, annotation_id: uuid.UUID) -> TeacherAnnotation:
    annotation = repo.get_active(db, annotation_id)
    if not annotation:
        raise HTTPException(status_code=404, detail=_error("ANNOTATION_NOT_FOUND", "Annotation not found"))
    if annotation.teacher_id != teacher.id:
        raise HTTPException(status_code=403, detail=_error("ANNOTATION_FORBIDDEN", "Only the author can change this annotation"))
    return annotation


def update_annotation(db: Session, teacher: User, annotation_id: uuid.UUID, content: str) -> TeacherAnnotation:
    annotation = _owned_annotation(db, teacher, annotation_id)
    annotation.content = content
    annotation.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(annotation)
    return annotation


def delete_annotation(db: Session, teacher: User, annotation_id: uuid.UUID) -> None:
    # D7: soft delete; the row is kept and excluded from every read
    annotation = _owned_annotation(db, teacher, annotation_id)
    annotation.deleted_at = datetime.now(timezone.utc)
    db.commit()
