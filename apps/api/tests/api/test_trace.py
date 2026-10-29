"""Phase 06 — Digital Trace Test Suite."""
import os
import uuid
import datetime
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# --- MUST set DATABASE_URL before app import ---
PHASE06_DB_URL = "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase06_trace_test"
os.environ["DATABASE_URL"] = PHASE06_DB_URL

from app.main import app
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models.user import User, AccountStatus
from app.models.trace import TraceEventType
from alembic.config import Config
from alembic import command

# ===========================================================================
# DB GUARD — No unsafe database names allowed
# ===========================================================================

EXPECTED_DB_NAME = "spnc_phase06_trace_test"

def _assert_safe_db(url: str) -> None:
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/")
    if db_name != EXPECTED_DB_NAME:
        raise ValueError(
            f"UNSAFE DATABASE: '{db_name}'. "
            f"Phase 06 tests require '{EXPECTED_DB_NAME}'."
        )

_assert_safe_db(PHASE06_DB_URL)

engine = create_engine(PHASE06_DB_URL)
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
    _assert_safe_db(PHASE06_DB_URL)
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

@pytest.fixture(autouse=True)
def clean_db():
    _assert_safe_db(PHASE06_DB_URL)
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE users CASCADE;"))
        conn.commit()
    yield

@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===========================================================================
# Helpers
# ===========================================================================

def _make_user(db, username: str, role: str) -> User:
    u = User(
        username=username,
        email=f"{username}@spnc.io",
        password_hash=get_password_hash("Password123!"),
        full_name=username,
        role=role,
        status=AccountStatus.ACTIVE.value,
        force_password_change=False,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

def _login(username: str) -> str:
    r = client.post("/api/v1/auth/login", data={"username": username, "password": "Password123!"})
    assert r.status_code == 200
    return r.json()["access_token"]

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

def _create_trace_event(seq: int):
    return {
        "sequence_number": seq,
        "event_type": TraceEventType.EDITOR_CHANGED.value,
        "client_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "payload": {"content": f"code changes {seq}"}
    }

def _setup_session(db):
    t = _make_user(db, "teacher1", "TEACHER")
    s = _make_user(db, "student1", "STUDENT")
    t_tok = _login("teacher1")
    s_tok = _login("student1")
    
    r = client.post("/api/v1/classes", headers=_auth(t_tok), json={"name": "C1", "academic_year": "2026"})
    cls_id = r.json()["id"]
    client.post(f"/api/v1/classes/{cls_id}/members", headers=_auth(t_tok), json={"student_id": str(s.id)})
    
    r = client.post("/api/v1/problems", headers=_auth(t_tok), json={
        "title": "P1", "description": "D1",
        "visibility": "PUBLIC", "supported_languages": ["PYTHON3"]
    })
    prob_id = r.json()["id"]
    
    r = client.post("/api/v1/my/practice/sessions", headers=_auth(s_tok), json={"problem_id": prob_id, "language": "PYTHON3"})
    assert r.status_code == 201, f"Failed to start session: {r.text}"
    session_id = r.json()["id"]
    
    return t, s, t_tok, s_tok, cls_id, prob_id, session_id

# ===========================================================================
# Tests
# ===========================================================================

def test_t01_ingest_batch(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    
    req = {"events": [_create_trace_event(1), _create_trace_event(2)]}
    r = client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req)
    
    assert r.status_code == 200
    assert r.json()["accepted_count"] == 2
    assert r.json()["state"]["highest_contiguous_sequence"] == 2

def test_t02_trace_state(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    
    req = {"events": [_create_trace_event(1), _create_trace_event(3)]} # GAP!
    r = client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req)
    assert r.status_code == 200, f"Batch post failed: {r.text}"
    
    r = client.get(f"/api/v1/my/coding-sessions/{session_id}/trace-state", headers=_auth(s_tok))
    assert r.status_code == 200
    assert r.json()["highest_contiguous_sequence"] == 1

def test_t03_concurrency_exact_duplicate(db_session):
    # This verifies idempotency constraint behavior
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    req = {"events": [_create_trace_event(1)]}
    
    r1 = client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req)
    r2 = client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req)
    
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["accepted_count"] == 1
    assert r2.json()["accepted_count"] == 0 # Duplicates ignored natively

