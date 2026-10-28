"""Phase 10A — Submit and judge (docs/36 §4 10A; AC-10-02, AC-10-03, AC-10-10 partial).

The judge runs in-process (`judge_submission`) with a fake adapter: no Docker sandbox.

Database:
    spnc_phase10_submission_test  (PostgreSQL only; guarded)
"""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

PHASE10_DB_URL = os.environ.get(
    "PHASE10_DATABASE_URL",
    "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase10_submission_test",
)
os.environ["DATABASE_URL"] = PHASE10_DB_URL

from app.main import app
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models.exam import ExamParticipation
from app.models.problem import Problem
from app.models.run_submit import Submission
from app.models.session import CodingSession
from app.models.trace import CodeSnapshot, TraceEvent, TraceEventType
from app.models.user import User, AccountStatus
from app.services import submission as submission_svc
from app.services.queue import judge_queue
from app.services.storage import storage_adapter
from alembic.config import Config
from alembic import command

EXPECTED_DB_NAME = "spnc_phase10_submission_test"


def _assert_safe_db(url: str) -> None:
    db_name = urlparse(url).path.lstrip("/")
    if db_name != EXPECTED_DB_NAME:
        raise ValueError(f"UNSAFE DATABASE: '{db_name}'. Phase 10 tests require '{EXPECTED_DB_NAME}'.")


_assert_safe_db(PHASE10_DB_URL)
engine = create_engine(PHASE10_DB_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    _assert_safe_db(PHASE10_DB_URL)
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def clean_db():
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE users CASCADE;"))
        conn.commit()
    yield


@pytest.fixture(autouse=True)
def enqueued(monkeypatch):
    """Captures enqueues instead of touching Redis."""
    ids = []
    monkeypatch.setattr(judge_queue, "enqueue_submission", lambda sid: ids.append(sid) or True)
    return ids


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


class FakeAdapter:
    """Source code is a tiny program name: SUM adds the input ints, WRONG prints 0, CE fails to compile."""

    def __init__(self):
        self.calls = []

    def execute(self, source_code, input_data, memory_limit_mb=None):
        self.calls.append({"input": input_data, "memory_limit_mb": memory_limit_mb})
        base = {"stderr": "", "time_ms": 600, "memory_kb": 1024, "compile_error_message": None, "runtime_error_message": None}
        code = source_code.strip()
        if code == "CE":
            return {**base, "verdict": "COMPILE_ERROR", "stdout": "", "compile_error_message": "syntax error"}
        if code == "BOOM":
            raise RuntimeError("sandbox exploded")
        out = str(sum(int(x) for x in (input_data or "").split())) if code == "SUM" else "0"
        return {**base, "verdict": "ACCEPTED", "stdout": out + "\n"}


def _make_user(db, username, role):
    u = User(username=username, email=f"{username}@spnc.io", password_hash=get_password_hash("Password123!"),
             full_name=username, role=role, status=AccountStatus.ACTIVE.value, force_password_change=False)
    db.add(u)
    db.commit()
    return u


def _auth(username):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _add_case(h, pid, inp, out, sample=False, weight=10):
    r = client.post(f"/api/v1/problems/{pid}/test-cases",
                    json={"input_data": inp, "expected_output": out, "is_sample": sample, "score_weight": weight}, headers=h)
    assert r.status_code == 201, r.text


@pytest.fixture
def world(db):
    _make_user(db, "teacher", "TEACHER")
    stu = _make_user(db, "stu", "STUDENT")
    _make_user(db, "stu2", "STUDENT")
    h_t, h_s, h_s2 = _auth("teacher"), _auth("stu"), _auth("stu2")
    pid = client.post("/api/v1/problems", json={"title": "Sum", "description": "d", "visibility": "PUBLIC",
                                                "supported_languages": ["PYTHON3"]}, headers=h_t).json()["id"]
    _add_case(h_t, pid, "1 2\n", "3\n", sample=True, weight=10)
    _add_case(h_t, pid, "40 5\n", "45\n", weight=30)
    _add_case(h_t, pid, "100 1\n", "101\n", weight=60)
    return {"h_t": h_t, "h_s": h_s, "h_s2": h_s2, "pid": pid, "student_id": stu.id}


def _practice_session(w, h=None):
    r = client.post("/api/v1/my/practice/sessions", json={"problem_id": w["pid"], "language": "PYTHON3"}, headers=h or w["h_s"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _snapshot(h, sid, code):
    r = client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots", json={
        "reason": "SUBMIT", "language": "PYTHON3", "source_code": code, "line_count": len(code.splitlines()),
    }, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _submit(h, sid, snap_id):
    return client.post(f"/api/v1/my/coding-sessions/{sid}/submissions", json={"snapshot_id": snap_id}, headers=h)


def _judge(sub_id, adapter=None):
    with TestingSessionLocal() as s:
        return submission_svc.judge_submission(s, uuid.UUID(str(sub_id)), adapters={"PYTHON3": adapter or FakeAdapter()})


def _exam_session(w, max_score=50, start_offset=-5, end_offset=60):
    now = datetime.now(timezone.utc)
    h_t, h_s = w["h_t"], w["h_s"]
    cid = client.post("/api/v1/classes", json={"name": "C", "academic_year": "2026"}, headers=h_t).json()["id"]
    assert client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(w["student_id"])}, headers=h_t).status_code in (200, 201)
    eid = client.post("/api/v1/exams", json={"title": "E", "start_time": (now + timedelta(minutes=start_offset)).isoformat(),
                                             "end_time": (now + timedelta(minutes=end_offset)).isoformat()}, headers=h_t).json()["id"]
    assert client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=h_t).status_code in (200, 201)
    assert client.post(f"/api/v1/exams/{eid}/problems", json={"problem_id": w["pid"], "order_index": 1, "max_score": max_score},
                       headers=h_t).status_code in (200, 201)
    r = client.post(f"/api/v1/my/exams/{eid}/start", headers=h_s)
    assert r.status_code in (200, 201), r.text
    part_id = r.json()["id"]
    r = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}", json={"problem_id": w["pid"], "language": "PYTHON3"}, headers=h_s)
    assert r.status_code == 201, r.text
    return eid, part_id, r.json()["id"]


