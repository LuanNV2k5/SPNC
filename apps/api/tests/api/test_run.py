"""Phase 07 — Judge API Test Suite."""
import os
import uuid
import datetime
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PHASE07_DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase07_judge_test")
os.environ["DATABASE_URL"] = PHASE07_DB_URL

from app.main import app
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models.user import User, AccountStatus, RoleEnum
from app.models.session import CodingSession, SessionStatus
from app.models.trace import CodeSnapshot
from app.models.run_submit import Run, RunStatus
from alembic.config import Config
from alembic import command

EXPECTED_DB_NAME = "spnc_phase07_judge_test"

def _assert_safe_db(url: str) -> None:
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/")
    if db_name != EXPECTED_DB_NAME:
        raise ValueError(
            f"UNSAFE DATABASE: '{db_name}'. "
            f"Phase 07 tests require '{EXPECTED_DB_NAME}'."
        )

_assert_safe_db(PHASE07_DB_URL)

engine = create_engine(PHASE07_DB_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        pass

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    _assert_safe_db(PHASE07_DB_URL)
    # Ensure DB exists
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    try:
        conn = psycopg2.connect(PHASE07_DB_URL.rsplit("/", 1)[0] + "/postgres")
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS {EXPECTED_DB_NAME}")
        cur.execute(f"CREATE DATABASE {EXPECTED_DB_NAME}")
        cur.close()
        conn.close()
    except Exception as e:
        pass

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    # Only clean run data, leave reference data (users, problems, sessions, snapshots) alone unless necessary
    # Or clean runs before each test
    db = TestingSessionLocal()
    for table in reversed(Run.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()

# Helper to create test user
def create_user(db, role=RoleEnum.STUDENT, status=AccountStatus.ACTIVE):
    user = User(
        username=f"student_{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("pass"),
        full_name="Test User",
        role=role,
        status=status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def create_session(db, student_id, status=SessionStatus.ACTIVE):
    from app.models.problem import Problem
    from app.models.session import PracticeAttempt

    prob = Problem(
        title=f"Prob {uuid.uuid4().hex[:6]}",
        description="test",
        time_limit_ms=1000,
        memory_limit_mb=256,
        owner_id=student_id
    )
    db.add(prob)
    db.commit()
    
    pa = PracticeAttempt(
        student_id=student_id,
        problem_id=prob.id
    )
    db.add(pa)
    db.commit()

    sess = CodingSession(
        student_id=student_id,
        problem_id=prob.id,
        status=status,
        language="PYTHON3",
        is_exam_context=False,
        practice_attempt_id=pa.id
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess

def create_snapshot(db, session_id, language="CPP17"):
    snap = CodeSnapshot(
        session_id=session_id,
        reason="PERIODIC",
        language=language,
        source_hash="test",
        object_key="test",
        line_count=10
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap

# J01 Student creates Run for own ACTIVE session
def test_J01_student_create_run():
    db = TestingSessionLocal()
    user = create_user(db)
    sess = create_session(db, user.id)
    snap = create_snapshot(db, sess.id)
    db.close()

    resp = client.post(
        f"/api/v1/auth/login",
        data={"username": user.username, "password": "pass"}
    )
    token = resp.json()["access_token"]
    
    res = client.post(
        f"/api/v1/my/coding-sessions/{sess.id}/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"snapshot_id": str(snap.id)}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == str(sess.id)
    assert data["snapshot_id"] == str(snap.id)
    assert data["status"] == "PENDING"

# J02 Other student denied
def test_J02_other_student_denied():
    db = TestingSessionLocal()
    user1 = create_user(db)
    user2 = create_user(db)
    sess = create_session(db, user1.id)
    snap = create_snapshot(db, sess.id)
    db.close()

    resp = client.post(
        f"/api/v1/auth/login",
        data={"username": user2.username, "password": "pass"}
    )
    token = resp.json()["access_token"]
    
    res = client.post(
        f"/api/v1/my/coding-sessions/{sess.id}/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"snapshot_id": str(snap.id)}
    )
    assert res.status_code in [403, 404]

# J03 Teacher cannot create run
def test_J03_teacher_cannot_create_run():
    db = TestingSessionLocal()
    student = create_user(db)
    teacher = create_user(db, role=RoleEnum.TEACHER)
    sess = create_session(db, student.id)
    snap = create_snapshot(db, sess.id)
    db.close()

    resp = client.post(
        f"/api/v1/auth/login",
        data={"username": teacher.username, "password": "pass"}
    )
    token = resp.json()["access_token"]
    
    res = client.post(
        f"/api/v1/my/coding-sessions/{sess.id}/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"snapshot_id": str(snap.id)}
    )
    assert res.status_code == 403

# J04 Anonymous denied
def test_J04_anonymous_denied():
    res = client.post(
        f"/api/v1/my/coding-sessions/{uuid.uuid4()}/runs",
        json={"snapshot_id": str(uuid.uuid4())}
    )
    assert res.status_code == 401

# J05 disabled user denied
def test_J05_disabled_user_denied():
    db = TestingSessionLocal()
    user = create_user(db, status=AccountStatus.PENDING)
    # db.close()

    resp = client.post(
        f"/api/v1/auth/login",
        data={"username": user.username, "password": "pass"}
    )
    assert resp.status_code in [400, 401, 403]

# J06 locked user denied
def test_J06_locked_user_denied():
    db = TestingSessionLocal()
    user = create_user(db, status=AccountStatus.LOCKED)
    # db.close()

    resp = client.post(
        f"/api/v1/auth/login",
        data={"username": user.username, "password": "pass"}
    )
    assert resp.status_code in [400, 401, 403]

# J07 ENDED session rejected
def test_J07_ended_session_rejected():
    db = TestingSessionLocal()
    user = create_user(db)
    sess = create_session(db, user.id, status=SessionStatus.ENDED)
    snap = create_snapshot(db, sess.id)
    # db.close()

    resp = client.post(f"/api/v1/auth/login", data={"username": user.username, "password": "pass"})
    token = resp.json()["access_token"]
    res = client.post(f"/api/v1/my/coding-sessions/{sess.id}/runs", headers={"Authorization": f"Bearer {token}"}, json={"snapshot_id": str(snap.id)})
    assert res.status_code == 403
    assert "RUN_SESSION_NOT_ACTIVE" in str(res.json())

# J08 ABANDONED session rejected
def test_J08_abandoned_session_rejected():
    db = TestingSessionLocal()
    user = create_user(db)
    sess = create_session(db, user.id, status=SessionStatus.ABANDONED)
    snap = create_snapshot(db, sess.id)
    # db.close()

    resp = client.post(f"/api/v1/auth/login", data={"username": user.username, "password": "pass"})
    token = resp.json()["access_token"]
    res = client.post(f"/api/v1/my/coding-sessions/{sess.id}/runs", headers={"Authorization": f"Bearer {token}"}, json={"snapshot_id": str(snap.id)})
    assert res.status_code == 403
    assert "RUN_SESSION_NOT_ACTIVE" in str(res.json())

# J09 invalid snapshot rejected
def test_J09_invalid_snapshot():
    db = TestingSessionLocal()
    user = create_user(db)
    sess = create_session(db, user.id)
    # db.close()

    resp = client.post(f"/api/v1/auth/login", data={"username": user.username, "password": "pass"})
    token = resp.json()["access_token"]
    res = client.post(f"/api/v1/my/coding-sessions/{sess.id}/runs", headers={"Authorization": f"Bearer {token}"}, json={"snapshot_id": str(uuid.uuid4())})
    assert res.status_code == 404
    assert "RUN_SNAPSHOT_INVALID" in str(res.json())

# J10 cross-session snapshot rejected
def test_J10_cross_session_snapshot():
    db = TestingSessionLocal()
    user = create_user(db)
    sess1 = create_session(db, user.id)
    sess2 = create_session(db, user.id)
    snap = create_snapshot(db, sess1.id)
    # db.close()

    resp = client.post(f"/api/v1/auth/login", data={"username": user.username, "password": "pass"})
    token = resp.json()["access_token"]
    res = client.post(f"/api/v1/my/coding-sessions/{sess2.id}/runs", headers={"Authorization": f"Bearer {token}"}, json={"snapshot_id": str(snap.id)})
    assert res.status_code == 403
    assert "RUN_SNAPSHOT_INVALID" in str(res.json())

# J11 unsupported language rejected
def test_J11_unsupported_language():
    db = TestingSessionLocal()
    user = create_user(db)
    sess = create_session(db, user.id)
    snap = create_snapshot(db, sess.id, language="RUST")
    # db.close()

    resp = client.post(f"/api/v1/auth/login", data={"username": user.username, "password": "pass"})
    token = resp.json()["access_token"]
    res = client.post(f"/api/v1/my/coding-sessions/{sess.id}/runs", headers={"Authorization": f"Bearer {token}"}, json={"snapshot_id": str(snap.id)})
    assert res.status_code == 400
    assert "RUN_LANGUAGE_UNSUPPORTED" in str(res.json())

# J12 Run references exact snapshot (verified by schema and response)
def test_J12_run_snapshot_reference():
    db = TestingSessionLocal()
    user = create_user(db)
    sess = create_session(db, user.id)
    snap = create_snapshot(db, sess.id)
    # db.close()

    resp = client.post(f"/api/v1/auth/login", data={"username": user.username, "password": "pass"})
    token = resp.json()["access_token"]
    res = client.post(f"/api/v1/my/coding-sessions/{sess.id}/runs", headers={"Authorization": f"Bearer {token}"}, json={"snapshot_id": str(snap.id)})
    assert res.status_code == 200
    assert res.json()["snapshot_id"] == str(snap.id)

# J13 input persisted
def test_J13_input_persisted():
    db = TestingSessionLocal()
    user = create_user(db)
    sess = create_session(db, user.id)
    snap = create_snapshot(db, sess.id)
    # db.close()

    resp = client.post(f"/api/v1/auth/login", data={"username": user.username, "password": "pass"})
    token = resp.json()["access_token"]
    res = client.post(f"/api/v1/my/coding-sessions/{sess.id}/runs", headers={"Authorization": f"Bearer {token}"}, json={"snapshot_id": str(snap.id), "input": "hello_input"})
    assert res.status_code == 200
    
    db = TestingSessionLocal()
    run = db.get(Run, res.json()["id"])
    assert run.testcase_results["input"] == "hello_input"
    # db.close()

# J14 execution_time_ms persisted (simulated update)
def test_J14_execution_time_ms_persisted():
    db = TestingSessionLocal()
    user = create_user(db)
    sess = create_session(db, user.id)
    snap = create_snapshot(db, sess.id)
    
    resp = client.post(f"/api/v1/auth/login", data={"username": user.username, "password": "pass"})
    token = resp.json()["access_token"]
    res = client.post(f"/api/v1/my/coding-sessions/{sess.id}/runs", headers={"Authorization": f"Bearer {token}"}, json={"snapshot_id": str(snap.id)})
    
    run_id = res.json()["id"]
    from app.repositories.run import run_repository
    run_repository.write_result(db, run_id, 0, RunStatus.COMPLETED, "ACCEPTED", 1234, 50, {})
    
    run = db.get(Run, run_id)
    assert run.execution_time_ms == 1234
    # db.close()

# J15 own Run retrieval
def test_J15_own_run_retrieval():
    db = TestingSessionLocal()
    user = create_user(db)
    sess = create_session(db, user.id)
    snap = create_snapshot(db, sess.id)
    # db.close()

    resp = client.post(f"/api/v1/auth/login", data={"username": user.username, "password": "pass"})
    token = resp.json()["access_token"]
    res = client.post(f"/api/v1/my/coding-sessions/{sess.id}/runs", headers={"Authorization": f"Bearer {token}"}, json={"snapshot_id": str(snap.id)})
    run_id = res.json()["id"]
    
    get_res = client.get(f"/api/v1/my/coding-sessions/{sess.id}/runs/{run_id}", headers={"Authorization": f"Bearer {token}"})
    assert get_res.status_code == 200
    assert get_res.json()["id"] == run_id

# J16 unauthorized Run read denied
def test_J16_unauthorized_run_read_denied():
    db = TestingSessionLocal()
    user1 = create_user(db)
    user2 = create_user(db)
    sess = create_session(db, user1.id)
    snap = create_snapshot(db, sess.id)
    # db.close()

    resp1 = client.post(f"/api/v1/auth/login", data={"username": user1.username, "password": "pass"})
    token1 = resp1.json()["access_token"]
    res = client.post(f"/api/v1/my/coding-sessions/{sess.id}/runs", headers={"Authorization": f"Bearer {token1}"}, json={"snapshot_id": str(snap.id)})
    run_id = res.json()["id"]

    resp2 = client.post(f"/api/v1/auth/login", data={"username": user2.username, "password": "pass"})
    token2 = resp2.json()["access_token"]
    get_res = client.get(f"/api/v1/my/coding-sessions/{sess.id}/runs/{run_id}", headers={"Authorization": f"Bearer {token2}"})
    assert get_res.status_code == 403