def test_t04_concurrency_conflict(db_session):
    # This verifies all-or-nothing rollback on conflict
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    req1 = {"events": [_create_trace_event(1)]}
    
    req2 = {"events": [_create_trace_event(1)]}
    req2["events"][0]["payload"] = {"content": "DIFFERENT CONTENT"}
    
    r1 = client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req1)
    r2 = client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req2)
    
    assert r1.status_code == 200
    assert r2.status_code == 409 # Conflict

def test_t05_threaded_concurrency(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    req = {"events": [_create_trace_event(1)]}
    
    import concurrent.futures
    
    def fire():
        return client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req)
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fire) for _ in range(5)]
        responses = [f.result() for f in concurrent.futures.as_completed(futures)]
        
    status_codes = [r.status_code for r in responses]
    accepted = [r.json().get("accepted_count", 0) for r in responses if r.status_code == 200]
    
    # Due to idempotency, one might accept 1, others accept 0, but no 500 errors!
    assert all(c == 200 for c in status_codes)
    assert sum(accepted) == 1


def test_t05b_concurrent_retries_never_conflict(db_session):
    """docs/42 §7: identical batches racing (client retries) are all accepted, one inserts.
    Before the ON CONFLICT fix the loser of the race got 409 intermittently (seen in CI)."""
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    import concurrent.futures

    for round_no in range(1, 6):
        req = {"events": [_create_trace_event(round_no * 10 + k) for k in range(3)]}

        def fire():
            return client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            responses = list(executor.map(lambda _: fire(), range(20)))
        assert [r.status_code for r in responses] == [200] * 20, [r.text for r in responses if r.status_code != 200][:2]
        assert sum(r.json()["accepted_count"] for r in responses) == 3


def test_t05c_conflicting_content_still_rejected(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    url = f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch"
    ev = _create_trace_event(1)
    assert client.post(url, headers=_auth(s_tok), json={"events": [ev]}).status_code == 200
    changed = {**ev, "payload": {"different": True}}
    assert client.post(url, headers=_auth(s_tok), json={"events": [changed]}).status_code == 409
    # Mixed batch: one new + one conflicting -> nothing from it is stored
    r = client.post(url, headers=_auth(s_tok), json={"events": [_create_trace_event(2), changed]})
    assert r.status_code == 409
    state = client.get(f"/api/v1/my/coding-sessions/{session_id}/trace-state", headers=_auth(s_tok)).json()
    assert state["highest_contiguous_sequence"] == 1

def test_r01_teacher_replay(db_session):
    _, s, t_tok, s_tok, cls_id, _, session_id = _setup_session(db_session)
    req = {"events": [_create_trace_event(1), _create_trace_event(2)]}
    client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req)
    
    r = client.get(f"/api/v1/classes/{cls_id}/students/{s.id}/sessions/{session_id}/trace-events", headers=_auth(t_tok))
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2
    assert r.json()["state"]["highest_contiguous_sequence"] == 2

