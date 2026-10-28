"""Phase 10B — Exam lifecycle and timeout finalization (docs/36 §4 10B; D1, D10, D11, D13).

DRAFT -> SCHEDULED (publish) -> ONGOING (start_time) -> ENDED (end_time); DRAFT/SCHEDULED -> CANCELLED.
Every transition locks the exam row and re-checks its state, so concurrent ticks and
re-runs after a crash are no-ops for work already done.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.exam import Exam, ExamAssignment, ExamParticipation, ExamProblem, ExamStatus, ParticipationStatus
from app.models.run_submit import Submission, SubmissionSource
from app.models.session import CodingSession, SessionStatus, TerminationSource
from app.models.trace import CodeSnapshot
from app.models.user import AuditLog, User
from app.repositories import academic as academic_repo
from app.repositories import submission as submission_repo
from app.services.queue import judge_queue
from app.services.exam_access import participant_deadline
from app.services.session_lifecycle import finalize_session
from app.services.submission import record_submission

logger = logging.getLogger(__name__)


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def _value(v) -> str:
    return v if isinstance(v, str) else v.value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lock_exam(db: Session, exam_id: uuid.UUID, skip_locked: bool = False) -> Optional[Exam]:
    stmt = select(Exam).where(Exam.id == exam_id).with_for_update(skip_locked=skip_locked) \
        .execution_options(populate_existing=True)
    return db.scalar(stmt)


def _owned_exam(db: Session, owner: User, exam_id: uuid.UUID) -> Exam:
    exam = _lock_exam(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail=_error("EXAM_NOT_FOUND", "Exam not found"))
    if exam.owner_id != owner.id:
        raise HTTPException(status_code=403, detail=_error("EXAM_FORBIDDEN", "Not your exam"))
    return exam


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

def publish_exam(db: Session, owner: User, exam_id: uuid.UUID) -> Exam:
    """DRAFT -> SCHEDULED after validation (AC-10-05). Flushes only; the router commits."""
    exam = _owned_exam(db, owner, exam_id)
    if _value(exam.status) != ExamStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail=_error("EXAM_NOT_DRAFT", "Only a DRAFT exam can be published"))
    if exam.start_time <= _now():
        raise HTTPException(status_code=422, detail=_error("EXAM_START_IN_PAST", "start_time must be in the future"))
    if not academic_repo.get_exam_class_ids(db, exam.id):
        raise HTTPException(status_code=422, detail=_error("EXAM_NO_CLASS", "Assign at least one class before publishing"))
    problems = academic_repo.get_exam_problems(db, exam.id)
    if not problems:
        raise HTTPException(status_code=422, detail=_error("EXAM_NO_PROBLEM", "Attach at least one problem before publishing"))
    # OQ-09 assumption: every problem must be gradable at publish time
    missing = [str(ep.problem_id) for ep in problems if submission_repo.count_test_cases(db, ep.problem_id) == 0]
    if missing:
        raise HTTPException(status_code=422, detail=_error(
            "EXAM_PROBLEM_WITHOUT_TEST_CASES", f"Problems without test cases: {', '.join(missing)}"))
    exam.status = ExamStatus.SCHEDULED.value
    db.flush()
    return exam


# ---------------------------------------------------------------------------
# Student finalize
# ---------------------------------------------------------------------------

def _active_sessions(db: Session, participation_id: uuid.UUID) -> List[CodingSession]:
    return list(db.scalars(select(CodingSession).where(and_(
        CodingSession.exam_participation_id == participation_id,
        CodingSession.status == SessionStatus.ACTIVE.value,
    )).order_by(CodingSession.opened_at)).all())


def _lock_participation(db: Session, exam_id: uuid.UUID, student_id: uuid.UUID) -> Optional[ExamParticipation]:
    return db.scalar(select(ExamParticipation).where(and_(
        ExamParticipation.exam_id == exam_id, ExamParticipation.student_id == student_id,
    )).with_for_update().execution_options(populate_existing=True))


def finalize_participation(db: Session, student: User, exam_id: uuid.UUID) -> ExamParticipation:
    """IN_PROGRESS -> COMPLETED; ends the student's ACTIVE exam sessions (actor STUDENT), no auto-submit."""
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail=_error("EXAM_NOT_FOUND", "Exam not found"))
    participation = _lock_participation(db, exam_id, student.id)
    if not participation:
        raise HTTPException(status_code=404, detail=_error("PARTICIPATION_NOT_FOUND", "Participation not found"))
    if _value(participation.status) != ParticipationStatus.IN_PROGRESS.value:
        raise HTTPException(status_code=409, detail=_error("PARTICIPATION_NOT_ACTIVE", "Participation is not in progress"))
    # After the participant's deadline the timeout path owns the participation, whatever the scheduler lag
    now = _now()
    if now >= participant_deadline(exam, participation):
        raise HTTPException(status_code=403, detail=_error("EXAM_ENDED", "Exam has ended"))

    for session in _active_sessions(db, participation.id):
        finalize_session(db, session.id, SessionStatus.ENDED, TerminationSource.STUDENT)
    participation.status = ParticipationStatus.COMPLETED.value
    participation.completed_at = now
    db.flush()
    return participation


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

