"""Phase 10A — Submit and judge (docs/36 §3, §4 10A; D2, D4, D5, D7, D12, D14).

Submit runs in the API process: one transaction creates the Submission, appends the
server-authored SUBMISSION_CREATED event and ends the session (D2), then enqueues.
Judging runs in the worker under the Phase 07 fencing (claim -> grade -> fenced write).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.exam import Exam, ExamParticipation, ExamStatus, ParticipationStatus
from app.models.problem import Problem
from app.models.run_submit import RunStatus, RunVerdict, Submission, SubmissionSource
from app.models.session import SessionStatus, TerminationSource
from app.models.trace import CodeSnapshot, TraceEvent, TraceEventType
from app.models.user import User
from app.repositories import academic as academic_repo
from app.repositories import submission as submission_repo
from app.repositories import trace as trace_repo
from app.services.exam_access import assert_participant_open
from app.services.judge.grader import grade
from app.services.points import award_for_submission
from app.services.queue import judge_queue
from app.services.session_lifecycle import finalize_session
from app.services.storage import StorageUnavailable, storage_adapter
from app.services.trace import _generate_fingerprint

logger = logging.getLogger(__name__)

PRACTICE_SCORE_BASE = 100

_CASE_FIELDS = ("testcase_id", "order_index", "is_sample", "verdict", "passed", "execution_time_ms", "memory_used_kb")
_SAMPLE_FIELDS = ("input", "expected_output", "stdout", "stderr")
_SUMMARY_FIELDS = ("passed_count", "total_count", "passed_weight", "total_weight", "score_base",
                   "time_limit_ms", "memory_limit_mb", "compile_error_message")


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def _value(v) -> str:
    return v if isinstance(v, str) else v.value


# ---------------------------------------------------------------------------
# Submit (API)
# ---------------------------------------------------------------------------

def _check_exam_window(db: Session, participation_id: uuid.UUID) -> uuid.UUID:
    """DI-8 / REQ-EXAM-012: participation IN_PROGRESS and the exam open per D11."""
    participation = db.get(ExamParticipation, participation_id)
    if not participation or _value(participation.status) != ParticipationStatus.IN_PROGRESS.value:
        raise HTTPException(status_code=403, detail=_error("PARTICIPATION_NOT_ACTIVE", "Participation is not in progress"))
    exam = db.get(Exam, participation.exam_id)
    assert_participant_open(exam, participation, datetime.now(timezone.utc))   # D11 + docs/38 D7 deadline
    return exam.id


def record_submission(db: Session, session, snapshot: CodeSnapshot, exam_id: Optional[uuid.UUID],
                      source: SubmissionSource) -> Submission:
    """Creates the PENDING Submission and its server-authored SUBMISSION_CREATED event (REQ-TRACE-012).
    The caller holds the session lock, finalizes the session afterwards and owns the commit."""
    submission = submission_repo.create(db, Submission(
        student_id=session.student_id,
        problem_id=session.problem_id,
        session_id=session.id,
        snapshot_id=snapshot.id,
        exam_id=exam_id,
        source=source.value,
        status=RunStatus.PENDING.value,
    ))
    # Same pattern as SESSION_ENDED (Phase 08E): sequence max + 1, server clock
    now = datetime.now(timezone.utc)
    payload = {"source": "SERVER", "submission_id": str(submission.id), "code_snapshot_id": str(snapshot.id)}
    if source != SubmissionSource.STUDENT:
        payload["submission_source"] = source.value
    trace_repo.append_server_event(db, TraceEvent(
        session_id=session.id,
        sequence_number=trace_repo.get_max_sequence(db, session.id) + 1,
        event_type=TraceEventType.SUBMISSION_CREATED.value,
        canonical_fingerprint=_generate_fingerprint(TraceEventType.SUBMISSION_CREATED.value, payload),
        client_timestamp=now,
        server_timestamp=now,
        payload=payload,
    ))
    return submission


def create_submission(db: Session, student: User, session_id: uuid.UUID, snapshot_id: uuid.UUID) -> Submission:
    # FOR UPDATE: serializes against trace ingest and a concurrent end/submit of the same session
    session = academic_repo.lock_session_for_finalize(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_error("SESSION_NOT_FOUND", "Session not found"))
    if session.student_id != student.id:
        raise HTTPException(status_code=403, detail=_error("SESSION_FORBIDDEN", "Not your session"))
    if _value(session.status) != SessionStatus.ACTIVE.value:
        raise HTTPException(status_code=403, detail=_error("SUBMISSION_SESSION_NOT_ACTIVE", "Session is not active"))

    snapshot = db.get(CodeSnapshot, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=_error("SUBMISSION_SNAPSHOT_NOT_FOUND", "Snapshot not found"))
    if snapshot.session_id != session.id:
        raise HTTPException(status_code=403, detail=_error("SUBMISSION_SNAPSHOT_INVALID", "Snapshot does not belong to this session"))

    exam_id = _check_exam_window(db, session.exam_participation_id) if session.is_exam_context else None

    if submission_repo.count_test_cases(db, session.problem_id) == 0:
        raise HTTPException(status_code=422, detail=_error("PROBLEM_HAS_NO_TEST_CASES", "Problem has no test cases to judge against"))

    submission = record_submission(db, session, snapshot, exam_id, SubmissionSource.STUDENT)

    # D2: submit ends the session; a further attempt opens a new session
    finalize_session(db, session.id, SessionStatus.ENDED, TerminationSource.STUDENT)

    db.commit()
    db.refresh(submission)
    # A lost enqueue is harmless: the reconciler re-enqueues stale PENDING submissions
    judge_queue.enqueue_submission(submission.id)
    return submission


# ---------------------------------------------------------------------------
# Judge (worker)
# ---------------------------------------------------------------------------

def _fail(db: Session, submission_id: uuid.UUID, generation: int, message: str) -> bool:
    written = submission_repo.write_result(
        db, submission_id, generation, RunStatus.FAILED_INTERNAL, RunVerdict.INTERNAL_ERROR.value, None,
        {"internal_error": message},
    )
    db.commit()
    return written


def judge_submission(db: Session, submission_id: uuid.UUID, adapters: Optional[Mapping[str, Any]] = None) -> bool:
    """Claims, grades and writes one submission. Returns True only if this call persisted a result."""
    if adapters is None:
        from app.services.judge.adapters import ADAPTERS
        adapters = ADAPTERS

    submission = submission_repo.claim_for_judging(db, submission_id)
    if not submission:
        logger.info(f"Worker skipped submission {submission_id}, either not PENDING or CAS failed.")
        return False
    generation = submission.execution_generation

    try:
        snapshot = db.get(CodeSnapshot, submission.snapshot_id)
        adapter = adapters.get(snapshot.language)
        if not adapter:
            return _fail(db, submission_id, generation, f"Unsupported language: {snapshot.language}")
        # Never grade fabricated code: missing content is an internal failure, not empty source
        try:
            available = storage_adapter.exists_code_snapshot(snapshot.object_key)
            source_code = storage_adapter.download_code_snapshot(snapshot.object_key) if available else None
        except StorageUnavailable:
            available = False
        if not available:
            return _fail(db, submission_id, generation, "Snapshot content unavailable")

        test_cases = submission_repo.load_test_cases(db, submission.problem_id)
        if not test_cases:
            return _fail(db, submission_id, generation, "Problem has no test cases")

        if submission.exam_id:
            score_base = submission_repo.exam_max_score(db, submission.exam_id, submission.problem_id)
            if score_base is None:
                return _fail(db, submission_id, generation, "Problem is no longer part of the exam")
        else:
            score_base = PRACTICE_SCORE_BASE

        problem = db.get(Problem, submission.problem_id)
        outcome = grade(adapter, source_code, test_cases, score_base, problem.time_limit_ms, problem.memory_limit_mb)
    except Exception:
        logger.exception(f"Unhandled error judging submission {submission_id}")
        db.rollback()
        return _fail(db, submission_id, generation, "Judge error")

    if outcome["internal_error"]:
        status, score = RunStatus.FAILED_INTERNAL, None
    else:
        status, score = RunStatus.COMPLETED, outcome["score"]
    written = submission_repo.write_result(
        db, submission.id, generation, status, outcome["verdict"].value, score, outcome["judge_result"],
    )
    if not written:
        # A newer generation owns this submission (reconciler recovery); drop the stale result
        db.rollback()
        logger.info(f"Stale result for submission {submission_id} generation {generation} rejected")
        return False
    if submission.exam_id:
        submission_repo.recompute_exam_total(db, submission.exam_id, submission.student_id)
    elif status == RunStatus.COMPLETED:
        # Phase 14 (OQ-16): practice points, same transaction as the fenced write
        award_for_submission(db, submission, outcome["verdict"].value)
    db.commit()
    return True


def recover_stale_submissions(db: Session, threshold_seconds: int) -> int:
    """Reconciler sweep: bump generation of stuck PENDING/RUNNING submissions and re-enqueue."""
    recovered = 0
    for sub in submission_repo.get_stale(db, threshold_seconds):
        logger.info(f"Attempting to recover stale submission: {sub.id} (Status: {sub.status})")
        fresh = submission_repo.recover_stale(db, sub.id, sub.execution_generation)
        if fresh:
            judge_queue.enqueue_submission(fresh.id)
            recovered += 1
        else:
            logger.info(f"Failed to claim stale submission {sub.id} (already recovered by another process)")
    return recovered


# ---------------------------------------------------------------------------
# Student read (D7, D14)
# ---------------------------------------------------------------------------

def student_judge_result(judge_result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """D7: per-case verdict/time/memory for all cases; I/O only for samples (whitelist)."""
    if not judge_result:
        return None
    if "testcases" not in judge_result:
        return {"internal_error": True}
    cases = []
    for case in judge_result["testcases"]:
        entry = {k: case.get(k) for k in _CASE_FIELDS}
        if case.get("is_sample"):
            entry.update({k: case.get(k) for k in _SAMPLE_FIELDS})
        cases.append(entry)
    view = {k: judge_result.get(k) for k in _SUMMARY_FIELDS}
    view["testcases"] = cases
    return view


def result_visible_to_student(db: Session, submission: Submission) -> bool:
    """D14: practice always; exam only after ENDED and with allow_view_result_after."""
    if submission.exam_id is None:
        return True
    exam = db.get(Exam, submission.exam_id)
    return _value(exam.status) == ExamStatus.ENDED.value and bool(exam.allow_view_result_after)


def to_student_response(db: Session, submission: Submission) -> Dict[str, Any]:
    visible = result_visible_to_student(db, submission)
    return {
        "id": submission.id,
        "student_id": submission.student_id,
        "problem_id": submission.problem_id,
        "session_id": submission.session_id,
        "snapshot_id": submission.snapshot_id,
        "exam_id": submission.exam_id,
        "source": _value(submission.source),
        "status": _value(submission.status),
        "verdict": submission.verdict if visible else None,
        "score": submission.score if visible else None,
        "judge_result": student_judge_result(submission.judge_result) if visible else None,
        "result_visible": visible,
        "created_at": submission.created_at,
    }