def test_s01_snapshot(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    req = {
        "reason": "RUN",
        "language": "PYTHON3",
        "source_code": "print('hello')",
        "line_count": 1
    }
    r = client.post(f"/api/v1/my/coding-sessions/{session_id}/snapshots", headers=_auth(s_tok), json=req)
    assert r.status_code == 200
    assert r.json()["reason"] == "RUN"
    assert r.json()["object_key"].startswith(f"snapshots/{session_id}")

import pytest
import uuid
from app.models.session import SessionStatus

def test_N01_get_empty_scratchpad(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    resp = client.get(
        f"/api/v1/my/coding-sessions/{session_id}/scratchpad",
        headers=_auth(s_tok)
    )
    assert resp.status_code == 404
    data = resp.json()
    error_code = data.get("detail", {}).get("error_code") if "detail" in data else data.get("error_code")
    assert error_code == "NOT_FOUND"

def test_N02_put_scratchpad_active_session(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    payload = {
        "content": "some test notes",
        "client_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    resp = client.put(
        f"/api/v1/my/coding-sessions/{session_id}/scratchpad",
        headers=_auth(s_tok),
        json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "some test notes"
    assert data["revision_sequence"] == 1

def test_N03_put_exact_duplicate_scratchpad(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    payload = {
        "content": "some test notes", # same as N02 (assuming same test state or we'll just run it)
        "client_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    resp1 = client.put(
        f"/api/v1/my/coding-sessions/{session_id}/scratchpad",
        headers=_auth(s_tok),
        json=payload
    )
    assert resp1.status_code == 200
    
    resp2 = client.put(
        f"/api/v1/my/coding-sessions/{session_id}/scratchpad",
        headers=_auth(s_tok),
        json=payload
    )
    assert resp2.status_code == 200
    assert resp1.json()["revision_sequence"] == resp2.json()["revision_sequence"] # same sequence

def test_N04_put_new_content_scratchpad(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    payload = {
        "content": "some test notes",
        "client_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    client.put(
        f"/api/v1/my/coding-sessions/{session_id}/scratchpad",
        headers=_auth(s_tok),
        json=payload
    )
    
    payload2 = {
        "content": "some NEW notes",
        "client_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    resp = client.put(
        f"/api/v1/my/coding-sessions/{session_id}/scratchpad",
        headers=_auth(s_tok),
        json=payload2
    )
    assert resp.status_code == 200
    assert resp.json()["revision_sequence"] > 1
    assert resp.json()["content"] == "some NEW notes"

def test_N05_put_scratchpad_inactive_session(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    from app.models.session import CodingSession
    test_session = db_session.get(CodingSession, session_id)
    test_session.status = SessionStatus.ENDED.value
    db_session.commit()
    
    payload = {
        "content": "try to mutate after end",
        "client_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    resp = client.put(
        f"/api/v1/my/coding-sessions/{session_id}/scratchpad",
        headers=_auth(s_tok),
        json=payload
    )
    assert resp.status_code == 403
    data = resp.json()
    error_code = data.get("detail", {}).get("error_code") if isinstance(data.get("detail"), dict) else data.get("error_code")
    assert error_code == "SESSION_NOT_ACTIVE"

def test_N06_teacher_read_scratchpad(db_session):
    _, s, t_tok, _, cls_id, _, session_id = _setup_session(db_session)
    # write as student first
    from app.repositories.trace import save_scratchpad_revision
    save_scratchpad_revision(db_session, session_id, "for the teacher", datetime.datetime.now(datetime.timezone.utc), "fp123")
    save_scratchpad_revision(db_session, session_id, "second rev for teacher", datetime.datetime.now(datetime.timezone.utc), "fp456")
    db_session.commit()
    
    resp = client.get(
        f"/api/v1/classes/{cls_id}/students/{s.id}/sessions/{session_id}/scratchpad",
        headers=_auth(t_tok)
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "second rev for teacher"

def test_N07_teacher_read_scratchpad_history(db_session):
    _, s, t_tok, _, cls_id, _, session_id = _setup_session(db_session)
    from app.repositories.trace import save_scratchpad_revision
    save_scratchpad_revision(db_session, session_id, "rev 1", datetime.datetime.now(datetime.timezone.utc), "fp1")
    save_scratchpad_revision(db_session, session_id, "rev 2", datetime.datetime.now(datetime.timezone.utc), "fp2")
    db_session.commit()
    
    resp = client.get(
        f"/api/v1/classes/{cls_id}/students/{s.id}/sessions/{session_id}/scratchpad/history",
        headers=_auth(t_tok)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2

def test_X01_transaction_boundary_trace_service(db_session):
    _, _, _, s_tok, _, _, session_id = _setup_session(db_session)
    # create trace event 1
    req = {"events": [_create_trace_event(1)]}
    client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req)
    
    # attempt to insert event 2 and a conflicting event 1
    conflict_event = _create_trace_event(1)
    conflict_event["payload"]["content"] = "CONFLICTING CONTENT"
    req2 = {"events": [_create_trace_event(2), conflict_event]}
    resp = client.post(f"/api/v1/my/coding-sessions/{session_id}/trace-events/batch", headers=_auth(s_tok), json=req2)
    assert resp.status_code == 409
    
    # verify event 2 was NOT saved (because it rolled back the transaction)
    highest, _ = get_trace_state(db_session, session_id)
    assert highest == 1

def get_trace_state(db, session_id):
    from app.repositories.trace import get_trace_state
    return get_trace_state(db, session_id)