# ---------------------------------------------------------------------------
# AC-10-02 — submit
# ---------------------------------------------------------------------------
def test_submit_creates_submission_event_and_ends_session(db, world, enqueued):
    w = world
    sid = _practice_session(w)
    snap = _snapshot(w["h_s"], sid, "SUM\n")

    r = _submit(w["h_s"], sid, snap)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "PENDING" and body["source"] == "STUDENT" and body["exam_id"] is None
    assert body["snapshot_id"] == snap and body["verdict"] is None and body["judge_result"] is None
    assert enqueued == [uuid.UUID(body["id"])]

    events = db.scalars(select(TraceEvent).where(TraceEvent.session_id == uuid.UUID(sid)).order_by(TraceEvent.sequence_number)).all()
    assert [e.event_type for e in events] == [TraceEventType.SUBMISSION_CREATED.value, TraceEventType.SESSION_ENDED.value]
    assert [e.sequence_number for e in events] == [1, 2]
    assert events[0].payload == {"source": "SERVER", "submission_id": body["id"], "code_snapshot_id": snap}

    # D2: the session is ENDED by the student; final snapshot is the submitted one
    s = db.get(CodingSession, uuid.UUID(sid))
    assert s.status == "ENDED" and s.termination_source == "STUDENT"
    assert str(s.final_code_snapshot_id) == snap


def test_second_submit_on_same_session_rejected(world):
    w = world
    sid = _practice_session(w)
    snap = _snapshot(w["h_s"], sid, "SUM\n")
    assert _submit(w["h_s"], sid, snap).status_code == 201
    r = _submit(w["h_s"], sid, snap)
    assert r.status_code == 403 and r.json()["error_code"] == "SUBMISSION_SESSION_NOT_ACTIVE"


def test_submit_rejects_cross_session_snapshot_and_foreign_session(db, world):
    w = world
    sid = _practice_session(w)
    other_sid = _practice_session(w)
    other_snap = _snapshot(w["h_s"], other_sid, "SUM\n")
    r = _submit(w["h_s"], sid, other_snap)
    assert r.status_code == 403 and r.json()["error_code"] == "SUBMISSION_SNAPSHOT_INVALID"

    snap = _snapshot(w["h_s"], sid, "SUM\n")
    r = _submit(w["h_s2"], sid, snap)
    assert r.status_code == 403 and r.json()["error_code"] == "SESSION_FORBIDDEN"
    assert _submit(w["h_s"], sid, str(uuid.uuid4())).status_code == 404
    assert _submit(w["h_s"], str(uuid.uuid4()), snap).status_code == 404
    assert _submit(w["h_t"], sid, snap).status_code == 403
    # Nothing was written by the rejected attempts
    assert db.scalars(select(Submission)).all() == []
    assert db.get(CodingSession, uuid.UUID(sid)).status == "ACTIVE"


