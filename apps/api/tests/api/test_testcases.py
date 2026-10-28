"""Phase 10A — Test case API (REQ-PROB-002; docs/36 AC-10-01).

Database:
    spnc_phase10_submission_test  (PostgreSQL only; guarded)
"""
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PHASE10_DB_URL = os.environ.get(
    "PHASE10_DATABASE_URL",
    "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase10_submission_test",
)
os.environ["DATABASE_URL"] = PHASE10_DB_URL

from app.main import app
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models.user import User, AccountStatus
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


def _auth(username):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def world(db):
    _make_user(db, "owner", "TEACHER")
    _make_user(db, "other_t", "TEACHER")
    _make_user(db, "stu", "STUDENT")
    h_owner, h_other, h_stu = _auth("owner"), _auth("other_t"), _auth("stu")
    pid = client.post("/api/v1/problems", json={"title": "Sum", "description": "d", "visibility": "PUBLIC",
                                                "supported_languages": ["PYTHON3"]}, headers=h_owner).json()["id"]
    return {"h_owner": h_owner, "h_other": h_other, "h_stu": h_stu, "pid": pid}


def _url(w, suffix=""):
    return f"/api/v1/problems/{w['pid']}/test-cases{suffix}"


def _add(w, **body):
    payload = {"input_data": "1 2\n", "expected_output": "3\n"}
    payload.update(body)
    return client.post(_url(w), json=payload, headers=w["h_owner"])


def test_owner_crud_and_auto_order(world):
    w = world
    r1 = _add(w, is_sample=True)
    assert r1.status_code == 201, r1.text
    assert r1.json()["order_index"] == 1 and r1.json()["is_sample"] is True and r1.json()["score_weight"] == 10
    r2 = _add(w, input_data="5 5\n", expected_output="10\n", score_weight=30)
    assert r2.json()["order_index"] == 2 and r2.json()["is_sample"] is False

    listed = client.get(_url(w), headers=w["h_owner"]).json()
    assert listed["total"] == 2
    assert [i["order_index"] for i in listed["items"]] == [1, 2]

    tc_id = r2.json()["id"]
    r = client.patch(_url(w, f"/{tc_id}"), json={"is_sample": True, "score_weight": 5}, headers=w["h_owner"])
    assert r.status_code == 200
    assert r.json()["is_sample"] is True and r.json()["score_weight"] == 5

    assert client.delete(_url(w, f"/{tc_id}"), headers=w["h_owner"]).status_code == 204
    assert client.get(_url(w), headers=w["h_owner"]).json()["total"] == 1


def test_order_index_conflict(world):
    w = world
    _add(w, order_index=3)
    r = _add(w, order_index=3)
    assert r.status_code == 409 and r.json()["error_code"] == "TEST_CASE_ORDER_TAKEN"


def test_validation(world):
    w = world
    assert _add(w, score_weight=-1).status_code == 422
    assert _add(w, unknown_field=1).status_code == 422
    assert client.post(_url(w), json={"input_data": "x"}, headers=w["h_owner"]).status_code == 422


def test_non_owner_and_student_cannot_manage(world):
    w = world
    tc_id = _add(w).json()["id"]
    for h in (w["h_other"], w["h_stu"]):
        assert client.get(_url(w), headers=h).status_code == 403
        assert client.post(_url(w), json={"expected_output": "1"}, headers=h).status_code == 403
        assert client.patch(_url(w, f"/{tc_id}"), json={"score_weight": 1}, headers=h).status_code == 403
        assert client.delete(_url(w, f"/{tc_id}"), headers=h).status_code == 403


def test_students_see_samples_only(world):
    w = world
    _add(w, input_data="SAMPLE_IN", expected_output="SAMPLE_OUT", is_sample=True)
    _add(w, input_data="SECRET_IN", expected_output="SECRET_OUT", is_sample=False)
    r = client.get(f"/api/v1/problems/{w['pid']}/samples", headers=w["h_stu"])
    assert r.status_code == 200
    assert r.json() == {"items": [{"order_index": 1, "input_data": "SAMPLE_IN", "expected_output": "SAMPLE_OUT"}]}
    assert "SECRET" not in r.text


def test_samples_require_problem_access(db, world):
    w = world
    private = client.post("/api/v1/problems", json={"title": "P", "description": "d", "visibility": "PRIVATE",
                                                    "supported_languages": ["PYTHON3"]}, headers=w["h_owner"]).json()["id"]
    assert client.get(f"/api/v1/problems/{private}/samples", headers=w["h_stu"]).status_code == 403


def test_edits_blocked_while_exam_running(db, world):
    w = world
    tc_id = _add(w).json()["id"]
    now = datetime.now(timezone.utc)
    eid = client.post("/api/v1/exams", json={"title": "E", "start_time": (now - timedelta(minutes=5)).isoformat(),
                                             "end_time": (now + timedelta(hours=1)).isoformat()},
                      headers=w["h_owner"]).json()["id"]
    assert client.post(f"/api/v1/exams/{eid}/problems", json={"problem_id": w["pid"], "order_index": 1},
                       headers=w["h_owner"]).status_code in (200, 201)
    for resp in (
        _add(w),
        client.patch(_url(w, f"/{tc_id}"), json={"score_weight": 1}, headers=w["h_owner"]),
        client.delete(_url(w, f"/{tc_id}"), headers=w["h_owner"]),
    ):
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "PROBLEM_IN_ONGOING_EXAM"
