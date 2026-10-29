"""Phase 10B — Exam timeout finalization (docs/36 §4 10B; AC-10-07, invariant 2, D1).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.exam import Exam, ExamParticipation
from app.models.run_submit import Submission
from app.models.session import CodingSession
from app.models.trace import CodeSnapshot, TraceEvent, TraceEventType
from app.models.user import User
from app.services import exam_lifecycle
from tests.api.test_exam_lifecycle import _class_with, _draft, _exam_session, _set
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _judge, _snapshot, _submit, client,
    clean_db, db, enqueued, setup_database, world,
)


@pytest.fixture
def running(db, world):
    """ONGOING exam joined by stu and stu2; returns w plus eid and participation ids."""
    w = world
    stu2 = db.scalar(select(User).where(User.username == "stu2"))
    cid = _class_with(w, w["student_id"], stu2.id)
    eid = _draft(w, cid=cid, pid=w["pid"])
    assert client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"]).status_code == 200
    now = datetime.now(timezone.utc)
    _set(eid, start_time=now - timedelta(minutes=5), end_time=now + timedelta(minutes=60), status="ONGOING")
    p1 = client.post(f"/api/v1/my/exams/{eid}/start", headers=w["h_s"]).json()["id"]
    p2 = client.post(f"/api/v1/my/exams/{eid}/start", headers=w["h_s2"]).json()["id"]
    return {**w, "eid": eid, "p1": p1, "p2": p2}


def _session_for(w, part_id, h):
    r = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}", json={"problem_id": w["pid"], "language": "PYTHON3"},
                    headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _end_now(eid, end=None):
    end = end or datetime.now(timezone.utc)   # after every snapshot already committed by the test
    _set(eid, start_time=end - timedelta(hours=1), end_time=end)


def _tick():
    with TestingSessionLocal() as s:
        return exam_lifecycle.run_tick(s)


def test_timeout_auto_submits_latest_snapshot_and_expires(db, running, enqueued):
    w = running
    with_code = _exam_session(w, w["p1"])
    _snapshot(w["h_s"], with_code, "WRONG\n")
    latest = _snapshot(w["h_s"], with_code, "SUM\n")
    # docs/41 R4: one active session per participation and problem, so the session without code is stu2's
    no_code = _session_for(w, w["p2"], w["h_s2"])
    _end_now(w["eid"])
    enqueued.clear()

    result = _tick()
    assert result["ended"] == 1 and len(result["auto_submissions"]) == 1
    assert enqueued == result["auto_submissions"]

    sub = db.get(Submission, result["auto_submissions"][0])
    assert sub.source == "SYSTEM_EXAM_TIMEOUT" and str(sub.snapshot_id) == latest
    assert str(sub.session_id) == with_code and str(sub.exam_id) == w["eid"] and sub.status == "PENDING"

    for sid in (with_code, no_code):
        s = db.get(CodingSession, uuid.UUID(sid))
        assert s.status == "ENDED" and s.termination_source == "SYSTEM_EXAM_TIMEOUT"
    # D1: no snapshot -> no submission
    assert db.scalars(select(Submission).where(Submission.session_id == uuid.UUID(no_code))).all() == []

    # Event order: SUBMISSION_CREATED, then SESSION_ENDED last (docs/34)
    events = db.scalars(select(TraceEvent).where(TraceEvent.session_id == uuid.UUID(with_code))
                        .order_by(TraceEvent.sequence_number)).all()
    assert [e.event_type for e in events][-2:] == [TraceEventType.SUBMISSION_CREATED.value, TraceEventType.SESSION_ENDED.value]
    assert events[-2].payload == {"source": "SERVER", "submission_id": str(sub.id), "code_snapshot_id": latest,
                                  "submission_source": "SYSTEM_EXAM_TIMEOUT"}
    assert events[-1].payload["termination_actor"] == "SYSTEM_EXAM_TIMEOUT"

    for pid in (w["p1"], w["p2"]):
        p = db.get(ExamParticipation, uuid.UUID(pid))
        assert p.status == "EXPIRED" and p.expired_at is not None
    assert db.get(Exam, uuid.UUID(w["eid"])).status == "ENDED"

    # Re-running is a no-op
    assert _tick() == {"started": 0, "ended": 0, "auto_submissions": []}
    assert len(db.scalars(select(Submission)).all()) == 1

    # The auto-submission judges like any other and counts for D5
    assert _judge(sub.id) is True
    db.expire_all()
    assert db.get(Submission, sub.id).score == 40                      # ExamProblem.max_score
    assert db.get(ExamParticipation, uuid.UUID(w["p1"])).total_score == 40


def test_timeout_never_uses_snapshots_received_after_end_time(db, running):
    w = running
    sid = _exam_session(w, w["p1"])
    before = _snapshot(w["h_s"], sid, "WRONG\n")
    after = _snapshot(w["h_s"], sid, "SUM\n")
    t_before = db.get(CodeSnapshot, uuid.UUID(before)).created_at
    t_after = db.get(CodeSnapshot, uuid.UUID(after)).created_at
    assert t_before < t_after
    _end_now(w["eid"], end=t_before + (t_after - t_before) / 2)

    result = _tick()
    assert [str(db.get(Submission, i).snapshot_id) for i in result["auto_submissions"]] == [before]


def test_timeout_only_snapshot_after_end_means_no_submission(db, running):
    w = running
    sid = _exam_session(w, w["p1"])
    snap = _snapshot(w["h_s"], sid, "SUM\n")
    _end_now(w["eid"], end=db.get(CodeSnapshot, uuid.UUID(snap)).created_at - timedelta(milliseconds=1))
    assert _tick()["auto_submissions"] == []
    assert db.get(CodingSession, uuid.UUID(sid)).status == "ENDED"


def test_timeout_skips_already_submitted_sessions(db, running):
    """A student submit ends its session (D2), so the timeout never re-submits it."""
    w = running
    sid = _exam_session(w, w["p1"])
    assert _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n")).status_code == 201
    _end_now(w["eid"])
    assert _tick()["auto_submissions"] == []
    assert len(db.scalars(select(Submission)).all()) == 1


def test_timeout_resumes_after_crash_without_duplicates(db, running, monkeypatch, enqueued):
    w = running
    s1 = _exam_session(w, w["p1"])
    _snapshot(w["h_s"], s1, "SUM\n")
    s2 = _session_for(w, w["p2"], w["h_s2"])
    _snapshot(w["h_s2"], s2, "SUM\n")
    _end_now(w["eid"])

    real = exam_lifecycle.expire_participation
    calls = {"n": 0}

    def crash_on_second(db_, exam, participation_id):
        calls["n"] += 1
        created = real(db_, exam, participation_id)
        if calls["n"] == 2:
            raise RuntimeError("worker died mid-participation")
        return created

    monkeypatch.setattr(exam_lifecycle, "expire_participation", crash_on_second)
    first = _tick()
    assert first["ended"] == 0 and len(first["auto_submissions"]) == 1
    db.expire_all()
    assert db.get(Exam, uuid.UUID(w["eid"])).status == "ONGOING"
    assert sorted(db.get(ExamParticipation, uuid.UUID(p)).status for p in (w["p1"], w["p2"])) == ["EXPIRED", "IN_PROGRESS"]

    monkeypatch.setattr(exam_lifecycle, "expire_participation", real)
    second = _tick()
    assert second["ended"] == 1 and len(second["auto_submissions"]) == 1
    db.expire_all()
    subs = db.scalars(select(Submission)).all()
    assert len(subs) == 2 and {str(s.session_id) for s in subs} == {s1, s2}
    assert db.get(Exam, uuid.UUID(w["eid"])).status == "ENDED"


def test_observation_reads_stored_participation_state(db, running):
    w = running
    _end_now(w["eid"])
    _tick()
    items = client.get(f"/api/v1/exams/{w['eid']}/observation", headers=w["h_t"]).json()["items"]
    assert {i["participation_status"] for i in items} == {"EXPIRED"}