def _assert_cancellable(exam: Exam, ongoing_code: str) -> None:
    status = _value(exam.status)
    if status == ExamStatus.ENDED.value:
        raise HTTPException(status_code=400, detail=_error("INVALID_STATE", "Cannot cancel an ended exam"))
    # A SCHEDULED exam past start_time is running even if the scheduler has not ticked yet
    if status == ExamStatus.ONGOING.value or (status == ExamStatus.SCHEDULED.value and _now() >= exam.start_time):
        raise HTTPException(status_code=409, detail=_error(ongoing_code, "An ongoing exam cannot be cancelled"))


def _apply_cancel(db: Session, exam: Exam, actor_id: uuid.UUID, reason: Optional[str]) -> None:
    now = _now()
    exam.status = ExamStatus.CANCELLED.value
    exam.cancelled_at = now
    exam.cancelled_by = actor_id
    exam.cancel_reason = reason
    # REQ-EXAM-011: open participations become CANCELLED; no submissions are created
    for p in db.scalars(select(ExamParticipation).where(and_(
        ExamParticipation.exam_id == exam.id,
        ExamParticipation.status.in_([ParticipationStatus.NOT_STARTED.value, ParticipationStatus.IN_PROGRESS.value]),
    )).with_for_update()).all():
        p.status = ParticipationStatus.CANCELLED.value
    db.flush()


def cancel_exam(db: Session, owner: User, exam_id: uuid.UUID, reason: str) -> Exam:
    """REQ-EXAM-010/011: owner cancels a DRAFT/SCHEDULED exam, with metadata and AuditLog."""
    exam = _owned_exam(db, owner, exam_id)
    if _value(exam.status) == ExamStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail=_error("EXAM_ALREADY_CANCELLED", "Exam is already cancelled"))
    _assert_cancellable(exam, "EXAM_ONGOING")
    _apply_cancel(db, exam, owner.id, reason)
    db.add(AuditLog(actor_id=owner.id, action="EXAM_CANCELLED", target_type="EXAM", target_id=str(exam.id),
                    metadata_payload={"reason": reason}))
    db.flush()
    return exam


def admin_cancel_exam(db: Session, admin: User, exam_id: uuid.UUID) -> Exam:
    """D13: DRAFT/SCHEDULED only until OQ-23 is decided. Idempotent on CANCELLED (Phase 04)."""
    exam = _lock_exam(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail=_error("EXAM_NOT_FOUND", "Exam not found"))
    if _value(exam.status) == ExamStatus.CANCELLED.value:
        return exam
    _assert_cancellable(exam, "EXAM_ONGOING_CANCEL_UNDECIDED")
    _apply_cancel(db, exam, admin.id, None)
    db.add(AuditLog(actor_id=admin.id, action="EXAM_ADMIN_CANCELLED", target_type="EXAM", target_id=str(exam.id)))
    db.flush()
    return exam


# ---------------------------------------------------------------------------
# Scheduler tick (D10) and timeout finalization (REQ-SESSION-003/004)
# ---------------------------------------------------------------------------

def _timeout_snapshot(db: Session, session: CodingSession, end_time: datetime) -> Optional[CodeSnapshot]:
    """Latest server-received snapshot before the deadline, if newer than the session's last submission (D1)."""
    snapshot = db.scalar(select(CodeSnapshot).where(and_(
        CodeSnapshot.session_id == session.id, CodeSnapshot.created_at < end_time,
    )).order_by(CodeSnapshot.created_at.desc(), CodeSnapshot.id.desc()).limit(1))
    if snapshot is None:
        return None
    last_submitted = db.scalar(
        select(CodeSnapshot.created_at).join(Submission, Submission.snapshot_id == CodeSnapshot.id)
        .where(Submission.session_id == session.id).order_by(CodeSnapshot.created_at.desc()).limit(1)
    )
    if last_submitted is not None and last_submitted >= snapshot.created_at:
        return None
    return snapshot


