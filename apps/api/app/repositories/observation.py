"""Phase 09 — Teacher Observation queries (read-only)."""
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.models.class_org import ClassMembership
from app.models.exam import Exam, ExamAssignment, ExamParticipation
from app.models.observation import AttentionSignal, SignalStatus
from app.models.problem import Problem
from app.models.run_submit import Run, Submission
from app.models.session import CodingSession
from app.models.trace import CodeSnapshot, TraceEvent, TraceEventType
from app.models.class_org import Class
from app.models.user import User
from app.services.observation_auth import session_visible_in_class_clause

# Same closed set as IDLE detection (docs/01_DOMAIN.md DTI-09)
MEANINGFUL_EVENT_TYPES = (
    TraceEventType.EDITOR_CHANGED.value,
    TraceEventType.RUN_REQUESTED.value,
    TraceEventType.SUBMISSION_CREATED.value,
)


def attention_rows(db: Session, class_id: uuid.UUID, teacher_id: uuid.UUID) -> List[Tuple[uuid.UUID, str, int, datetime]]:
    """(student_id, signal_type, count, latest_detected_at) for NEW signals on sessions visible in the class."""
    stmt = (
        select(AttentionSignal.student_id, AttentionSignal.signal_type,
               func.count(AttentionSignal.id), func.max(AttentionSignal.detected_at))
        .join(CodingSession, CodingSession.id == AttentionSignal.session_id)
        .join(ClassMembership, and_(
            ClassMembership.student_id == AttentionSignal.student_id,
            ClassMembership.class_id == class_id,
            ClassMembership.is_active == True,
        ))
        .where(and_(
            AttentionSignal.status == SignalStatus.NEW.value,
            session_visible_in_class_clause(class_id, teacher_id),
        ))
        .group_by(AttentionSignal.student_id, AttentionSignal.signal_type)
    )
    return [tuple(r) for r in db.execute(stmt).all()]


def get_users(db: Session, user_ids: List[uuid.UUID]) -> Dict[uuid.UUID, User]:
    if not user_ids:
        return {}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}


def visible_sessions_for_student(
    db: Session, class_id: uuid.UUID, teacher_id: uuid.UUID, student_id: uuid.UUID, skip: int, limit: int
) -> Tuple[List[CodingSession], int]:
    where = and_(
        CodingSession.student_id == student_id,
        session_visible_in_class_clause(class_id, teacher_id),
    )
    total = db.scalar(select(func.count(CodingSession.id)).where(where)) or 0
    items = db.scalars(
        select(CodingSession).where(where)
        .order_by(desc(CodingSession.opened_at), desc(CodingSession.id))
        .offset(skip).limit(limit)
    ).all()
    return list(items), total


def session_details(db: Session, session_ids: List[uuid.UUID]) -> Dict[uuid.UUID, dict]:
    """Batch-loads the derived fields of REQ-OBS-002 for the given sessions."""
    if not session_ids:
        return {}
    details = {sid: {"problem_title": "", "exam_id": None, "exam_title": None,
                     "latest_meaningful_event_at": None, "latest_submission_verdict": None,
                     "signal_count": 0} for sid in session_ids}

    for sid, title in db.execute(
        select(CodingSession.id, Problem.title)
        .join(Problem, Problem.id == CodingSession.problem_id)
        .where(CodingSession.id.in_(session_ids))
    ).all():
        details[sid]["problem_title"] = title

    for sid, exam_id, exam_title in db.execute(
        select(CodingSession.id, Exam.id, Exam.title)
        .join(ExamParticipation, ExamParticipation.id == CodingSession.exam_participation_id)
        .join(Exam, Exam.id == ExamParticipation.exam_id)
        .where(CodingSession.id.in_(session_ids))
    ).all():
        details[sid]["exam_id"] = exam_id
        details[sid]["exam_title"] = exam_title

    for sid, latest in db.execute(
        select(TraceEvent.session_id, func.max(TraceEvent.server_timestamp))
        .where(and_(TraceEvent.session_id.in_(session_ids), TraceEvent.event_type.in_(MEANINGFUL_EVENT_TYPES)))
        .group_by(TraceEvent.session_id)
    ).all():
        details[sid]["latest_meaningful_event_at"] = latest

    latest_sub = (
        select(Submission.session_id, Submission.verdict,
               func.row_number().over(partition_by=Submission.session_id,
                                      order_by=(desc(Submission.created_at), desc(Submission.id))).label("rn"))
        .where(Submission.session_id.in_(session_ids))
        .subquery()
    )
    for sid, verdict in db.execute(select(latest_sub.c.session_id, latest_sub.c.verdict).where(latest_sub.c.rn == 1)).all():
        details[sid]["latest_submission_verdict"] = verdict

    for sid, count in db.execute(
        select(AttentionSignal.session_id, func.count(AttentionSignal.id))
        .where(AttentionSignal.session_id.in_(session_ids))
        .group_by(AttentionSignal.session_id)
    ).all():
        details[sid]["signal_count"] = count

    return details


def signals_for_session(db: Session, session_id: uuid.UUID) -> List[AttentionSignal]:
    return list(db.scalars(
        select(AttentionSignal).where(AttentionSignal.session_id == session_id)
        .order_by(AttentionSignal.detected_at, AttentionSignal.id)
    ).all())