def test_submit_on_ended_session_rejected(world):
    w = world
    sid = _practice_session(w)
    snap = _snapshot(w["h_s"], sid, "SUM\n")
    assert client.post(f"/api/v1/my/practice/sessions/{sid}/end", json={}, headers=w["h_s"]).status_code == 200
    r = _submit(w["h_s"], sid, snap)
    assert r.status_code == 403 and r.json()["error_code"] == "SUBMISSION_SESSION_NOT_ACTIVE"


def test_submit_requires_test_cases(db, world):
    w = world
    pid = client.post("/api/v1/problems", json={"title": "Empty", "description": "d", "visibility": "PUBLIC",
                                                "supported_languages": ["PYTHON3"]}, headers=w["h_t"]).json()["id"]
    sid = client.post("/api/v1/my/practice/sessions", json={"problem_id": pid, "language": "PYTHON3"}, headers=w["h_s"]).json()["id"]
    snap = _snapshot(w["h_s"], sid, "SUM\n")
    r = _submit(w["h_s"], sid, snap)
    assert r.status_code == 422 and r.json()["error_code"] == "PROBLEM_HAS_NO_TEST_CASES"
    assert db.get(CodingSession, uuid.UUID(sid)).status == "ACTIVE"


# ---------------------------------------------------------------------------
# AC-10-03 — judge
# ---------------------------------------------------------------------------
def test_judge_accepted_full_score_and_problem_limits(db, world):
    w = world
    db.get(Problem, uuid.UUID(w["pid"])).memory_limit_mb = 64
    db.commit()
    sid = _practice_session(w)
    sub_id = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n")).json()["id"]

    adapter = FakeAdapter()
    assert _judge(sub_id, adapter) is True
    assert [c["memory_limit_mb"] for c in adapter.calls] == [64, 64, 64]   # D12

    sub = db.get(Submission, uuid.UUID(sub_id))
    assert sub.status == "COMPLETED" and sub.verdict == "ACCEPTED" and sub.score == 100
    assert sub.judge_result["passed_count"] == 3 and sub.judge_result["memory_limit_mb"] == 64
    # Duplicate delivery is a no-op
    assert _judge(sub_id) is False


def test_judge_wrong_answer_partial_score_and_student_view_hides_hidden_io(db, world):
    w = world
    sid = _practice_session(w)
    sub_id = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "WRONG\n")).json()["id"]
    assert _judge(sub_id) is True

    r = client.get(f"/api/v1/my/submissions/{sub_id}", headers=w["h_s"])
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "WRONG_ANSWER" and body["score"] == 0 and body["result_visible"] is True
    cases = body["judge_result"]["testcases"]
    assert [c["order_index"] for c in cases] == [1, 2, 3]
    assert cases[0]["is_sample"] and cases[0]["input"] == "1 2\n" and cases[0]["stdout"] == "0\n"
    for hidden in cases[1:]:
        assert hidden["verdict"] == "WRONG_ANSWER"
        assert "input" not in hidden and "expected_output" not in hidden and "stdout" not in hidden
    # Hidden I/O appears nowhere in judge_result (ids stripped: random hex could contain the digits)
    shown = json.dumps([{k: v for k, v in c.items() if k != "testcase_id"} for c in cases])
    assert "45" not in shown and "101" not in shown and "40 5" not in shown and "100 1" not in shown

    listed = client.get("/api/v1/my/submissions", headers=w["h_s"]).json()
    assert listed["total"] == 1 and listed["items"][0]["judge_result"]["passed_count"] == 0


def test_judge_partial_weighted_score(db, world):
    w = world
    # A program that only gets the sample right: 10 of 100 weight
    sid = _practice_session(w)
    sub_id = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n")).json()["id"]

    class SampleOnly(FakeAdapter):
        def execute(self, source_code, input_data, memory_limit_mb=None):
            res = super().execute(source_code, input_data, memory_limit_mb)
            return res if input_data == "1 2\n" else {**res, "stdout": "nope\n"}

    assert _judge(sub_id, SampleOnly()) is True
    sub = db.get(Submission, uuid.UUID(sub_id))
    assert sub.verdict == "WRONG_ANSWER" and sub.score == 10


def test_judge_compile_error(db, world):
    w = world
    sid = _practice_session(w)
    sub_id = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "CE\n")).json()["id"]
    adapter = FakeAdapter()
    assert _judge(sub_id, adapter) is True
    assert len(adapter.calls) == 1
    sub = db.get(Submission, uuid.UUID(sub_id))
    assert sub.verdict == "COMPILE_ERROR" and sub.score == 0 and sub.judge_result["compile_error_message"] == "syntax error"


