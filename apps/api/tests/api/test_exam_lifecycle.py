"""Phase 10B — Exam lifecycle (docs/36 §4 10B; AC-10-05, 06, 08, 09, 10).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test).
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.models.exam import Exam, ExamParticipation
from app.models.run_submit import Submission
from app.models.session import CodingSession
from app.models.user import AuditLog, User
from app.services import exam_lifecycle
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _add_case, _auth, _judge, _make_user, _snapshot, _submit, client,
    clean_db, db, enqueued, setup_database, world,
)


def _iso(minutes):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _class_with(w, *student_ids):
    cid = client.post("/api/v1/classes", json={"name": "C", "academic_year": "2026"}, headers=w["h_t"]).json()["id"]
    for sid in student_ids:
        assert client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(sid)}, headers=w["h_t"]).status_code in (200, 201)
    return cid


def _draft(w, start=60, end=120, cid=None, pid=None, **extra):
    eid = client.post("/api/v1/exams", json={"title": "E", "start_time": _iso(start), "end_time": _iso(end), **extra},
                      headers=w["h_t"]).json()["id"]
    if cid:
        assert client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=w["h_t"]).status_code in (200, 201)
    if pid:
        assert client.post(f"/api/v1/exams/{eid}/problems", json={"problem_id": pid, "order_index": 1, "max_score": 40},
                           headers=w["h_t"]).status_code in (200, 201)
    return eid


def _set(eid, **cols):
    with TestingSessionLocal() as s:
        sets = ", ".join(f"{k} = :{k}" for k in cols)
        s.execute(text(f"UPDATE exams SET {sets} WHERE id = :id"), {**cols, "id": eid})
        s.commit()


def _open_exam(w, **extra):
    """A running exam the student has joined: returns (eid, participation_id, session_id)."""
    cid = _class_with(w, w["student_id"])
    eid = _draft(w, cid=cid, pid=w["pid"], **extra)
    assert client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"]).status_code == 200
    now = datetime.now(timezone.utc)
    _set(eid, start_time=now - timedelta(minutes=5), end_time=now + timedelta(minutes=60))
    part_id = client.post(f"/api/v1/my/exams/{eid}/start", headers=w["h_s"]).json()["id"]
    sid = _exam_session(w, part_id)
    return eid, part_id, sid


def _exam_session(w, part_id):
    r = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}", json={"problem_id": w["pid"], "language": "PYTHON3"},
                    headers=w["h_s"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# AC-10-05 — publish validation and D11 access
# ---------------------------------------------------------------------------
def test_publish_validation_steps(world):
    w = world
    eid = _draft(w)
    pub = lambda: client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"])  # noqa: E731
    assert pub().json()["error_code"] == "EXAM_NO_CLASS"

    cid = _class_with(w, w["student_id"])
    client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=w["h_t"])
    assert pub().json()["error_code"] == "EXAM_NO_PROBLEM"

    bare = client.post("/api/v1/problems", json={"title": "Bare", "description": "d", "visibility": "PUBLIC",
                                                 "supported_languages": ["PYTHON3"]}, headers=w["h_t"]).json()["id"]
    client.post(f"/api/v1/exams/{eid}/problems", json={"problem_id": bare, "order_index": 1}, headers=w["h_t"])
    r = pub()
    assert r.status_code == 422 and r.json()["error_code"] == "EXAM_PROBLEM_WITHOUT_TEST_CASES" and bare in r.json()["message"]

    _add_case(w["h_t"], bare, "1\n", "1\n")
    r = pub()
    assert r.status_code == 200 and r.json()["status"] == "SCHEDULED"
    assert pub().status_code == 409 and pub().json()["error_code"] == "EXAM_NOT_DRAFT"


def test_publish_rejects_past_start_and_non_owner(db, world):
    w = world
    cid = _class_with(w, w["student_id"])
    past = _draft(w, start=-5, end=60, cid=cid, pid=w["pid"])
    r = client.post(f"/api/v1/exams/{past}/publish", headers=w["h_t"])
    assert r.status_code == 422 and r.json()["error_code"] == "EXAM_START_IN_PAST"

    _make_user(db, "other_t", "TEACHER")
    future = _draft(w, cid=cid, pid=w["pid"])
    assert client.post(f"/api/v1/exams/{future}/publish", headers=_auth("other_t")).status_code == 403
    assert client.post(f"/api/v1/exams/{future}/publish", headers=w["h_s"]).status_code == 403


def test_draft_exam_cannot_be_joined_or_listed(world):
    w = world
    cid = _class_with(w, w["student_id"])
    eid = _draft(w, start=-5, end=60, cid=cid, pid=w["pid"])
    r = client.post(f"/api/v1/my/exams/{eid}/start", headers=w["h_s"])
    assert r.status_code == 403 and r.json()["error_code"] == "EXAM_NOT_PUBLISHED"
    assert client.get("/api/v1/my/exams", headers=w["h_s"]).json()["total"] == 0

    _set(eid, status="SCHEDULED")   # published, scheduler not yet ticked: time window decides (REQ-EXAM-012)
    assert client.post(f"/api/v1/my/exams/{eid}/start", headers=w["h_s"]).status_code == 201
    assert client.get("/api/v1/my/exams", headers=w["h_s"]).json()["total"] == 1

    _set(eid, status="ENDED")
    part = client.get(f"/api/v1/my/exams/{eid}/participation", headers=w["h_s"]).json()["id"]
    r = client.post(f"/api/v1/my/exam-sessions?participation_id={part}", json={"problem_id": w["pid"], "language": "PYTHON3"},
                    headers=w["h_s"])
    assert r.status_code == 403 and r.json()["error_code"] == "EXAM_ENDED"


# ---------------------------------------------------------------------------
# AC-10-06 — scheduler transitions
# ---------------------------------------------------------------------------
def test_scheduler_moves_scheduled_to_ongoing_to_ended_idempotently(db, world):
    w = world
    cid = _class_with(w, w["student_id"])
    eid = _draft(w, start=60, end=120, cid=cid, pid=w["pid"])
    client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"])
    exam = db.get(Exam, uuid.UUID(eid))
    start, end = exam.start_time, exam.end_time

    with TestingSessionLocal() as s:
        assert exam_lifecycle.run_tick(s, now=start - timedelta(seconds=1))["started"] == 0
        assert exam_lifecycle.run_tick(s, now=start)["started"] == 1
        assert exam_lifecycle.run_tick(s, now=start + timedelta(seconds=30)) == {"started": 0, "ended": 0, "auto_submissions": []}
    db.expire_all()
    assert db.get(Exam, uuid.UUID(eid)).status == "ONGOING"

    with TestingSessionLocal() as s:
        assert exam_lifecycle.run_tick(s, now=end)["ended"] == 1
        assert exam_lifecycle.run_tick(s, now=end + timedelta(seconds=30))["ended"] == 0
    db.expire_all()
    assert db.get(Exam, uuid.UUID(eid)).status == "ENDED"


def test_scheduler_catches_up_whole_window_in_one_tick(db, world):
    w = world
    cid = _class_with(w, w["student_id"])
    eid = _draft(w, cid=cid, pid=w["pid"])
    client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"])
    with TestingSessionLocal() as s:
        result = exam_lifecycle.run_tick(s, now=datetime.now(timezone.utc) + timedelta(hours=3))
    assert (result["started"], result["ended"]) == (1, 1)
    db.expire_all()
    assert db.get(Exam, uuid.UUID(eid)).status == "ENDED"


def test_scheduler_ignores_draft_and_cancelled(db, world):
    w = world
    draft = _draft(w, start=-30, end=-10)
    cancelled = _draft(w, start=-30, end=-10)
    _set(cancelled, status="CANCELLED")
    with TestingSessionLocal() as s:
        assert exam_lifecycle.run_tick(s) == {"started": 0, "ended": 0, "auto_submissions": []}
    db.expire_all()
    assert db.get(Exam, uuid.UUID(draft)).status == "DRAFT"
    assert db.get(Exam, uuid.UUID(cancelled)).status == "CANCELLED"


# ---------------------------------------------------------------------------
# AC-10-08 — student finalize
# ---------------------------------------------------------------------------
def test_finalize_completes_ends_sessions_without_submission(db, world):
    w = world
    eid, part_id, sid = _open_exam(w)
    snap = _snapshot(w["h_s"], sid, "SUM\n")

    r = client.post(f"/api/v1/my/exams/{eid}/finalize", headers=w["h_s"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "COMPLETED" and r.json()["completed_at"] is not None

    s = db.get(CodingSession, uuid.UUID(sid))
    assert s.status == "ENDED" and s.termination_source == "STUDENT"
    assert db.scalars(select(Submission)).all() == []      # the student chose to finish: no auto-submit

    # Later actions are refused
    assert client.post(f"/api/v1/my/exams/{eid}/finalize", headers=w["h_s"]).json()["error_code"] == "PARTICIPATION_NOT_ACTIVE"
    r = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}", json={"problem_id": w["pid"], "language": "PYTHON3"},
                    headers=w["h_s"])
    assert r.status_code == 403 and r.json()["error_code"] == "PARTICIPATION_NOT_ACTIVE"

    # The timeout pass leaves a COMPLETED participation alone
    _set(eid, start_time=datetime.now(timezone.utc) - timedelta(hours=2), end_time=datetime.now(timezone.utc) - timedelta(seconds=1),
         status="ONGOING")
    with TestingSessionLocal() as s2:
        assert exam_lifecycle.run_tick(s2)["auto_submissions"] == []
    db.expire_all()
    assert db.get(ExamParticipation, uuid.UUID(part_id)).status == "COMPLETED"
    assert snap  # snapshot existed but was never auto-submitted


def test_submit_after_finalize_is_forbidden(world):
    w = world
    eid, part_id, sid = _open_exam(w)
    sid2 = _exam_session(w, part_id)
    snap = _snapshot(w["h_s"], sid2, "SUM\n")
    client.post(f"/api/v1/my/exams/{eid}/finalize", headers=w["h_s"])
    r = _submit(w["h_s"], sid2, snap)
    assert r.status_code == 403   # session already ended by finalize


def test_finalize_after_end_time_is_refused(world):
    w = world
    eid, part_id, sid = _open_exam(w)
    _set(eid, start_time=datetime.now(timezone.utc) - timedelta(hours=2), end_time=datetime.now(timezone.utc) - timedelta(seconds=1))
    r = client.post(f"/api/v1/my/exams/{eid}/finalize", headers=w["h_s"])
    assert r.status_code == 403 and r.json()["error_code"] == "EXAM_ENDED"


# ---------------------------------------------------------------------------
# AC-10-09 — teacher and admin cancel
# ---------------------------------------------------------------------------
def test_teacher_cancel_scheduled_exam(db, world):
    w = world
    cid = _class_with(w, w["student_id"])
    eid = _draft(w, cid=cid, pid=w["pid"])
    client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"])
    db.add(ExamParticipation(exam_id=uuid.UUID(eid), student_id=w["student_id"], status="NOT_STARTED"))
    db.commit()

    assert client.post(f"/api/v1/exams/{eid}/cancel", json={"reason": ""}, headers=w["h_t"]).status_code == 422
    assert client.post(f"/api/v1/exams/{eid}/cancel", json={"reason": "x", "extra": 1}, headers=w["h_t"]).status_code == 422
    assert client.post(f"/api/v1/exams/{eid}/cancel", json={"reason": "x"}, headers=w["h_s"]).status_code == 403

    r = client.post(f"/api/v1/exams/{eid}/cancel", json={"reason": "Room unavailable"}, headers=w["h_t"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "CANCELLED" and body["cancel_reason"] == "Room unavailable" and body["cancelled_at"]

    db.expire_all()
    exam = db.get(Exam, uuid.UUID(eid))
    teacher = db.scalar(select(User).where(User.username == "teacher"))
    assert exam.cancelled_by == teacher.id
    assert [p.status for p in db.scalars(select(ExamParticipation).where(ExamParticipation.exam_id == exam.id))] == ["CANCELLED"]
    log = db.scalar(select(AuditLog).where(AuditLog.action == "EXAM_CANCELLED"))
    assert log.target_id == eid and log.actor_id == teacher.id and log.metadata_payload == {"reason": "Room unavailable"}
    assert db.scalars(select(Submission)).all() == []

    again = client.post(f"/api/v1/exams/{eid}/cancel", json={"reason": "x"}, headers=w["h_t"])
    assert again.status_code == 409 and again.json()["error_code"] == "EXAM_ALREADY_CANCELLED"


def test_teacher_cannot_cancel_running_or_ended(world):
    w = world
    eid, _, _ = _open_exam(w)
    for status in ("ONGOING", "SCHEDULED"):   # SCHEDULED past start_time counts as running (scheduler lag)
        _set(eid, status=status)
        r = client.post(f"/api/v1/exams/{eid}/cancel", json={"reason": "x"}, headers=w["h_t"])
        assert r.status_code == 409 and r.json()["error_code"] == "EXAM_ONGOING"
    _set(eid, status="ENDED")
    r = client.post(f"/api/v1/exams/{eid}/cancel", json={"reason": "x"}, headers=w["h_t"])
    assert r.status_code == 400 and r.json()["error_code"] == "INVALID_STATE"


def test_admin_cancel_restricted_to_draft_and_scheduled(db, world):
    w = world
    _make_user(db, "admin", "ADMIN")
    h_a = _auth("admin")
    eid, part_id, _ = _open_exam(w)
    _set(eid, status="ONGOING")
    r = client.patch(f"/api/v1/admin/exams/{eid}/cancel", headers=h_a)
    assert r.status_code == 409 and r.json()["error_code"] == "EXAM_ONGOING_CANCEL_UNDECIDED"
    db.expire_all()
    assert db.get(ExamParticipation, uuid.UUID(part_id)).status == "IN_PROGRESS"

    draft = _draft(w)
    assert client.patch(f"/api/v1/admin/exams/{draft}/cancel", headers=h_a).status_code == 200
    assert client.patch(f"/api/v1/admin/exams/{draft}/cancel", headers=h_a).status_code == 200   # idempotent (Phase 04)
    db.expire_all()
    assert db.get(Exam, uuid.UUID(draft)).status == "CANCELLED"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "EXAM_ADMIN_CANCELLED")).target_id == draft


# ---------------------------------------------------------------------------
# AC-10-10 — result visibility (D14)
# ---------------------------------------------------------------------------
def test_exam_results_visible_only_after_ended_with_flag(db, world):
    w = world
    eid, _, sid = _open_exam(w)
    sub_id = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n")).json()["id"]
    assert _judge(sub_id) is True
    get = lambda: client.get(f"/api/v1/my/submissions/{sub_id}", headers=w["h_s"]).json()  # noqa: E731

    assert client.patch(f"/api/v1/exams/{eid}", json={"allow_view_result_after": True}, headers=w["h_t"]).json()["allow_view_result_after"]
    body = get()
    assert body["result_visible"] is False and body["score"] is None   # flag set, exam not ENDED

    _set(eid, status="ENDED", allow_view_result_after=False)
    assert get()["result_visible"] is False

    _set(eid, allow_view_result_after=True)
    body = get()
    assert body["result_visible"] is True and body["verdict"] == "ACCEPTED" and body["score"] == 40
    hidden = [c for c in body["judge_result"]["testcases"] if not c["is_sample"]]
    assert hidden and all("input" not in c and "stdout" not in c for c in hidden)   # D7 still applies
