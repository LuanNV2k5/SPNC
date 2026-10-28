"""Phase 09A — Teacher Observation read API (docs/35 AC-09-01..08).

Database:
    spnc_phase09_observation_test  (PostgreSQL only; guarded)
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PHASE09_DB_URL = os.environ.get(
    "PHASE09_DATABASE_URL",
    "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase09_observation_test",
)
os.environ["DATABASE_URL"] = PHASE09_DB_URL

from app.main import app
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models.user import User, AccountStatus
from app.models.observation import AttentionSignal
from app.models.run_submit import Run, RunStatus, RunVerdict
from app.models.trace import CodeSnapshot
from alembic.config import Config
from alembic import command

EXPECTED_DB_NAME = "spnc_phase09_observation_test"


def _assert_safe_db(url: str) -> None:
    db_name = urlparse(url).path.lstrip("/")
    if db_name != EXPECTED_DB_NAME:
        raise ValueError(f"UNSAFE DATABASE: '{db_name}'. Phase 09 tests require '{EXPECTED_DB_NAME}'.")


_assert_safe_db(PHASE09_DB_URL)
engine = create_engine(PHASE09_DB_URL)
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
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def clean_db():
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE users CASCADE;"))
        conn.commit()
    yield


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _make_user(db, username, role):
    u = User(username=username, email=f"{username}@spnc.io", password_hash=get_password_hash("Password123!"),
             full_name=f"Full {username}", role=role, status=AccountStatus.ACTIVE.value, force_password_change=False)
    db.add(u)
    db.commit()
    return u


def _auth(username):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _class(h, name, student_ids):
    cid = client.post("/api/v1/classes", json={"name": name, "academic_year": "2026"}, headers=h).json()["id"]
    for sid in student_ids:
        assert client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(sid)}, headers=h).status_code in (200, 201)
    return cid


def _problem(h, title, visibility="PUBLIC"):
    r = client.post("/api/v1/problems", json={"title": title, "description": "d", "visibility": visibility,
                                              "supported_languages": ["PYTHON3"]}, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _practice(h, problem_id):
    r = client.post("/api/v1/my/practice/sessions", json={"problem_id": problem_id, "language": "PYTHON3"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ingest(h, sid, seqs):
    events = [{"sequence_number": n, "event_type": "EDITOR_CHANGED",
               "client_timestamp": datetime.now(timezone.utc).isoformat(), "payload": {"n": n}} for n in seqs]
    assert client.post(f"/api/v1/my/coding-sessions/{sid}/trace-events/batch", json={"events": events}, headers=h).status_code == 200


def _snapshot(h, sid, code):
    r = client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots",
                    json={"reason": "RUN", "language": "PYTHON3", "source_code": code, "line_count": len(code.splitlines())}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _signal(db, student_id, session_id, signal_type="IDLE_DETECTED", status="NEW"):
    sig = AttentionSignal(student_id=student_id, session_id=uuid.UUID(session_id), signal_type=signal_type,
                          status=status, rule_version="1.1.0", evidence={"duration_seconds": 400.0},
                          dedup_key=f"TEST:{uuid.uuid4()}")
    db.add(sig)
    db.commit()
    return sig


@pytest.fixture
def world(db):
    """
    T1 owns C1, T2 owns C2; student S is in both classes.
    P1 (owned by T1) -> practice session s1 is visible to T1 in C1.
    P2 (owned by T2, published to C2 only) -> practice session s2 is NOT visible to T1 in C1.
    """
    t1 = _make_user(db, "t1", "TEACHER")
    t2 = _make_user(db, "t2", "TEACHER")
    s = _make_user(db, "stu", "STUDENT")
    other = _make_user(db, "other_stu", "STUDENT")
    h1, h2, hs = _auth("t1"), _auth("t2"), _auth("stu")
    c1 = _class(h1, "C1", [s.id])
    c2 = _class(h2, "C2", [s.id])
    p1 = _problem(h1, "Two Sum")
    p2 = _problem(h2, "Other Teacher Problem", visibility="CLASS")
    assert client.post(f"/api/v1/problems/{p2}/publish", json={"class_id": c2}, headers=h2).status_code == 201
    s1 = _practice(hs, p1)
    s2 = _practice(hs, p2)
    return {"t1": t1, "t2": t2, "s": s, "other": other, "h1": h1, "h2": h2, "hs": hs,
            "c1": c1, "c2": c2, "p1": p1, "p2": p2, "s1": s1, "s2": s2}


def _base(w, session_key="s1"):
    return f"/api/v1/classes/{w['c1']}/students/{w['s'].id}/sessions/{w[session_key]}"


# ---------------------------------------------------------------------------
# AC-09-01 / 03 — authorization and the §3 visibility rule
# ---------------------------------------------------------------------------
def test_non_owner_teacher_forbidden_everywhere(world):
    w = world
    urls = [
        f"/api/v1/classes/{w['c1']}/attention",
        f"/api/v1/classes/{w['c1']}/students/{w['s'].id}/sessions",
        f"/api/v1/classes/{w['c1']}/students/{w['s'].id}/signals",
        _base(w) + "/timeline",
        _base(w) + "/runs",
    ]
    for url in urls:
        r = client.get(url, headers=w["h2"])
        assert r.status_code == 403, url
        assert r.json()["error_code"] == "FORBIDDEN_RESOURCE"
        assert "request_id" in r.json()


def test_student_role_cannot_use_observation_api(world):
    r = client.get(f"/api/v1/classes/{world['c1']}/attention", headers=world["hs"])
    assert r.status_code == 403


def test_student_not_in_class_forbidden(world):
    w = world
    r = client.get(f"/api/v1/classes/{w['c1']}/students/{w['other'].id}/sessions", headers=w["h1"])
    assert r.status_code == 403


def test_session_outside_class_context_is_hidden(world):
    w = world
    for suffix in ("/timeline", "/runs", "/trace-events", "/trace-state", "/scratchpad"):
        r = client.get(_base(w, "s2") + suffix, headers=w["h1"])
        assert r.status_code == 404, suffix
    # T2 sees s2 in C2 (published there)
    r = client.get(f"/api/v1/classes/{w['c2']}/students/{w['s'].id}/sessions/{w['s2']}/timeline", headers=w["h2"])
    assert r.status_code == 200


def test_owned_problem_session_hidden_from_other_class(world):
    w = world
    # s1 is on T1's own problem; T2 must not see it in C2 (not published there, not owned by T2)
    r = client.get(f"/api/v1/classes/{w['c2']}/students/{w['s'].id}/sessions/{w['s1']}/timeline", headers=w["h2"])
    assert r.status_code == 404


def test_publication_to_class_makes_foreign_problem_visible(db, world):
    w = world
    # P2 belongs to T2; publishing it to C1 (rule: published to class) makes s2 visible to T1 in C1
    from app.models.problem import ProblemClassPublication
    db.add(ProblemClassPublication(problem_id=uuid.UUID(w["p2"]), class_id=uuid.UUID(w["c1"])))
    db.commit()
    assert client.get(_base(w, "s2") + "/timeline", headers=w["h1"]).status_code == 200


# ---------------------------------------------------------------------------
# AC-09-02 — F1: run reads
# ---------------------------------------------------------------------------
def _run(db, session_id, snapshot_id):
    run = Run(session_id=uuid.UUID(session_id), snapshot_id=uuid.UUID(snapshot_id), status=RunStatus.COMPLETED.value,
              verdict=RunVerdict.RUNTIME_ERROR.value, testcase_results={"stderr": "x"})
    db.add(run)
    db.commit()
    return run


def test_teacher_cannot_read_runs_through_student_endpoint(db, world):
    w = world
    _run(db, w["s1"], _snapshot(w["hs"], w["s1"], "print(1)\n"))
    assert client.get(f"/api/v1/my/coding-sessions/{w['s1']}/runs", headers=w["h1"]).status_code == 403
    assert client.get(f"/api/v1/my/coding-sessions/{w['s1']}/runs", headers=w["h2"]).status_code == 403
    r = client.get(f"/api/v1/my/coding-sessions/{w['s1']}/runs", headers=w["hs"])
    assert r.status_code == 200 and len(r.json()) == 1


def test_teacher_reads_runs_through_class_scoped_endpoint(db, world):
    w = world
    run = _run(db, w["s1"], _snapshot(w["hs"], w["s1"], "print(1)\n"))
    r = client.get(_base(w) + "/runs", headers=w["h1"])
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["id"] == str(run.id)
    assert r.json()["items"][0]["verdict"] == "RUNTIME_ERROR"


# ---------------------------------------------------------------------------
# AC-09-04 — attention list
# ---------------------------------------------------------------------------
def test_attention_lists_only_new_signals_on_visible_sessions(db, world):
    w = world
    _signal(db, w["s"].id, w["s1"], "IDLE_DETECTED")
    _signal(db, w["s"].id, w["s1"], "IDLE_DETECTED")
    _signal(db, w["s"].id, w["s1"], "FAST_FIRST_CODE")
    _signal(db, w["s"].id, w["s1"], "LOC_ANOMALY", status="ACKNOWLEDGED")
    _signal(db, w["s"].id, w["s2"], "REPEATED_FAILURE")   # not visible in C1

    r = client.get(f"/api/v1/classes/{w['c1']}/attention", headers=w["h1"])
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["student_id"] == str(w["s"].id)
    assert item["username"] == "stu"
    assert item["new_signal_count"] == 3
    assert item["counts_by_type"] == {"IDLE_DETECTED": 2, "FAST_FIRST_CODE": 1}

    r2 = client.get(f"/api/v1/classes/{w['c2']}/attention", headers=w["h2"])
    assert r2.json()["items"][0]["counts_by_type"] == {"REPEATED_FAILURE": 1}


def test_attention_empty_when_no_new_signals(world):
    r = client.get(f"/api/v1/classes/{world['c1']}/attention", headers=world["h1"])
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0, "page": 1, "size": 50}


# ---------------------------------------------------------------------------
# AC-09-05 — session list
# ---------------------------------------------------------------------------
def test_session_list_fields(db, world):
    w = world
    _ingest(w["hs"], w["s1"], [1, 2])
    _snapshot(w["hs"], w["s1"], "a = 1\nb = 2\n")
    _signal(db, w["s"].id, w["s1"])
    assert client.post(f"/api/v1/my/practice/sessions/{w['s1']}/end", json={}, headers=w["hs"]).status_code == 200

    r = client.get(f"/api/v1/classes/{w['c1']}/students/{w['s'].id}/sessions", headers=w["h1"])
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1                         # s2 hidden in C1
    item = body["items"][0]
    assert item["id"] == w["s1"]
    assert item["problem_title"] == "Two Sum"
    assert item["context"] == "PRACTICE"
    assert item["exam_id"] is None
    assert item["status"] == "ENDED"
    assert item["termination_source"] == "STUDENT"
    assert item["latest_meaningful_event_at"] is not None
    assert item["latest_submission_verdict"] is None
    assert item["signal_count"] == 1
    assert item["final_loc"] == 2
    assert item["working_time_seconds"] >= 0


# ---------------------------------------------------------------------------
# AC-09-06 / 07 — timeline and snapshots
# ---------------------------------------------------------------------------
def test_timeline_events_signals_snapshots(db, world):
    w = world
    _ingest(w["hs"], w["s1"], [2, 1, 3])
    snap_id = _snapshot(w["hs"], w["s1"], "print('hi')\n")
    sig = _signal(db, w["s"].id, w["s1"])
    client.post(f"/api/v1/my/practice/sessions/{w['s1']}/end", json={}, headers=w["hs"])

    r = client.get(_base(w) + "/timeline", headers=w["h1"])
    assert r.status_code == 200
    body = r.json()
    assert [e["sequence_number"] for e in body["events"]] == [1, 2, 3, 4]     # D3: sequence order
    assert body["events"][-1]["event_type"] == "SESSION_ENDED"
    assert body["events"][-1]["payload"]["termination_actor"] == "STUDENT"
    assert all(e["server_timestamp"] for e in body["events"])
    assert body["total_events"] == 4
    assert body["state"]["highest_contiguous_sequence"] == 4
    assert [s["id"] for s in body["signals"]] == [str(sig.id)]
    assert [s["id"] for s in body["snapshots"]] == [snap_id]
    assert body["session"]["status"] == "ENDED"

    page = client.get(_base(w) + "/timeline?skip=1&limit=2", headers=w["h1"]).json()
    assert [e["sequence_number"] for e in page["events"]] == [2, 3]


def test_snapshot_content_only_within_session(world):
    w = world
    snap_id = _snapshot(w["hs"], w["s1"], "x = 42\n")
    foreign_snap = _snapshot(w["hs"], w["s2"], "secret = 1\n")

    r = client.get(_base(w) + f"/snapshots/{snap_id}", headers=w["h1"])
    assert r.status_code == 200
    assert r.json()["source_code"] == "x = 42\n"
    assert r.json()["content_available"] is True

    r = client.get(_base(w) + f"/snapshots/{foreign_snap}", headers=w["h1"])
    assert r.status_code == 404
    assert r.json()["error_code"] == "SNAPSHOT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Signals list
# ---------------------------------------------------------------------------
def test_signal_list_filters(db, world):
    w = world
    _signal(db, w["s"].id, w["s1"], "IDLE_DETECTED")
    _signal(db, w["s"].id, w["s1"], "FAST_FIRST_CODE", status="DISMISSED")
    _signal(db, w["s"].id, w["s2"], "IDLE_DETECTED")   # hidden in C1
    base = f"/api/v1/classes/{w['c1']}/students/{w['s'].id}/signals"
    assert client.get(base, headers=w["h1"]).json()["total"] == 2
    assert client.get(base + "?status=NEW", headers=w["h1"]).json()["total"] == 1
    r = client.get(base + "?signal_type=FAST_FIRST_CODE", headers=w["h1"]).json()
    assert r["total"] == 1 and r["items"][0]["status"] == "DISMISSED"
    assert r["items"][0]["evidence"] == {"duration_seconds": 400.0}


# ---------------------------------------------------------------------------
# AC-09-08 — exam observation
# ---------------------------------------------------------------------------
def _exam(h, title, class_ids, problem_ids, start, end):
    eid = client.post("/api/v1/exams", json={"title": title, "start_time": start.isoformat(), "end_time": end.isoformat()},
                      headers=h).json()["id"]
    for cid in class_ids:
        assert client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=h).status_code in (200, 201)
    for i, pid in enumerate(problem_ids, 1):
        assert client.post(f"/api/v1/exams/{eid}/problems", json={"problem_id": pid, "order_index": i}, headers=h).status_code in (200, 201)
    return eid


def test_exam_observation_overview(db, world):
    w = world
    s_b = _make_user(db, "stu_b", "STUDENT")
    client.post(f"/api/v1/classes/{w['c1']}/members", json={"student_id": str(s_b.id)}, headers=w["h1"])
    now = datetime.now(timezone.utc)
    eid = _exam(w["h1"], "Midterm", [w["c1"]], [w["p1"]], now - timedelta(minutes=10), now + timedelta(minutes=110))
    from app.models.exam import Exam
    db.get(Exam, uuid.UUID(eid)).status = "SCHEDULED"   # docs/36 D11: published
    db.commit()

    # end the practice sessions first: an active practice does not block, but keep the exam session the only ACTIVE one
    part_id = client.post(f"/api/v1/my/exams/{eid}/start", headers=w["hs"]).json()["id"]
    r = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}",
                    json={"problem_id": w["p1"], "language": "PYTHON3"}, headers=w["hs"])
    assert r.status_code == 201, r.text
    exam_sid = r.json()["id"]
    _ingest(w["hs"], exam_sid, [1])
    snap = _snapshot(w["hs"], exam_sid, "print(1)\n")
    _run(db, exam_sid, snap)
    _signal(db, w["s"].id, exam_sid)

    r = client.get(f"/api/v1/exams/{eid}/observation", headers=w["h1"])
    assert r.status_code == 200
    body = r.json()
    assert body["exam_title"] == "Midterm"
    assert body["total"] == 2
    by_user = {i["username"]: i for i in body["items"]}
    stu = by_user["stu"]
    assert stu["participation_status"] == "IN_PROGRESS"
    assert stu["current_session"]["id"] == exam_sid
    assert stu["current_session"]["run_count"] == 1
    assert stu["current_session"]["latest_activity_at"] is not None
    assert stu["signal_count"] == 1
    assert stu["submitted_problem_count"] == 0
    assert by_user["stu_b"]["participation_status"] == "NOT_STARTED"
    assert by_user["stu_b"]["current_session"] is None

    # the exam session is visible in C1 (exam assigned to C1)
    r = client.get(f"/api/v1/classes/{w['c1']}/students/{w['s'].id}/sessions/{exam_sid}/timeline", headers=w["h1"])
    assert r.status_code == 200
    assert r.json()["session"]["context"] == "EXAM"
    assert r.json()["session"]["exam_title"] == "Midterm"
    # but not in C2 (exam not assigned there)
    r = client.get(f"/api/v1/classes/{w['c2']}/students/{w['s'].id}/sessions/{exam_sid}/timeline", headers=w["h2"])
    assert r.status_code == 404


def test_exam_observation_derived_states(db, world):
    w = world
    now = datetime.now(timezone.utc)
    ended = _exam(w["h1"], "Past", [w["c1"]], [w["p1"]], now - timedelta(hours=3), now - timedelta(hours=1))
    r = client.get(f"/api/v1/exams/{ended}/observation", headers=w["h1"])
    assert r.json()["items"][0]["participation_status"] == "EXPIRED"     # D6

    future = _exam(w["h1"], "Future", [w["c1"]], [w["p1"]], now + timedelta(hours=1), now + timedelta(hours=2))
    from app.models.exam import Exam
    exam = db.get(Exam, uuid.UUID(future))
    exam.status = "CANCELLED"
    db.commit()
    r = client.get(f"/api/v1/exams/{future}/observation", headers=w["h1"])
    assert r.json()["items"][0]["participation_status"] == "CANCELLED"   # D6


def test_exam_observation_owner_only(world):
    w = world
    now = datetime.now(timezone.utc)
    eid = _exam(w["h1"], "Mine", [w["c1"]], [w["p1"]], now - timedelta(minutes=5), now + timedelta(hours=1))
    r = client.get(f"/api/v1/exams/{eid}/observation", headers=w["h2"])
    assert r.status_code == 403
    assert client.get(f"/api/v1/exams/{uuid.uuid4()}/observation", headers=w["h1"]).status_code == 404