def test_judge_adapter_crash_is_failed_internal(db, world):
    w = world
    sid = _practice_session(w)
    sub_id = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "BOOM\n")).json()["id"]
    assert _judge(sub_id) is True
    sub = db.get(Submission, uuid.UUID(sub_id))
    assert sub.status == "FAILED_INTERNAL" and sub.verdict == "INTERNAL_ERROR" and sub.score is None
    body = client.get(f"/api/v1/my/submissions/{sub_id}", headers=w["h_s"]).json()
    assert body["judge_result"] == {"internal_error": True}
    assert "exploded" not in str(body)


def test_judge_missing_snapshot_content_never_fabricates_code(db, world):
    w = world
    sid = _practice_session(w)
    snap = _snapshot(w["h_s"], sid, "SUM\n")
    sub_id = _submit(w["h_s"], sid, snap).json()["id"]
    storage_adapter._memory_store.pop(db.get(CodeSnapshot, uuid.UUID(snap)).object_key)
    adapter = FakeAdapter()
    assert _judge(sub_id, adapter) is True
    assert adapter.calls == []
    sub = db.get(Submission, uuid.UUID(sub_id))
    assert sub.status == "FAILED_INTERNAL" and sub.judge_result == {"internal_error": "Snapshot content unavailable"}


# ---------------------------------------------------------------------------
# Exam context — window, max_score, D5 total, D14 visibility
# ---------------------------------------------------------------------------
def test_exam_submission_scores_on_max_score_updates_best_total_and_hides_result(db, world):
    w = world
    eid, part_id, sid = _exam_session(w, max_score=50)
    r = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "WRONG\n"))
    assert r.status_code == 201 and r.json()["exam_id"] == eid
    first = r.json()["id"]
    assert _judge(first) is True

    # D2: a new session for the next attempt; best score wins (D5)
    sid2 = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}", json={"problem_id": w["pid"], "language": "PYTHON3"},
                       headers=w["h_s"]).json()["id"]
    second = _submit(w["h_s"], sid2, _snapshot(w["h_s"], sid2, "SUM\n")).json()["id"]
    assert _judge(second) is True
    assert db.get(Submission, uuid.UUID(second)).score == 50
    assert db.get(ExamParticipation, uuid.UUID(part_id)).total_score == 50

    sid3 = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}", json={"problem_id": w["pid"], "language": "PYTHON3"},
                       headers=w["h_s"]).json()["id"]
    third = _submit(w["h_s"], sid3, _snapshot(w["h_s"], sid3, "WRONG\n")).json()["id"]
    assert _judge(third) is True
    db.expire_all()
    assert db.get(ExamParticipation, uuid.UUID(part_id)).total_score == 50

    # D14: exam results stay hidden (allow_view_result_after arrives in 10B)
    body = client.get(f"/api/v1/my/submissions/{second}", headers=w["h_s"]).json()
    assert body["status"] == "COMPLETED" and body["result_visible"] is False
    assert body["verdict"] is None and body["score"] is None and body["judge_result"] is None


def test_exam_submit_outside_window_or_inactive_participation_rejected(db, world):
    w = world
    eid, part_id, sid = _exam_session(w)
    snap = _snapshot(w["h_s"], sid, "SUM\n")

    p = db.get(ExamParticipation, uuid.UUID(part_id))
    p.status = "COMPLETED"
    db.commit()
    r = _submit(w["h_s"], sid, snap)
    assert r.status_code == 403 and r.json()["error_code"] == "PARTICIPATION_NOT_ACTIVE"

    p.status = "IN_PROGRESS"
    db.commit()
    db.execute(text("UPDATE exams SET start_time = now() - interval '2 hours', end_time = now() - interval '1 second' WHERE id = :id"),
               {"id": eid})
    db.commit()
    r = _submit(w["h_s"], sid, snap)
    assert r.status_code == 403 and r.json()["error_code"] == "EXAM_ENDED"

    db.execute(text("UPDATE exams SET end_time = now() + interval '1 hour', status = 'CANCELLED' WHERE id = :id"), {"id": eid})
    db.commit()
    r = _submit(w["h_s"], sid, snap)
    assert r.status_code == 403 and r.json()["error_code"] == "EXAM_CANCELLED"
    assert db.scalars(select(Submission)).all() == []
