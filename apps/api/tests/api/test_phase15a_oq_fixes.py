"""Phase 15A — Behaviour fixes from the open-question review (docs/41 R1-R5).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from app.core.config import settings
from app.models.session import CodingSession
from app.models.user import User
from app.services import login_throttle as throttle_mod
from app.services.login_throttle import login_throttle
from app.services.session_lifecycle import abandon_stale_practice_sessions
from tests.api.test_exam_lifecycle import _class_with, _draft, _set
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _auth, _make_user, _practice_session, _snapshot, _submit, client,
    clean_db, db, enqueued, setup_database, world,
)


@pytest.fixture(autouse=True)
def fresh_throttle(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_THROTTLE_BACKEND", "memory")
    login_throttle._backend = None
    yield
    login_throttle._backend = None


def _login(username, password="Password123!"):
    return client.post("/api/v1/auth/login", data={"username": username, "password": password})


# ---------------------------------------------------------------------------
# R1 — OQ-02 login throttling
# ---------------------------------------------------------------------------
def test_five_failures_block_further_attempts(db):
    _make_user(db, "victim", "STUDENT")
    _make_user(db, "bystander", "STUDENT")
    for _ in range(5):
        assert _login("victim", "nope").status_code == 401
    blocked = _login("victim")                               # even the right password
    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "LOGIN_RATE_LIMITED"
    assert blocked.headers["Retry-After"] == str(settings.LOGIN_WINDOW_SECONDS)
    assert _login("VICTIM").status_code == 429               # username is case-insensitive in the key
    assert _login("bystander").status_code == 200            # other accounts unaffected
    # No account lockout: the account itself is untouched
    assert db.scalar(select(User.status).where(User.username == "victim")) == "ACTIVE"


def test_success_resets_the_counter(db):
    _make_user(db, "forgetful", "STUDENT")
    for _ in range(4):
        _login("forgetful", "nope")
    assert _login("forgetful").status_code == 200
    for _ in range(4):
        assert _login("forgetful", "nope").status_code == 401
    assert _login("forgetful").status_code == 200


def test_redis_backend_shared_and_fails_open(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_THROTTLE_BACKEND", "redis")
    name, ip = f"redis-{uuid.uuid4().hex}", "203.0.113.7"
    a, b = throttle_mod.LoginThrottle(), throttle_mod.LoginThrottle()   # two API processes
    for _ in range(5):
        a.record_failure(name, ip)
    assert b.is_blocked(name, ip) is True
    b.reset(name, ip)
    assert a.is_blocked(name, ip) is False

    monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:1/0")      # Redis down
    down = throttle_mod.LoginThrottle()
    down.record_failure(name, ip)
    assert down.is_blocked(name, ip) is False                 # never blocks every login


# ---------------------------------------------------------------------------
# R2 — OQ-05 no self-modification
# ---------------------------------------------------------------------------
def test_admin_cannot_change_own_role_or_status(db):
    a1 = _make_user(db, "admin1", "ADMIN")
    a2 = _make_user(db, "admin2", "ADMIN")
    h1 = _auth("admin1")
    for body in ({"role": "TEACHER"}, {"status": "LOCKED"}):
        r = client.patch(f"/api/v1/admin/users/{a1.id}", json=body, headers=h1)
        assert r.status_code == 403 and r.json()["error_code"] == "SELF_MODIFICATION_FORBIDDEN"
    assert client.patch(f"/api/v1/admin/users/{a1.id}", json={"role": "ADMIN"}, headers=h1).status_code == 200   # no-op
    assert client.patch(f"/api/v1/admin/users/{a2.id}", json={"role": "TEACHER"}, headers=h1).status_code == 200  # another admin


# ---------------------------------------------------------------------------
# R3 — OQ-10 PUBLIC requires a class membership (REQ-PROB-003)
# ---------------------------------------------------------------------------
def test_public_problems_need_an_active_membership(db, world):
    w = world
    _make_user(db, "loner", "STUDENT")
    h = _auth("loner")
    pid = w["pid"]                                             # PUBLIC
    assert client.get(f"/api/v1/problems/{pid}", headers=h).status_code == 403
    r = client.post("/api/v1/my/practice/sessions", json={"problem_id": pid, "language": "PYTHON3"}, headers=h)
    assert r.status_code == 403 and r.json()["error_code"] == "PROBLEM_FORBIDDEN"
    assert client.get("/api/v1/problems/public/bank", headers=h).json()["total"] == 0
    assert client.get("/api/v1/my/practice/problems", headers=h).json()["total"] == 0
    assert client.get(f"/api/v1/problems/{pid}/samples", headers=h).status_code == 403

    code = client.post("/api/v1/classes", json={"name": "Open", "academic_year": "2026"}, headers=w["h_t"]).json()["invite_code"]
    assert client.post("/api/v1/my/classes/join", json={"invite_code": code}, headers=h).status_code == 201
    assert client.get(f"/api/v1/problems/{pid}", headers=h).status_code == 200
    assert client.get("/api/v1/problems/public/bank", headers=h).json()["total"] >= 1

    # Teachers keep reading other teachers' PUBLIC problems (domain §1, docs/41 R10)
    _make_user(db, "other_t", "TEACHER")
    assert client.get(f"/api/v1/problems/{pid}", headers=_auth("other_t")).status_code == 200


# ---------------------------------------------------------------------------
# R4 — OQ-01 one ACTIVE exam session per participation + problem
# ---------------------------------------------------------------------------
def test_exam_session_is_resumed_not_duplicated(db, world):
    w = world
    both = client.post("/api/v1/problems", json={"title": "Both", "description": "d", "visibility": "PUBLIC",
                                                 "supported_languages": ["PYTHON3", "CPP17"]}, headers=w["h_t"]).json()["id"]
    client.post(f"/api/v1/problems/{both}/test-cases", json={"input_data": "1 2\n", "expected_output": "3\n"}, headers=w["h_t"])
    cid = _class_with(w, w["student_id"])
    eid = _draft(w, cid=cid, pid=both)
    assert client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"]).status_code == 200
    now = datetime.now(timezone.utc)
    _set(eid, start_time=now - timedelta(minutes=5), end_time=now + timedelta(minutes=60), status="ONGOING")
    part = client.post(f"/api/v1/my/exams/{eid}/start", headers=w["h_s"]).json()["id"]
    start = lambda lang="PYTHON3": client.post(f"/api/v1/my/exam-sessions?participation_id={part}",  # noqa: E731
                                               json={"problem_id": both, "language": lang}, headers=w["h_s"])

    first = start()
    assert first.status_code == 201
    again = start()
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    other_lang = start("CPP17")
    assert other_lang.status_code == 409 and other_lang.json()["error_code"] == "EXAM_SESSION_ALREADY_ACTIVE"

    # After submit (D2) the next start opens a new session
    sid = first.json()["id"]
    assert _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n")).status_code == 201
    nxt = start()
    assert nxt.status_code == 201 and nxt.json()["id"] != sid
    active = db.scalars(select(CodingSession).where(CodingSession.exam_participation_id == uuid.UUID(part),
                                                    CodingSession.status == "ACTIVE")).all()
    assert len(active) == 1


# ---------------------------------------------------------------------------
# R5 — OQ-01 / OQ-13 stale practice sessions
# ---------------------------------------------------------------------------
def _age_session(sid, hours, trace_hours=None):
    t = datetime.now(timezone.utc) - timedelta(hours=hours)
    with TestingSessionLocal() as s:
        s.execute(text("UPDATE coding_sessions SET opened_at = :t WHERE id = :id"), {"t": t, "id": sid})
        if trace_hours is not None:
            s.execute(text("UPDATE trace_events SET server_timestamp = :t WHERE session_id = :id"),
                      {"t": datetime.now(timezone.utc) - timedelta(hours=trace_hours), "id": sid})
        s.commit()


def _ingest(h, sid):
    client.post(f"/api/v1/my/coding-sessions/{sid}/trace-events/batch", json={"events": [{
        "sequence_number": 1, "event_type": "EDITOR_CHANGED", "client_timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {}}]}, headers=h)


def test_stale_practice_sessions_are_abandoned(db, world):
    w = world
    idle = _practice_session(w)
    recent = _practice_session(w)
    old_but_active = _practice_session(w)
    _ingest(w["h_s"], old_but_active)
    stale_trace = _practice_session(w)
    _ingest(w["h_s"], stale_trace)
    _age_session(idle, 25)
    _age_session(old_but_active, 48, trace_hours=1)          # opened long ago, typing an hour ago
    _age_session(stale_trace, 48, trace_hours=30)

    with TestingSessionLocal() as s:
        abandoned = abandon_stale_practice_sessions(s)
    assert sorted(map(str, abandoned)) == sorted([idle, stale_trace])

    db.expire_all()
    for sid in (idle, stale_trace):
        s = db.get(CodingSession, uuid.UUID(sid))
        assert s.status == "ABANDONED" and s.termination_source == "SYSTEM_SESSION_POLICY"
    for sid in (recent, old_but_active):
        assert db.get(CodingSession, uuid.UUID(sid)).status == "ACTIVE"

    with TestingSessionLocal() as s:
        assert abandon_stale_practice_sessions(s) == []        # idempotent


def test_exam_sessions_are_left_to_the_timeout_path(db, world):
    w = world
    cid = _class_with(w, w["student_id"])
    eid = _draft(w, cid=cid, pid=w["pid"])
    client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"])
    now = datetime.now(timezone.utc)
    _set(eid, start_time=now - timedelta(minutes=5), end_time=now + timedelta(minutes=60), status="ONGOING")
    part = client.post(f"/api/v1/my/exams/{eid}/start", headers=w["h_s"]).json()["id"]
    sid = client.post(f"/api/v1/my/exam-sessions?participation_id={part}", json={"problem_id": w["pid"], "language": "PYTHON3"},
                      headers=w["h_s"]).json()["id"]
    _age_session(sid, 30)
    with TestingSessionLocal() as s:
        assert abandon_stale_practice_sessions(s) == []
    assert db.get(CodingSession, uuid.UUID(sid)).status == "ACTIVE"
