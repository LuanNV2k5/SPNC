"""Phase 09A — Teacher Observation read service (docs/35 §4 09A).

Every function authorizes through app.services.observation_auth before reading.
Read-only: nothing here mutates data.
"""
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.exam import ExamStatus, ParticipationStatus
from app.models.session import CodingSession, SessionStatus
from app.models.user import User
from app.repositories import observation as repo
from app.repositories import trace as trace_repo
from app.services import observation_auth as auth
from app.services.storage import storage_adapter


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def _value(v):
    return getattr(v, "value", v)


def _session_item(s: CodingSession, d: dict) -> dict:
    return {
        "id": s.id,
        "problem_id": s.problem_id,
        "problem_title": d["problem_title"],
        "context": "EXAM" if s.is_exam_context else "PRACTICE",
        "exam_id": d["exam_id"],
        "exam_title": d["exam_title"],
        "opened_at": s.opened_at,
        "first_code_at": s.first_code_at,
        "ended_at": s.ended_at,
        "status": _value(s.status),
        "termination_source": _value(s.termination_source),
        "latest_meaningful_event_at": d["latest_meaningful_event_at"],
        "latest_submission_verdict": _value(d["latest_submission_verdict"]),
        "signal_count": d["signal_count"],
        "final_loc": s.final_loc,
        "working_time_seconds": s.working_time_seconds,
    }


def list_attention(db: Session, teacher: User, class_id: uuid.UUID, skip: int, limit: int):
    """REQ-OBS-001: students with NEW signals on sessions visible in this class."""
    auth.authorize_class(db, teacher, class_id)
    per_student = defaultdict(lambda: {"counts_by_type": {}, "new_signal_count": 0, "latest_detected_at": None})
    for student_id, signal_type, count, latest in repo.attention_rows(db, class_id, teacher.id):
        entry = per_student[student_id]
        entry["counts_by_type"][_value(signal_type)] = count
        entry["new_signal_count"] += count
        if entry["latest_detected_at"] is None or latest > entry["latest_detected_at"]:
            entry["latest_detected_at"] = latest

    ordered = sorted(per_student.items(), key=lambda kv: (kv[1]["latest_detected_at"], str(kv[0])), reverse=True)
    page = ordered[skip:skip + limit]
    users = repo.get_users(db, [sid for sid, _ in page])
    items = [{
        "student_id": sid,
        "username": users[sid].username,
        "full_name": users[sid].full_name,
        **entry,
    } for sid, entry in page]
    return items, len(ordered)


def list_student_sessions(db: Session, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID, skip: int, limit: int):
    """REQ-OBS-002."""
    auth.authorize_student(db, teacher, class_id, student_id)
    sessions, total = repo.visible_sessions_for_student(db, class_id, teacher.id, student_id, skip, limit)
    details = repo.session_details(db, [s.id for s in sessions])
    return [_session_item(s, details[s.id]) for s in sessions], total


def get_timeline(db: Session, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID, session_id: uuid.UUID, skip: int, limit: int):
    """REQ-OBS-003 (order per D3: sequence_number, server_timestamp on every event)."""
    session = auth.authorize_session(db, teacher, class_id, student_id, session_id)
    events, total = trace_repo.get_paginated_history(db, session_id, skip, limit)
    highest, next_expected = trace_repo.get_trace_state(db, session_id)
    details = repo.session_details(db, [session.id])
    return {
        "session": _session_item(session, details[session.id]),
        "events": events,
        "total_events": total,
        "skip": skip,
        "limit": limit,
        "state": {"highest_contiguous_sequence": highest, "next_expected_sequence": next_expected},
        "signals": repo.signals_for_session(db, session_id),
        "snapshots": repo.snapshots_for_session(db, session_id),
        "runs": repo.runs_for_session(db, session_id),
    }


def get_snapshot(db: Session, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID, session_id: uuid.UUID, snapshot_id: uuid.UUID):
    """REQ-OBS-004."""
    auth.authorize_session(db, teacher, class_id, student_id, session_id)
    snap = repo.get_snapshot_in_session(db, session_id, snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail=_error("SNAPSHOT_NOT_FOUND", "Snapshot not found in this session"))
    available = storage_adapter.exists_code_snapshot(snap.object_key)
    return {
        "id": snap.id,
        "session_id": snap.session_id,
        "reason": _value(snap.reason),
        "language": snap.language,
        "line_count": snap.line_count,
        "created_at": snap.created_at,
        "source_code": storage_adapter.download_code_snapshot(snap.object_key) if available else None,
        "content_available": available,
    }


def list_session_runs(db: Session, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID, session_id: uuid.UUID):
    """RBAC Run READ OWN_CLASS (replaces the unscoped teacher branch removed from RunService, docs/35 F1)."""
    auth.authorize_session(db, teacher, class_id, student_id, session_id)
    runs = repo.runs_for_session(db, session_id)
    return runs, len(runs)


def list_student_signals(
    db: Session, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID,
    status: Optional[str], session_id: Optional[uuid.UUID], signal_type: Optional[str], skip: int, limit: int,
):
    auth.authorize_student(db, teacher, class_id, student_id)
    return repo.visible_signals_for_student(db, class_id, teacher.id, student_id, status, session_id, signal_type, skip, limit)


def _derived_participation_status(exam, participation, now: datetime) -> str:
    """docs/36 10B: the stored participation state is authoritative (D8 enum). The docs/35 D6
    derivation remains only for students who never joined, so they read CANCELLED/EXPIRED."""
    if participation is not None:
        return _value(participation.status)
    if _value(exam.status) == ExamStatus.CANCELLED.value:
        return ParticipationStatus.CANCELLED.value
    if now >= exam.end_time:
        return ParticipationStatus.EXPIRED.value
    return ParticipationStatus.NOT_STARTED.value


def get_exam_observation(db: Session, teacher: User, exam_id: uuid.UUID, skip: int, limit: int):
    """REQ-OBS-008."""
    exam = auth.authorize_exam(db, teacher, exam_id)
    students, total = repo.exam_observed_students(db, exam_id, teacher.id, skip, limit)
    participations = repo.exam_participations(db, exam_id, [u.id for u in students])
    sessions_by_part = repo.exam_sessions_by_participation(db, [p.id for p in participations.values()])
    all_session_ids = [s.id for ss in sessions_by_part.values() for s in ss]
    submitted = repo.submitted_problems(db, all_session_ids)
    signals = repo.signal_counts(db, all_session_ids)
    runs = repo.run_counts(db, all_session_ids)
    activity = repo.latest_activity(db, all_session_ids)
    now = datetime.now(timezone.utc)

    items = []
    for u in students:
        p = participations.get(u.id)
        sessions = sessions_by_part.get(p.id, []) if p else []
        active = next((s for s in sessions if _value(s.status) == SessionStatus.ACTIVE.value), None)
        items.append({
            "student_id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "participation_status": _derived_participation_status(exam, p, now),
            "started_at": p.started_at if p else None,
            "completed_at": p.completed_at if p else None,
            "submitted_problem_count": len(set().union(*(submitted.get(s.id, set()) for s in sessions))),
            "current_session": {
                "id": active.id,
                "problem_id": active.problem_id,
                "opened_at": active.opened_at,
                "latest_activity_at": activity.get(active.id),
                "run_count": runs.get(active.id, 0),
            } if active else None,
            "signal_count": sum(signals.get(s.id, 0) for s in sessions),
        })
    return exam, items, total
