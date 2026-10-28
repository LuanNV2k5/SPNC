"""Phase 08E — Session Hardening Test Suite (docs/34_SESSION_HARDENING.md).

Covers AC-08E-02..10: server-side finalization, SESSION_ENDED, final_loc,
working time, termination actor integrity, reserved event type, flush guard
and ingest/finalize serialization.

Database:
    spnc_phase08e_session_test  (PostgreSQL only; guarded)
"""
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

PHASE08E_DB_URL = os.environ.get(
    "PHASE08E_DATABASE_URL",
    "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase08e_session_test",
)
os.environ["DATABASE_URL"] = PHASE08E_DB_URL

from app.main import app
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models.user import User, AccountStatus
from app.models.session import CodingSession, SessionStatus, TerminationSource
from app.models.trace import TraceEvent, TraceEventType
from app.models.observation import TraceSignalOutbox
from app.repositories import trace as trace_repo
from app.services import session_lifecycle
from app.services.storage import storage_adapter
from alembic.config import Config
from alembic import command

EXPECTED_DB_NAME = "spnc_phase08e_session_test"


def _assert_safe_db(url: str) -> None:
    db_name = urlparse(url).path.lstrip("/")
    if db_name != EXPECTED_DB_NAME:
        raise ValueError(f"UNSAFE DATABASE: '{db_name}'. Phase 08E tests require '{EXPECTED_DB_NAME}'.")


_assert_safe_db(PHASE08E_DB_URL)

engine = create_engine(PHASE08E_DB_URL)
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
    _assert_safe_db(PHASE08E_DB_URL)
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


def _make_user(db, username: str, role: str) -> User:
    u = User(
        username=username, email=f"{username}@spnc.io", password_hash=get_password_hash("Password123!"),
        full_name=username, role=role, status=AccountStatus.ACTIVE.value, force_password_change=False,
    )
    db.add(u)
    db.commit()
    return u


