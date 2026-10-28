"""Phase 12B — Exam edit lock, per-student duration, post-deadline cutoff (docs/38 D6-D8; AC-12-06..08).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test).
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.models.exam import ExamParticipation
from app.models.run_submit import Submission
from app.models.session import CodingSession
from app.models.trace import CodeSnapshot
from app.models.user import User
from app.services import exam_lifecycle
from tests.api.test_exam_lifecycle import _class_with, _draft, _set
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _snapshot, _submit, client,
    clean_db, db, enqueued, setup_database, world,
)


def _iso(minutes):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _running_exam(db, w, duration=None, students=("stu",)):
    """ONGOING exam (window -5 min .. +115 min) joined by the given students; returns eid and participation ids."""
    ids = [db.scalar(select(User).where(User.username == u)).id for u in students]
    cid = _class_with(w, *ids)
    extra = {"duration_minutes": duration} if duration else {}
    eid = _draft(w, start=60, end=180, cid=cid, pid=w["pid"], **extra)
    assert client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"]).status_code == 200
    now = datetime.now(timezone.utc)
    _set(eid, start_time=now - timedelta(minutes=5), end_time=now + timedelta(minutes=115), status="ONGOING")
    headers = {"stu": w["h_s"], "stu2": w["h_s2"]}
    parts = {u: client.post(f"/api/v1/my/exams/{eid}/start", headers=headers[u]).json()["id"] for u in students}
    return eid, parts


def _exam_session(w, part_id, h):
    r = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}", json={"problem_id": w["pid"], "language": "PYTHON3"}, headers=h)
    return r


def _started(part_id, started_at):
    with TestingSessionLocal() as s:
        s.execute(text("UPDATE exam_participations SET started_at = :t WHERE id = :id"), {"t": started_at, "id": part_id})
        s.commit()


# ---------------------------------------------------------------------------
# AC-12-06 — edit lock
# ---------------------------------------------------------------------------
def test_exam_editable_only_while_draft(db, world):
    w = world
    cid = _class_with(w, w["student_id"])
    other_cid = _class_with(w)
    p2 = client.post("/api/v1/problems", json={"title": "P2", "description": "d", "visibility": "PUBLIC",
                                               "supported_languages": ["PYTHON3"]}, headers=w["h_t"]).json()["id"]
    eid = _draft(w, cid=cid, pid=w["pid"])
    assert client.patch(f"/api/v1/exams/{eid}", json={"title": "Draft edit"}, headers=w["h_t"]).status_code == 200
    assert client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"]).status_code == 200

    attempts = lambda: (  # noqa: E731
        client.patch(f"/api/v1/exams/{eid}", json={"title": "x"}, headers=w["h_t"]),
        client.patch(f"/api/v1/exams/{eid}", json={"end_time": _iso(500)}, headers=w["h_t"]),
        client.patch(f"/api/v1/exams/{eid}", json={"title": "x", "allow_view_result_after": True}, headers=w["h_t"]),
        client.post(f"/api/v1/exams/{eid}/problems", json={"problem_id": p2, "order_index": 2}, headers=w["h_t"]),
        client.delete(f"/api/v1/exams/{eid}/problems/{w['pid']}", headers=w["h_t"]),
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": other_cid}, headers=w["h_t"]),
        client.delete(f"/api/v1/exams/{eid}/classes/{cid}", headers=w["h_t"]),
    )
    for status in ("SCHEDULED", "ONGOING", "ENDED", "CANCELLED"):
        _set(eid, status=status)
        for r in attempts():
            assert r.status_code == 409, (status, r.text)
            assert r.json()["error_code"] == "EXAM_NOT_EDITABLE"
        # D6 exception: result visibility stays editable, except once cancelled
        r = client.patch(f"/api/v1/exams/{eid}", json={"allow_view_result_after": True}, headers=w["h_t"])
        assert r.status_code == (409 if status == "CANCELLED" else 200), (status, r.text)


# ---------------------------------------------------------------------------
# AC-12-07 — duration
# ---------------------------------------------------------------------------
def test_duration_validation(world):
    w = world
    body = {"title": "E", "start_time": _iso(60), "end_time": _iso(120)}
    r = client.post("/api/v1/exams", json={**body, "duration_minutes": 45}, headers=w["h_t"])
    assert r.status_code == 201 and r.json()["duration_minutes"] == 45
    too_long = client.post("/api/v1/exams", json={**body, "duration_minutes": 61}, headers=w["h_t"])
    assert too_long.status_code == 422 and too_long.json()["error_code"] == "EXAM_DURATION_TOO_LONG"
    assert client.post("/api/v1/exams", json={**body, "duration_minutes": 0}, headers=w["h_t"]).status_code == 422
    eid = r.json()["id"]
    assert client.patch(f"/api/v1/exams/{eid}", json={"duration_minutes": 61}, headers=w["h_t"]).status_code == 422
    assert client.patch(f"/api/v1/exams/{eid}", json={"duration_minutes": 30}, headers=w["h_t"]).json()["duration_minutes"] == 30


def test_participant_deadline_blocks_every_write(db, world):
    """Window still open, but the student's own 30 minutes are over (D7) -> nothing is accepted (D8)."""
    w = world
    eid, parts = _running_exam(db, w, duration=30)
    part = parts["stu"]
    sid = _exam_session(w, part, w["h_s"]).json()["id"]
    snap = _snapshot(w["h_s"], sid, "SUM\n")                       # accepted while time remains
    _started(part, datetime.now(timezone.utc) - timedelta(minutes=31))

    def expect_ended(r):
        assert r.status_code == 403, r.text
        assert r.json()["error_code"] == "EXAM_ENDED"

    expect_ended(_submit(w["h_s"], sid, snap))
    expect_ended(_exam_session(w, part, w["h_s"]))
    expect_ended(client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots", json={
        "reason": "RUN", "language": "PYTHON3", "source_code": "late\n", "line_count": 1}, headers=w["h_s"]))
    expect_ended(client.post(f"/api/v1/my/coding-sessions/{sid}/trace-events/batch", json={"events": [{
        "sequence_number": 1, "event_type": "EDITOR_CHANGED", "client_timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {}}]}, headers=w["h_s"]))
    expect_ended(client.put(f"/api/v1/my/coding-sessions/{sid}/scratchpad", json={
        "content": "notes", "client_timestamp": datetime.now(timezone.utc).isoformat()}, headers=w["h_s"]))
    expect_ended(client.post(f"/api/v1/my/exams/{eid}/finalize", headers=w["h_s"]))
    r = client.post(f"/api/v1/my/coding-sessions/{sid}/runs", json={"snapshot_id": snap}, headers=w["h_s"])
    assert r.status_code == 403

    assert len(db.scalars(select(CodeSnapshot).where(CodeSnapshot.session_id == uuid.UUID(sid))).all()) == 1


def test_window_end_blocks_writes_without_duration(db, world):
    w = world
    eid, parts = _running_exam(db, w)
    sid = _exam_session(w, parts["stu"], w["h_s"]).json()["id"]
    _set(eid, start_time=datetime.now(timezone.utc) - timedelta(hours=2), end_time=datetime.now(timezone.utc) - timedelta(seconds=1))
    r = client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots", json={
        "reason": "RUN", "language": "PYTHON3", "source_code": "late\n", "line_count": 1}, headers=w["h_s"])
    assert r.status_code == 403 and r.json()["error_code"] == "EXAM_ENDED"


def test_practice_sessions_unaffected(db, world):
    w = world
    _running_exam(db, w, duration=30)            # stu is in an exam; stu2 is not
    r = client.post("/api/v1/my/practice/sessions", json={"problem_id": w["pid"], "language": "PYTHON3"}, headers=w["h_s2"])
    sid = r.json()["id"]
    assert _snapshot(w["h_s2"], sid, "print(1)\n")


def test_scheduler_finalizes_participant_whose_duration_ran_out(db, world, enqueued):
    w = world
    eid, parts = _running_exam(db, w, duration=30, students=("stu", "stu2"))
    sid = _exam_session(w, parts["stu"], w["h_s"]).json()["id"]
    snap = _snapshot(w["h_s"], sid, "SUM\n")
    created = db.get(CodeSnapshot, uuid.UUID(snap)).created_at
    # stu's deadline falls just after the snapshot; stu2 started now and keeps working
    _started(parts["stu"], created + timedelta(milliseconds=1) - timedelta(minutes=30))

    with TestingSessionLocal() as s:
        result = exam_lifecycle.run_tick(s)
    assert result["ended"] == 0 and len(result["auto_submissions"]) == 1
    db.expire_all()
    sub = db.get(Submission, result["auto_submissions"][0])
    assert sub.source == "SYSTEM_EXAM_TIMEOUT" and str(sub.snapshot_id) == snap
    s1 = db.get(CodingSession, uuid.UUID(sid))
    assert s1.status == "ENDED" and s1.termination_source == "SYSTEM_EXAM_TIMEOUT"
    p1, p2 = db.get(ExamParticipation, uuid.UUID(parts["stu"])), db.get(ExamParticipation, uuid.UUID(parts["stu2"]))
    assert p1.status == "EXPIRED" and p1.expired_at is not None
    assert p2.status == "IN_PROGRESS"
    assert enqueued == result["auto_submissions"]

    # Idempotent
    with TestingSessionLocal() as s:
        assert exam_lifecycle.run_tick(s)["auto_submissions"] == []