def snapshots_for_session(db: Session, session_id: uuid.UUID) -> List[CodeSnapshot]:
    return list(db.scalars(
        select(CodeSnapshot).where(CodeSnapshot.session_id == session_id)
        .order_by(CodeSnapshot.created_at, CodeSnapshot.id)
    ).all())


def get_snapshot_in_session(db: Session, session_id: uuid.UUID, snapshot_id: uuid.UUID) -> Optional[CodeSnapshot]:
    return db.scalar(select(CodeSnapshot).where(and_(CodeSnapshot.id == snapshot_id, CodeSnapshot.session_id == session_id)))


def runs_for_session(db: Session, session_id: uuid.UUID) -> List[Run]:
    return list(db.scalars(select(Run).where(Run.session_id == session_id).order_by(Run.created_at, Run.id)).all())


def visible_signals_for_student(
    db: Session, class_id: uuid.UUID, teacher_id: uuid.UUID, student_id: uuid.UUID,
    status: Optional[str], session_id: Optional[uuid.UUID], signal_type: Optional[str], skip: int, limit: int,
) -> Tuple[List[AttentionSignal], int]:
    conditions = [
        AttentionSignal.student_id == student_id,
        session_visible_in_class_clause(class_id, teacher_id),
    ]
    if status:
        conditions.append(AttentionSignal.status == status)
    if session_id:
        conditions.append(AttentionSignal.session_id == session_id)
    if signal_type:
        conditions.append(AttentionSignal.signal_type == signal_type)
    base = select(AttentionSignal).join(CodingSession, CodingSession.id == AttentionSignal.session_id).where(and_(*conditions))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = db.scalars(base.order_by(desc(AttentionSignal.detected_at), desc(AttentionSignal.id)).offset(skip).limit(limit)).all()
    return list(items), total


def exam_observed_students(
    db: Session, exam_id: uuid.UUID, teacher_id: uuid.UUID, skip: int, limit: int
) -> Tuple[List[User], int]:
    """Active members of classes that are assigned to the exam AND owned by the teacher (docs/35 §3)."""
    student_ids = (
        select(ClassMembership.student_id)
        .join(ExamAssignment, ExamAssignment.class_id == ClassMembership.class_id)
        .join(Class, Class.id == ClassMembership.class_id)
        .where(and_(
            ExamAssignment.exam_id == exam_id,
            Class.owner_id == teacher_id,
            ClassMembership.is_active == True,
        ))
        .distinct()
        .subquery()
    )
    where = User.id.in_(select(student_ids.c.student_id))
    total = db.scalar(select(func.count(User.id)).where(where)) or 0
    users = db.scalars(select(User).where(where).order_by(User.username, User.id).offset(skip).limit(limit)).all()
    return list(users), total


def exam_participations(db: Session, exam_id: uuid.UUID, student_ids: List[uuid.UUID]) -> Dict[uuid.UUID, ExamParticipation]:
    if not student_ids:
        return {}
    rows = db.scalars(select(ExamParticipation).where(and_(
        ExamParticipation.exam_id == exam_id, ExamParticipation.student_id.in_(student_ids)
    ))).all()
    return {p.student_id: p for p in rows}


def exam_sessions_by_participation(db: Session, participation_ids: List[uuid.UUID]) -> Dict[uuid.UUID, List[CodingSession]]:
    result: Dict[uuid.UUID, List[CodingSession]] = {pid: [] for pid in participation_ids}
    if not participation_ids:
        return result
    for s in db.scalars(
        select(CodingSession).where(CodingSession.exam_participation_id.in_(participation_ids))
        .order_by(desc(CodingSession.opened_at), desc(CodingSession.id))
    ).all():
        result[s.exam_participation_id].append(s)
    return result


def submitted_problems(db: Session, session_ids: List[uuid.UUID]) -> Dict[uuid.UUID, set]:
    """Problems with at least one Submission, keyed by session (callers union per participation)."""
    result: Dict[uuid.UUID, set] = {}
    if not session_ids:
        return result
    for sid, pid in db.execute(
        select(Submission.session_id, Submission.problem_id)
        .where(Submission.session_id.in_(session_ids))
        .distinct()
    ).all():
        result.setdefault(sid, set()).add(pid)
    return result


def signal_counts(db: Session, session_ids: List[uuid.UUID]) -> Dict[uuid.UUID, int]:
    if not session_ids:
        return {}
    return {sid: c for sid, c in db.execute(
        select(AttentionSignal.session_id, func.count(AttentionSignal.id))
        .where(AttentionSignal.session_id.in_(session_ids))
        .group_by(AttentionSignal.session_id)
    ).all()}


def run_counts(db: Session, session_ids: List[uuid.UUID]) -> Dict[uuid.UUID, int]:
    if not session_ids:
        return {}
    return {sid: c for sid, c in db.execute(
        select(Run.session_id, func.count(Run.id)).where(Run.session_id.in_(session_ids)).group_by(Run.session_id)
    ).all()}


def latest_activity(db: Session, session_ids: List[uuid.UUID]) -> Dict[uuid.UUID, datetime]:
    if not session_ids:
        return {}
    return {sid: ts for sid, ts in db.execute(
        select(TraceEvent.session_id, func.max(TraceEvent.server_timestamp))
        .where(TraceEvent.session_id.in_(session_ids))
        .group_by(TraceEvent.session_id)
    ).all()}