def expire_participation(db: Session, exam: Exam, participation_id: uuid.UUID) -> List[uuid.UUID]:
    """
    Timeout finalization of one participation, in the caller's transaction:
    auto-submit per session (SUBMISSION_CREATED before SESSION_ENDED), end the session as
    SYSTEM_EXAM_TIMEOUT, then mark the participation EXPIRED. Returns new submission ids.
    """
    participation = db.scalar(select(ExamParticipation).where(ExamParticipation.id == participation_id)
                              .with_for_update().execution_options(populate_existing=True))
    if not participation or _value(participation.status) != ParticipationStatus.IN_PROGRESS.value:
        return []
    deadline = participant_deadline(exam, participation)   # docs/38 D7; end_time without a duration
    created = []
    for session in _active_sessions(db, participation.id):
        locked = academic_repo.lock_session_for_finalize(db, session.id)
        if _value(locked.status) != SessionStatus.ACTIVE.value:
            continue
        snapshot = _timeout_snapshot(db, locked, deadline)
        if snapshot is not None:
            created.append(record_submission(db, locked, snapshot, exam.id, SubmissionSource.SYSTEM_EXAM_TIMEOUT).id)
        finalize_session(db, locked.id, SessionStatus.ENDED, TerminationSource.SYSTEM_EXAM_TIMEOUT)
    participation.status = ParticipationStatus.EXPIRED.value
    participation.expired_at = _now()
    db.flush()
    return created


def _start_due_exams(db: Session, now: datetime) -> int:
    started = 0
    due = db.scalars(select(Exam.id).where(and_(
        Exam.status == ExamStatus.SCHEDULED.value, Exam.start_time <= now))).all()
    for exam_id in due:
        exam = _lock_exam(db, exam_id, skip_locked=True)
        if exam and _value(exam.status) == ExamStatus.SCHEDULED.value and exam.start_time <= now:
            exam.status = ExamStatus.ONGOING.value
            started += 1
        db.commit()
    return started


def _end_due_exams(db: Session, now: datetime) -> Tuple[int, List[uuid.UUID]]:
    ended, submissions = 0, []
    due = db.scalars(select(Exam.id).where(and_(
        Exam.status == ExamStatus.ONGOING.value, Exam.end_time <= now))).all()
    for exam_id in due:
        # One transaction per participation: a crash leaves the rest IN_PROGRESS for the next tick
        participation_ids = db.scalars(select(ExamParticipation.id).where(and_(
            ExamParticipation.exam_id == exam_id,
            ExamParticipation.status == ParticipationStatus.IN_PROGRESS.value))).all()
        for participation_id in participation_ids:
            exam = db.get(Exam, exam_id)
            try:
                new_ids = expire_participation(db, exam, participation_id)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(f"Timeout finalization failed for participation {participation_id}")
                continue
            for sid in new_ids:
                judge_queue.enqueue_submission(sid)
            submissions.extend(new_ids)

        exam = _lock_exam(db, exam_id, skip_locked=True)
        remaining = db.scalar(select(ExamParticipation.id).where(and_(
            ExamParticipation.exam_id == exam_id,
            ExamParticipation.status == ParticipationStatus.IN_PROGRESS.value)).limit(1))
        if exam and _value(exam.status) == ExamStatus.ONGOING.value and remaining is None:
            exam.status = ExamStatus.ENDED.value
            ended += 1
        db.commit()
    return ended, submissions


def _expire_overdue_participants(db: Session, now: datetime) -> List[uuid.UUID]:
    """docs/38 D7: in a running exam, a participant whose own duration ran out is finalized like a timeout."""
    submissions = []
    rows = db.execute(
        select(ExamParticipation.id, ExamParticipation.exam_id).join(Exam, Exam.id == ExamParticipation.exam_id)
        .where(and_(
            Exam.status == ExamStatus.ONGOING.value,
            Exam.duration_minutes.isnot(None),
            ExamParticipation.status == ParticipationStatus.IN_PROGRESS.value,
            ExamParticipation.started_at.isnot(None),
        ))
    ).all()
    for participation_id, exam_id in rows:
        exam = db.get(Exam, exam_id)
        participation = db.get(ExamParticipation, participation_id)
        if participant_deadline(exam, participation) > now:
            continue
        try:
            new_ids = expire_participation(db, exam, participation_id)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(f"Duration finalization failed for participation {participation_id}")
            continue
        for sid in new_ids:
            judge_queue.enqueue_submission(sid)
        submissions.extend(new_ids)
    return submissions


def run_tick(db: Session, now: Optional[datetime] = None) -> dict:
    """One idempotent scheduler pass. An exam whose whole window passed while the scheduler was
    down goes SCHEDULED -> ONGOING -> ENDED within the same tick."""
    now = now or _now()
    started = _start_due_exams(db, now)
    submissions = _expire_overdue_participants(db, now)
    ended, at_end = _end_due_exams(db, now)
    return {"started": started, "ended": ended, "auto_submissions": submissions + at_end}
