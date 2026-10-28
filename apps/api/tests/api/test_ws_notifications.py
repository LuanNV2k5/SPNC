"""Phase 09C — Teacher notification WebSocket (docs/35 AC-09-11).

Database:
    spnc_phase09_observation_test  (PostgreSQL only; guarded)
"""
import os
import queue
import threading
import uuid
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

PHASE09_DB_URL = os.environ.get(
    "PHASE09_DATABASE_URL",
    "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase09_observation_test",
)
os.environ["DATABASE_URL"] = PHASE09_DB_URL

from app.main import app
from app.db.session import get_db
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User, AccountStatus
from app.models.observation import AttentionSignal
from app.models.run_submit import Run
from app.realtime.hub import hub
from alembic.config import Config
from alembic import command

EXPECTED_DB_NAME = "spnc_phase09_observation_test"
WS_URL = "/api/v1/ws/teacher"


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
             full_name=username, role=role, status=AccountStatus.ACTIVE.value, force_password_change=False)
    db.add(u)
    db.commit()
    return u


def _token(username):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _receive(ws, timeout=5.0):
    """receive_json with a timeout so a missing notification fails instead of hanging."""
    box = queue.Queue()

    def worker():
        try:
            box.put(("ok", ws.receive_json()))
        except Exception as e:  # surfaced to the caller
            box.put(("err", e))

    threading.Thread(target=worker, daemon=True).start()
    try:
        kind, value = box.get(timeout=timeout)
    except queue.Empty:
        pytest.fail(f"no WebSocket message within {timeout}s")
    if kind == "err":
        raise value
    return value


@pytest.fixture
def world(db):
    t1, t2 = _make_user(db, "t1", "TEACHER"), _make_user(db, "t2", "TEACHER")
    s = _make_user(db, "stu", "STUDENT")
    tok1, tok2, toks = _token("t1"), _token("t2"), _token("stu")
    h1, hs = {"Authorization": f"Bearer {tok1}"}, {"Authorization": f"Bearer {toks}"}
    h2 = {"Authorization": f"Bearer {tok2}"}
    c1 = client.post("/api/v1/classes", json={"name": "C1", "academic_year": "2026"}, headers=h1).json()["id"]
    c2 = client.post("/api/v1/classes", json={"name": "C2", "academic_year": "2026"}, headers=h2).json()["id"]
    client.post(f"/api/v1/classes/{c1}/members", json={"student_id": str(s.id)}, headers=h1)
    client.post(f"/api/v1/classes/{c2}/members", json={"student_id": str(s.id)}, headers=h2)
    p1 = client.post("/api/v1/problems", json={"title": "P1", "description": "d", "visibility": "PUBLIC",
                                               "supported_languages": ["PYTHON3"]}, headers=h1).json()["id"]
    p2 = client.post("/api/v1/problems", json={"title": "P2", "description": "d", "visibility": "PUBLIC",
                                               "supported_languages": ["PYTHON3"]}, headers=h2).json()["id"]
    visible = client.post("/api/v1/my/practice/sessions", json={"problem_id": p1, "language": "PYTHON3"}, headers=hs).json()["id"]
    hidden = client.post("/api/v1/my/practice/sessions", json={"problem_id": p2, "language": "PYTHON3"}, headers=hs).json()["id"]
    return {"s": s, "tok1": tok1, "tok2": tok2, "toks": toks, "hs": hs, "c1": c1, "c2": c2,
            "visible": visible, "hidden": hidden}


def _connect_and_subscribe(token, class_id):
    ws = client.websocket_connect(WS_URL).__enter__()
    ws.send_json({"type": "auth", "access_token": token})
    assert _receive(ws) == {"type": "authenticated"}
    ws.send_json({"type": "subscribe", "class_id": class_id})
    assert _receive(ws) == {"type": "subscribed", "class_id": class_id}
    assert hub.wait_until_listening(5.0)
    return ws


def _insert_signal(db, student_id, session_id):
    sig = AttentionSignal(student_id=student_id, session_id=uuid.UUID(session_id), signal_type="IDLE_DETECTED",
                          status="NEW", rule_version="1.1.0", evidence={"duration_seconds": 400.0},
                          dedup_key=f"TEST:{uuid.uuid4()}")
    db.add(sig)
    db.commit()
    return sig


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def test_auth_timeout_closes(monkeypatch):
    monkeypatch.setattr(settings, "WS_AUTH_TIMEOUT_SECONDS", 0.5)
    with client.websocket_connect(WS_URL) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            _receive(ws)
        assert exc.value.code == 4401


def test_invalid_token_closes():
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"type": "auth", "access_token": "not-a-jwt"})
        with pytest.raises(WebSocketDisconnect) as exc:
            _receive(ws)
        assert exc.value.code == 4401


def test_student_token_refused(world):
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"type": "auth", "access_token": world["toks"]})
        with pytest.raises(WebSocketDisconnect) as exc:
            _receive(ws)
        assert exc.value.code == 4403


def test_foreign_class_subscription_refused(world):
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"type": "auth", "access_token": world["tok1"]})
        assert _receive(ws)["type"] == "authenticated"
        ws.send_json({"type": "subscribe", "class_id": world["c2"]})
        assert _receive(ws) == {"type": "error", "error_code": "FORBIDDEN_RESOURCE"}
        ws.send_json({"type": "subscribe"})
        assert _receive(ws) == {"type": "error", "error_code": "WS_INVALID_SUBSCRIPTION"}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
def test_signal_created_reaches_owner_only_for_visible_sessions(db, world):
    w = world
    ws = _connect_and_subscribe(w["tok1"], w["c1"])
    try:
        _insert_signal(db, w["s"].id, w["hidden"])     # not visible to T1 in C1 -> must not arrive
        sig = _insert_signal(db, w["s"].id, w["visible"])
        msg = _receive(ws)
        assert msg == {"type": "signal.created", "signal_id": str(sig.id), "session_id": w["visible"],
                       "student_id": str(w["s"].id), "signal_type": "IDLE_DETECTED"}
        assert "evidence" not in msg
    finally:
        ws.__exit__(None, None, None)


def test_run_completed_and_session_state(db, world):
    w = world
    snap = client.post(f"/api/v1/my/coding-sessions/{w['visible']}/snapshots",
                       json={"reason": "RUN", "language": "PYTHON3", "source_code": "print('secret code')\n",
                             "line_count": 1}, headers=w["hs"]).json()["id"]
    run = Run(session_id=uuid.UUID(w["visible"]), snapshot_id=uuid.UUID(snap), status="PENDING")
    db.add(run)
    db.commit()

    ws = _connect_and_subscribe(w["tok1"], w["c1"])
    try:
        run.status = "COMPLETED"
        run.verdict = "ACCEPTED"
        db.commit()
        msg = _receive(ws)
        assert msg == {"type": "run.completed", "run_id": str(run.id), "session_id": w["visible"],
                       "student_id": str(w["s"].id), "verdict": "ACCEPTED", "status": "COMPLETED"}

        assert client.post(f"/api/v1/my/practice/sessions/{w['visible']}/end", json={}, headers=w["hs"]).status_code == 200
        msg = _receive(ws)
        assert msg == {"type": "session.state", "session_id": w["visible"], "student_id": str(w["s"].id), "status": "ENDED"}
        assert "secret code" not in str(msg)
    finally:
        ws.__exit__(None, None, None)