def _auth(username: str) -> dict:
    r = client.post("/api/v1/auth/login", data={"username": username, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def practice(db):
    """Returns (student auth headers, session_id) for a fresh ACTIVE practice session."""
    _make_user(db, "teacher_08e", "TEACHER")
    _make_user(db, "student_08e", "STUDENT")
    h_t, h_s = _auth("teacher_08e"), _auth("student_08e")
    r = client.post("/api/v1/problems", json={
        "title": "P08E", "description": "d", "visibility": "PUBLIC", "supported_languages": ["PYTHON3"],
    }, headers=h_t)
    assert r.status_code in (200, 201), r.text
    r = client.post("/api/v1/my/practice/sessions", json={"problem_id": r.json()["id"], "language": "PYTHON3"}, headers=h_s)
    assert r.status_code == 201, r.text
    return h_s, r.json()["id"]


def _ingest(h, sid, seqs, event_type="EDITOR_CHANGED"):
    events = [{"sequence_number": n, "event_type": event_type,
               "client_timestamp": datetime.now(timezone.utc).isoformat(), "payload": {"n": n}} for n in seqs]
    return client.post(f"/api/v1/my/coding-sessions/{sid}/trace-events/batch", json={"events": events}, headers=h)


def _snapshot(h, sid, code):
    r = client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots", json={
        "reason": "RUN", "language": "PYTHON3", "source_code": code, "line_count": len(code.splitlines()),
    }, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _end(h, sid, body=None):
    return client.post(f"/api/v1/my/practice/sessions/{sid}/end", json=body or {}, headers=h)


def _events(db, sid):
    return db.scalars(select(TraceEvent).where(TraceEvent.session_id == uuid.UUID(sid)).order_by(TraceEvent.sequence_number)).all()


# ---------------------------------------------------------------------------
# AC-08E-02 / 04 / 05 — final_loc, SESSION_ENDED, working time
# ---------------------------------------------------------------------------
def test_end_computes_final_loc_from_latest_snapshot_and_records_session_ended(db, practice):
    h, sid = practice
    assert _ingest(h, sid, [1, 2, 3]).status_code == 200
    _snapshot(h, sid, "a = 1\n")
    latest_id = _snapshot(h, sid, "def f():\n\n    return 1\n\nprint(f())\n")

    r = _end(h, sid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ENDED"
    assert body["termination_source"] == "STUDENT"
    assert body["final_loc"] == 3                       # D2: non-blank lines only
    assert body["final_code_snapshot_id"] == latest_id
    assert body["working_time_seconds"] >= 0

    events = _events(db, sid)
    ended = [e for e in events if e.event_type == TraceEventType.SESSION_ENDED.value]
    assert len(ended) == 1
    assert ended[0].sequence_number == 4                 # previous max + 1
    assert events[-1].id == ended[0].id
    assert ended[0].payload == {
        "source": "SERVER",
        "final_code_snapshot_id": latest_id,
        "final_loc": 3,
        "working_time_seconds": body["working_time_seconds"],
        "termination_actor": "STUDENT",
    }

    s = db.get(CodingSession, uuid.UUID(sid))
    assert s.final_loc == 3
    assert str(s.final_code_snapshot_id) == latest_id
    # D1: wall clock from server timestamps
    assert s.working_time_seconds == max(0, int((s.ended_at - s.opened_at).total_seconds()))


def test_session_ended_is_not_enqueued_for_signals(db, practice):
    h, sid = practice
    _end(h, sid)
    assert db.scalars(select(TraceSignalOutbox).where(TraceSignalOutbox.session_id == uuid.UUID(sid))).all() == []


# ---------------------------------------------------------------------------
# AC-08E-03 — no snapshot / unavailable content: no fabrication
# ---------------------------------------------------------------------------
def test_end_without_snapshot_leaves_final_loc_null(db, practice):
    h, sid = practice
    r = _end(h, sid)
    assert r.status_code == 200
    assert r.json()["final_loc"] is None
    assert r.json()["final_code_snapshot_id"] is None
    ended = _events(db, sid)[-1]
    assert ended.sequence_number == 1
    assert ended.payload["final_loc"] is None
    assert ended.payload["final_code_snapshot_id"] is None


def test_end_with_unavailable_snapshot_content_leaves_final_loc_null(db, practice):
    h, sid = practice
    snap_id = _snapshot(h, sid, "x = 1\ny = 2\n")
    from app.models.trace import CodeSnapshot
    object_key = db.get(CodeSnapshot, uuid.UUID(snap_id)).object_key
    storage_adapter._memory_store.pop(object_key)

    r = _end(h, sid)
    assert r.status_code == 200
    assert r.json()["final_loc"] is None
    assert r.json()["final_code_snapshot_id"] == snap_id


# ---------------------------------------------------------------------------
# AC-08E-06 — termination actor integrity (D5)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("source", ["SYSTEM_EXAM_TIMEOUT", "SYSTEM_SESSION_POLICY", "ANYTHING"])
def test_student_cannot_claim_system_termination_actor(db, practice, source):
    h, sid = practice
    r = _end(h, sid, {"termination_source": source})
    assert r.status_code == 422
    assert r.json()["error_code"] == "TERMINATION_SOURCE_FORBIDDEN"
    assert "request_id" in r.json()
    s = db.get(CodingSession, uuid.UUID(sid))
    assert s.status == SessionStatus.ACTIVE.value
    assert _events(db, sid) == []


def test_explicit_student_termination_source_still_accepted(practice):
    h, sid = practice
    r = _end(h, sid, {"termination_source": "STUDENT"})
    assert r.status_code == 200
    assert r.json()["termination_source"] == "STUDENT"


# ---------------------------------------------------------------------------
# AC-08E-07 — SESSION_ENDED reserved for the server (D4)
# ---------------------------------------------------------------------------
def test_client_session_ended_event_rejected(db, practice):
    h, sid = practice
    r = _ingest(h, sid, [1], event_type="SESSION_ENDED")
    assert r.status_code == 422
    assert r.json()["error_code"] == "TRACE_EVENT_TYPE_RESERVED"
    assert _events(db, sid) == []
    # ordinary ingest and exact-duplicate retry are unaffected
    assert _ingest(h, sid, [1, 2]).json()["accepted_count"] == 2
    assert _ingest(h, sid, [1, 2]).json()["accepted_count"] == 0


# ---------------------------------------------------------------------------
# D6 — flush guard
# ---------------------------------------------------------------------------
def test_flush_guard_rejects_end_until_trace_is_flushed(db, practice):
    h, sid = practice
    _ingest(h, sid, [1, 2])
    r = _end(h, sid, {"last_sequence_number": 5})
    assert r.status_code == 409
    assert r.json()["error_code"] == "TRACE_NOT_FLUSHED"
    assert db.get(CodingSession, uuid.UUID(sid)).status == SessionStatus.ACTIVE.value

    _ingest(h, sid, [3, 4, 5])
    r = _end(h, sid, {"last_sequence_number": 5})
    assert r.status_code == 200
    assert _events(db, sid)[-1].sequence_number == 6


# ---------------------------------------------------------------------------
# AC-08E-10 — double end, and no trace after end
# ---------------------------------------------------------------------------
def test_second_end_returns_409_without_second_event(db, practice):
    h, sid = practice
    assert _end(h, sid).status_code == 200
    r = _end(h, sid)
    assert r.status_code == 409
    assert r.json()["error_code"] == "SESSION_ALREADY_ENDED"
    assert len([e for e in _events(db, sid) if e.event_type == TraceEventType.SESSION_ENDED.value]) == 1


def test_ingest_after_end_is_rejected(db, practice):
    h, sid = practice
    _end(h, sid)
    r = _ingest(h, sid, [2])
    assert r.status_code == 403
    assert r.json()["error_code"] == "SESSION_NOT_ACTIVE"
    assert _events(db, sid)[-1].event_type == TraceEventType.SESSION_ENDED.value


# ---------------------------------------------------------------------------
# Internal abandon entry point (future stale policy)
# ---------------------------------------------------------------------------
def test_abandon_records_system_session_policy(db, practice):
    _, sid = practice
    s = session_lifecycle.abandon_session(db, uuid.UUID(sid))
    db.commit()
    assert s.status == SessionStatus.ABANDONED.value
    assert s.termination_source == TerminationSource.SYSTEM_SESSION_POLICY.value
    assert _events(db, sid)[-1].payload["termination_actor"] == "SYSTEM_SESSION_POLICY"


# ---------------------------------------------------------------------------
# AC-08E-08 / 09 — lock semantics
# ---------------------------------------------------------------------------
def test_finalize_waits_for_in_flight_ingest_and_sequences_after_it(practice):
    _, sid = practice
    sid = uuid.UUID(sid)
    ingest_tx = TestingSessionLocal()
    result = {}
    try:
        # In-flight ingest: holds FOR KEY SHARE and has inserted seq 1, not yet committed
        trace_repo.lock_session_for_ingest(ingest_tx, sid)
        trace_repo.bulk_insert_events(ingest_tx, sid, [{
            "session_id": sid, "sequence_number": 1, "event_type": "EDITOR_CHANGED",
            "client_timestamp": datetime.now(timezone.utc), "payload": {}, "canonical_fingerprint": "fp1",
        }])

        def finalize():
            tx = TestingSessionLocal()
            try:
                session_lifecycle.finalize_session(tx, sid, SessionStatus.ENDED, TerminationSource.STUDENT)
                tx.commit()
                result["ok"] = True
            except Exception as e:  # surfaced through the assertion below
                result["error"] = repr(e)
            finally:
                tx.close()

        t = threading.Thread(target=finalize)
        t.start()
        time.sleep(0.5)
        assert t.is_alive(), "finalize must block while ingest holds its lock"
        ingest_tx.commit()
        t.join(timeout=10)
        assert result.get("ok"), result
    finally:
        ingest_tx.close()

    with TestingSessionLocal() as check:
        events = check.scalars(select(TraceEvent).where(TraceEvent.session_id == sid).order_by(TraceEvent.sequence_number)).all()
        assert [(e.sequence_number, e.event_type) for e in events] == [(1, "EDITOR_CHANGED"), (2, "SESSION_ENDED")]


def test_ingest_lock_compatible_with_outbox_claim(practice):
    _, sid = practice
    sid = uuid.UUID(sid)
    worker_tx = TestingSessionLocal()
    ingest_tx = TestingSessionLocal()
    try:
        # Signal outbox worker claim: FOR NO KEY UPDATE
        worker_tx.execute(select(CodingSession).where(CodingSession.id == sid).with_for_update(key_share=True))
        ingest_tx.execute(text("SET LOCAL lock_timeout = '1s'"))
        assert trace_repo.lock_session_for_ingest(ingest_tx, sid) is not None
    finally:
        ingest_tx.rollback()
        worker_tx.rollback()
        ingest_tx.close()
        worker_tx.close()
