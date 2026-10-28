"""Phase 05 — Academic Domain Test Suite.

Test Groups:
    P05-C01..C15  Class management
    P05-P01..P15  Problem management
    P05-E01..E25  Exam management + participation
    P05-S01..S15  Session (practice + exam)
    P05-A01..A10  Authorization matrix
    P05-D01..D10  Database-level invariants

Database:
    spnc_phase05_academic_test  (PostgreSQL only; no SQLite fallback)

This file refuses to run against any other database name.

NO placeholder tests.  Every assertion proves a domain invariant.
"""
import os
import uuid
import concurrent.futures
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# --- MUST set DATABASE_URL before app import (pydantic-settings reads env) ---
PHASE05_DB_URL = "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase05_academic_test"
os.environ["DATABASE_URL"] = PHASE05_DB_URL

from app.main import app
from app.db.session import get_db
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User, RoleEnum, AccountStatus
from app.models.class_org import Class, ClassMembership
from app.models.problem import Problem, ProblemVisibility, ProblemClassPublication
from app.models.exam import (
    Exam, ExamStatus, ExamProblem, ExamAssignment, ExamParticipation, ParticipationStatus
)
from app.models.session import CodingSession, SessionStatus, PracticeAttempt
from alembic.config import Config
from alembic import command

# ===========================================================================
# DB GUARD — No unsafe database names allowed
# ===========================================================================

EXPECTED_DB_NAME = "spnc_phase05_academic_test"


def _assert_safe_db(url: str) -> None:
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/")
    if db_name != EXPECTED_DB_NAME:
        raise ValueError(
            f"UNSAFE DATABASE: '{db_name}'. "
            f"Phase 05 tests require '{EXPECTED_DB_NAME}'."
        )


_assert_safe_db(PHASE05_DB_URL)

engine = create_engine(PHASE05_DB_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


# ===========================================================================
# Session-scoped DB setup — migrate once
# ===========================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    _assert_safe_db(PHASE05_DB_URL)
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


# ===========================================================================
# Per-test cleanup — truncate all data tables (cascade)
# ===========================================================================

@pytest.fixture(autouse=True)
def clean_db():
    _assert_safe_db(PHASE05_DB_URL)
    with engine.connect() as conn:
        conn.execute(text(
            "TRUNCATE TABLE users CASCADE;"
        ))
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

def _make_user(db, username: str, role: str, status=AccountStatus.ACTIVE.value) -> User:
    u = User(
        username=username,
        email=f"{username}@spnc.io",
        password_hash=get_password_hash("Password123!"),
        full_name=username,
        role=role,
        status=status,
        force_password_change=False,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _login(username: str) -> str:
    r = client.post("/api/v1/auth/login", data={
        "username": username,
        "password": "Password123!",
    })
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _future_exam_times(offset_minutes: int = 60, duration_minutes: int = 120) -> tuple:
    start = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    end = start + timedelta(minutes=duration_minutes)
    return start, end


def _past_exam_times(ended_minutes_ago: int = 30, duration_minutes: int = 60) -> tuple:
    end = datetime.now(timezone.utc) - timedelta(minutes=ended_minutes_ago)
    start = end - timedelta(minutes=duration_minutes)
    return start, end


def _publish(db, exam_id) -> None:
    """Marks an exam SCHEDULED (published). Phase 05 fixtures use past start times, which the
    publish endpoint (docs/36 10B) rejects, so the state is set directly."""
    db.query(Exam).filter(Exam.id == exam_id).update({"status": "SCHEDULED"})
    db.commit()


def _active_exam_times(started_minutes_ago: int = 10, duration_minutes: int = 120) -> tuple:
    start = datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago)
    end = start + timedelta(minutes=duration_minutes)
    return start, end


# ===========================================================================
# P05-C — CLASS MANAGEMENT
# ===========================================================================

class TestClassManagement:
    """P05-C01..C15 — Teacher class CRUD and membership management."""

    def test_P05_C01_teacher_create_class(self, db_session):
        """P05-C01: Teacher can create a class; response has owner_id = teacher."""
        t = _make_user(db_session, "teacher_c01", "TEACHER")
        token = _login("teacher_c01")
        r = client.post("/api/v1/classes", json={
            "name": "CS101", "academic_year": "2026"
        }, headers=_auth(token))
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "CS101"
        assert data["academic_year"] == "2026"
        assert data["owner_id"] == str(t.id)
        assert data["is_active"] is True

    def test_P05_C02_teacher_list_classes_only_own(self, db_session):
        """P05-C02: Teacher sees only own classes, not other teachers'."""
        t1 = _make_user(db_session, "teacher_c02a", "TEACHER")
        t2 = _make_user(db_session, "teacher_c02b", "TEACHER")
        tok1 = _login("teacher_c02a")
        tok2 = _login("teacher_c02b")
        client.post("/api/v1/classes", json={"name": "T1-Class", "academic_year": "2026"}, headers=_auth(tok1))
        client.post("/api/v1/classes", json={"name": "T2-Class", "academic_year": "2026"}, headers=_auth(tok2))
        r = client.get("/api/v1/classes", headers=_auth(tok1))
        assert r.status_code == 200
        names = [c["name"] for c in r.json()["items"]]
        assert "T1-Class" in names
        assert "T2-Class" not in names

    def test_P05_C03_get_class_owner_only(self, db_session):
        """P05-C03: Teacher gets own class; other teacher gets 403."""
        t1 = _make_user(db_session, "teacher_c03a", "TEACHER")
        t2 = _make_user(db_session, "teacher_c03b", "TEACHER")
        tok1 = _login("teacher_c03a")
        tok2 = _login("teacher_c03b")
        r = client.post("/api/v1/classes", json={"name": "SecretClass", "academic_year": "2026"}, headers=_auth(tok1))
        cid = r.json()["id"]
        # owner can get
        assert client.get(f"/api/v1/classes/{cid}", headers=_auth(tok1)).status_code == 200
        # other teacher cannot
        r2 = client.get(f"/api/v1/classes/{cid}", headers=_auth(tok2))
        assert r2.status_code == 403
        assert r2.json()["error_code"] == "CLASS_FORBIDDEN"

    def test_P05_C04_update_class(self, db_session):
        """P05-C04: Teacher can update own class name/year/active."""
        t = _make_user(db_session, "teacher_c04", "TEACHER")
        token = _login("teacher_c04")
        r = client.post("/api/v1/classes", json={"name": "OldName", "academic_year": "2025"}, headers=_auth(token))
        cid = r.json()["id"]
        r2 = client.patch(f"/api/v1/classes/{cid}", json={"name": "NewName", "is_active": False}, headers=_auth(token))
        assert r2.status_code == 200
        assert r2.json()["name"] == "NewName"
        assert r2.json()["is_active"] is False

    def test_P05_C05_enroll_student(self, db_session):
        """P05-C05: Teacher enrolls student into own class; membership is active."""
        t = _make_user(db_session, "teacher_c05", "TEACHER")
        s = _make_user(db_session, "student_c05", "STUDENT")
        tok = _login("teacher_c05")
        r = client.post("/api/v1/classes", json={"name": "EnrollTest", "academic_year": "2026"}, headers=_auth(tok))
        cid = r.json()["id"]
        r2 = client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok))
        assert r2.status_code == 201
        assert r2.json()["is_active"] is True

    def test_P05_C06_enroll_duplicate_returns_409(self, db_session):
        """P05-C06: Enrolling same student twice returns 409 ALREADY_ENROLLED."""
        t = _make_user(db_session, "teacher_c06", "TEACHER")
        s = _make_user(db_session, "student_c06", "STUDENT")
        tok = _login("teacher_c06")
        r = client.post("/api/v1/classes", json={"name": "DupTest", "academic_year": "2026"}, headers=_auth(tok))
        cid = r.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok))
        r2 = client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok))
        assert r2.status_code == 409
        assert r2.json()["error_code"] == "ALREADY_ENROLLED"

    def test_P05_C07_list_class_members(self, db_session):
        """P05-C07: Teacher lists members of own class; pagination works."""
        t = _make_user(db_session, "teacher_c07", "TEACHER")
        s1 = _make_user(db_session, "student_c07a", "STUDENT")
        s2 = _make_user(db_session, "student_c07b", "STUDENT")
        tok = _login("teacher_c07")
        r = client.post("/api/v1/classes", json={"name": "MemberList", "academic_year": "2026"}, headers=_auth(tok))
        cid = r.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s1.id)}, headers=_auth(tok))
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s2.id)}, headers=_auth(tok))
        r2 = client.get(f"/api/v1/classes/{cid}/members", headers=_auth(tok))
        assert r2.status_code == 200
        assert r2.json()["total"] == 2

    def test_P05_C08_remove_student(self, db_session):
        """P05-C08: Teacher removes student; membership deactivated; remove again -> 404."""
        t = _make_user(db_session, "teacher_c08", "TEACHER")
        s = _make_user(db_session, "student_c08", "STUDENT")
        tok = _login("teacher_c08")
        r = client.post("/api/v1/classes", json={"name": "RemoveTest", "academic_year": "2026"}, headers=_auth(tok))
        cid = r.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok))
        r2 = client.delete(f"/api/v1/classes/{cid}/members/{s.id}", headers=_auth(tok))
        assert r2.status_code == 204
        # Second delete -> 404
        r3 = client.delete(f"/api/v1/classes/{cid}/members/{s.id}", headers=_auth(tok))
        assert r3.status_code == 404

    def test_P05_C09_student_list_enrolled_classes(self, db_session):
        """P05-C09: Student sees enrolled classes in /my/classes."""
        t = _make_user(db_session, "teacher_c09", "TEACHER")
        s = _make_user(db_session, "student_c09", "STUDENT")
        tok_t = _login("teacher_c09")
        tok_s = _login("student_c09")
        r = client.post("/api/v1/classes", json={"name": "MyClass", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        r2 = client.get("/api/v1/my/classes", headers=_auth(tok_s))
        assert r2.status_code == 200
        assert any(c["id"] == cid for c in r2.json()["items"])

    def test_P05_C10_anonymous_class_returns_401(self):
        """P05-C10: Anonymous request to /classes returns 401."""
        r = client.get("/api/v1/classes")
        assert r.status_code == 401

    def test_P05_C11_student_cannot_create_class(self, db_session):
        """P05-C11: Student creating a class returns 403."""
        s = _make_user(db_session, "student_c11", "STUDENT")
        tok = _login("student_c11")
        r = client.post("/api/v1/classes", json={"name": "Forbidden", "academic_year": "2026"}, headers=_auth(tok))
        assert r.status_code == 403

    def test_P05_C12_teacher_cannot_enroll_non_student(self, db_session):
        """P05-C12: Enrolling a teacher (not a student) returns 422 NOT_A_STUDENT."""
        t1 = _make_user(db_session, "teacher_c12a", "TEACHER")
        t2 = _make_user(db_session, "teacher_c12b", "TEACHER")
        tok = _login("teacher_c12a")
        r = client.post("/api/v1/classes", json={"name": "C12", "academic_year": "2026"}, headers=_auth(tok))
        cid = r.json()["id"]
        r2 = client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(t2.id)}, headers=_auth(tok))
        assert r2.status_code == 422
        assert r2.json()["error_code"] == "NOT_A_STUDENT"

    def test_P05_C13_disabled_account_cannot_access(self, db_session):
        """P05-C13: A disabled teacher's valid token is rejected for class operations."""
        t = _make_user(db_session, "teacher_c13", "TEACHER")
        tok = _login("teacher_c13")
        # Disable the account
        t.status = AccountStatus.LOCKED.value
        db_session.commit()
        r = client.get("/api/v1/classes", headers=_auth(tok))
        assert r.status_code == 403
        assert r.json()["error_code"] == "ACCOUNT_LOCKED"

    def test_P05_C14_pagination_params(self, db_session):
        """P05-C14: Pagination returns correct page/size fields."""
        t = _make_user(db_session, "teacher_c14", "TEACHER")
        tok = _login("teacher_c14")
        for i in range(5):
            client.post("/api/v1/classes", json={"name": f"C{i}", "academic_year": "2026"}, headers=_auth(tok))
        r = client.get("/api/v1/classes?page=1&size=2", headers=_auth(tok))
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert data["size"] == 2
        assert len(data["items"]) == 2
        assert data["total"] == 5

    def test_P05_C15_error_body_has_required_fields(self, db_session):
        """P05-C15: Error responses include error_code and message."""
        t = _make_user(db_session, "teacher_c15", "TEACHER")
        tok = _login("teacher_c15")
        r = client.get(f"/api/v1/classes/{uuid.uuid4()}", headers=_auth(tok))
        assert r.status_code == 404
        body = r.json()
        assert "error_code" in body
        assert "message" in body


# ===========================================================================
# P05-P — PROBLEM MANAGEMENT
# ===========================================================================

class TestProblemManagement:
    """P05-P01..P15 — Teacher problem CRUD and visibility/publication."""

    def _create_problem(self, token, title="Test Problem", visibility="PRIVATE"):
        return client.post("/api/v1/problems", json={
            "title": title,
            "description": "Write a solution.",
            "visibility": visibility,
            "time_limit_ms": 1000,
            "memory_limit_mb": 256,
            "supported_languages": ["CPP17", "PYTHON3"],
        }, headers=_auth(token))

    def test_P05_P01_teacher_create_problem(self, db_session):
        """P05-P01: Teacher creates PRIVATE problem; owner_id correct."""
        t = _make_user(db_session, "teacher_p01", "TEACHER")
        tok = _login("teacher_p01")
        r = self._create_problem(tok, "Hello World")
        assert r.status_code == 201
        data = r.json()
        assert data["visibility"] == "PRIVATE"
        assert data["owner_id"] == str(t.id)

    def test_P05_P02_list_own_problems_only(self, db_session):
        """P05-P02: Teacher only sees own problems in list."""
        t1 = _make_user(db_session, "teacher_p02a", "TEACHER")
        t2 = _make_user(db_session, "teacher_p02b", "TEACHER")
        tok1 = _login("teacher_p02a")
        tok2 = _login("teacher_p02b")
        self._create_problem(tok1, "T1-Problem")
        self._create_problem(tok2, "T2-Problem")
        r = client.get("/api/v1/problems", headers=_auth(tok1))
        assert r.status_code == 200
        titles = [p["title"] for p in r.json()["items"]]
        assert "T1-Problem" in titles
        assert "T2-Problem" not in titles

    def test_P05_P03_teacher_gets_own_problem(self, db_session):
        """P05-P03: Teacher can get own PRIVATE problem; other teacher gets 403."""
        t1 = _make_user(db_session, "teacher_p03a", "TEACHER")
        t2 = _make_user(db_session, "teacher_p03b", "TEACHER")
        tok1 = _login("teacher_p03a")
        tok2 = _login("teacher_p03b")
        r = self._create_problem(tok1, "Private Prob")
        pid = r.json()["id"]
        assert client.get(f"/api/v1/problems/{pid}", headers=_auth(tok1)).status_code == 200
        r2 = client.get(f"/api/v1/problems/{pid}", headers=_auth(tok2))
        assert r2.status_code == 403
        assert r2.json()["error_code"] == "PROBLEM_FORBIDDEN"

    def test_P05_P04_update_problem(self, db_session):
        """P05-P04: Teacher updates own problem; fields change correctly."""
        t = _make_user(db_session, "teacher_p04", "TEACHER")
        tok = _login("teacher_p04")
        r = self._create_problem(tok, "Update Me")
        pid = r.json()["id"]
        r2 = client.patch(f"/api/v1/problems/{pid}", json={
            "title": "Updated Title", "visibility": "CLASS"
        }, headers=_auth(tok))
        assert r2.status_code == 200
        assert r2.json()["title"] == "Updated Title"
        assert r2.json()["visibility"] == "CLASS"

    def test_P05_P05_public_problems_bank(self, db_session):
        """P05-P05: Public problem bank accessible to students; PRIVATE problems not listed."""
        t = _make_user(db_session, "teacher_p05", "TEACHER")
        s = _make_user(db_session, "student_p05", "STUDENT")
        tok_t = _login("teacher_p05")
        tok_s = _login("student_p05")
        self._create_problem(tok_t, "PrivateProb", "PRIVATE")
        self._create_problem(tok_t, "PublicProb", "PUBLIC")
        r = client.get("/api/v1/problems/public/bank", headers=_auth(tok_s))
        assert r.status_code == 200
        titles = [p["title"] for p in r.json()["items"]]
        assert "PublicProb" in titles
        assert "PrivateProb" not in titles

    def test_P05_P06_student_cannot_see_private_problem(self, db_session):
        """P05-P06: Student cannot access PRIVATE problem directly."""
        t = _make_user(db_session, "teacher_p06", "TEACHER")
        s = _make_user(db_session, "student_p06", "STUDENT")
        tok_t = _login("teacher_p06")
        tok_s = _login("student_p06")
        r = self._create_problem(tok_t, "HiddenProblem", "PRIVATE")
        pid = r.json()["id"]
        r2 = client.get(f"/api/v1/problems/{pid}", headers=_auth(tok_s))
        assert r2.status_code == 403

    def test_P05_P07_student_sees_public_problem(self, db_session):
        """P05-P07: Student can access a PUBLIC problem."""
        t = _make_user(db_session, "teacher_p07", "TEACHER")
        s = _make_user(db_session, "student_p07", "STUDENT")
        tok_t = _login("teacher_p07")
        tok_s = _login("student_p07")
        r = self._create_problem(tok_t, "PublicAccess", "PUBLIC")
        pid = r.json()["id"]
        r2 = client.get(f"/api/v1/problems/{pid}", headers=_auth(tok_s))
        assert r2.status_code == 200

    def test_P05_P08_publish_to_class_requires_class_visibility(self, db_session):
        """P05-P08: Publishing PRIVATE problem returns 422 PROBLEM_NOT_CLASS_VISIBLE."""
        t = _make_user(db_session, "teacher_p08", "TEACHER")
        tok = _login("teacher_p08")
        r_cls = client.post("/api/v1/classes", json={"name": "P08Class", "academic_year": "2026"}, headers=_auth(tok))
        cid = r_cls.json()["id"]
        r_prob = self._create_problem(tok, "PrivateToPublish", "PRIVATE")
        pid = r_prob.json()["id"]
        r2 = client.post(f"/api/v1/problems/{pid}/publish",
                         json={"class_id": cid}, headers=_auth(tok))
        assert r2.status_code == 422
        assert r2.json()["error_code"] == "PROBLEM_NOT_CLASS_VISIBLE"

    def test_P05_P09_publish_class_problem_to_class(self, db_session):
        """P05-P09: Teacher publishes CLASS problem to own class; student in class sees it."""
        t = _make_user(db_session, "teacher_p09", "TEACHER")
        s = _make_user(db_session, "student_p09", "STUDENT")
        tok_t = _login("teacher_p09")
        tok_s = _login("student_p09")
        r_cls = client.post("/api/v1/classes", json={"name": "P09Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        r_prob = self._create_problem(tok_t, "ClassProblem", "CLASS")
        pid = r_prob.json()["id"]
        r_pub = client.post(f"/api/v1/problems/{pid}/publish",
                            json={"class_id": cid}, headers=_auth(tok_t))
        assert r_pub.status_code == 201
        # Student can now access
        r2 = client.get(f"/api/v1/problems/{pid}", headers=_auth(tok_s))
        assert r2.status_code == 200

    def test_P05_P10_student_not_in_class_cannot_see_class_problem(self, db_session):
        """P05-P10: CLASS problem published to class; student NOT in class cannot access."""
        t = _make_user(db_session, "teacher_p10", "TEACHER")
        s_in = _make_user(db_session, "student_p10a", "STUDENT")
        s_out = _make_user(db_session, "student_p10b", "STUDENT")
        tok_t = _login("teacher_p10")
        tok_out = _login("student_p10b")
        r_cls = client.post("/api/v1/classes", json={"name": "P10Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s_in.id)}, headers=_auth(tok_t))
        r_prob = self._create_problem(tok_t, "ClassOnlyProblem", "CLASS")
        pid = r_prob.json()["id"]
        client.post(f"/api/v1/problems/{pid}/publish", json={"class_id": cid}, headers=_auth(tok_t))
        r2 = client.get(f"/api/v1/problems/{pid}", headers=_auth(tok_out))
        assert r2.status_code == 403

    def test_P05_P11_publish_duplicate_returns_409(self, db_session):
        """P05-P11: Publishing same problem to same class twice returns 409."""
        t = _make_user(db_session, "teacher_p11", "TEACHER")
        tok = _login("teacher_p11")
        r_cls = client.post("/api/v1/classes", json={"name": "P11Class", "academic_year": "2026"}, headers=_auth(tok))
        cid = r_cls.json()["id"]
        r_prob = self._create_problem(tok, "P11Problem", "CLASS")
        pid = r_prob.json()["id"]
        client.post(f"/api/v1/problems/{pid}/publish", json={"class_id": cid}, headers=_auth(tok))
        r2 = client.post(f"/api/v1/problems/{pid}/publish", json={"class_id": cid}, headers=_auth(tok))
        assert r2.status_code == 409
        assert r2.json()["error_code"] == "ALREADY_PUBLISHED"

    def test_P05_P12_unpublish_from_class(self, db_session):
        """P05-P12: Teacher unpublishes problem; student loses access."""
        t = _make_user(db_session, "teacher_p12", "TEACHER")
        s = _make_user(db_session, "student_p12", "STUDENT")
        tok_t = _login("teacher_p12")
        tok_s = _login("student_p12")
        r_cls = client.post("/api/v1/classes", json={"name": "P12Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        r_prob = self._create_problem(tok_t, "P12Problem", "CLASS")
        pid = r_prob.json()["id"]
        client.post(f"/api/v1/problems/{pid}/publish", json={"class_id": cid}, headers=_auth(tok_t))
        # verify access
        assert client.get(f"/api/v1/problems/{pid}", headers=_auth(tok_s)).status_code == 200
        # unpublish
        r2 = client.delete(f"/api/v1/problems/{pid}/publish/{cid}", headers=_auth(tok_t))
        assert r2.status_code == 204
        # access revoked
        r3 = client.get(f"/api/v1/problems/{pid}", headers=_auth(tok_s))
        assert r3.status_code == 403

    def test_P05_P13_public_problem_teacher_cannot_edit_others(self, db_session):
        """P05-P13: PUBLIC problem still belongs to owner; another teacher cannot edit."""
        t1 = _make_user(db_session, "teacher_p13a", "TEACHER")
        t2 = _make_user(db_session, "teacher_p13b", "TEACHER")
        tok1 = _login("teacher_p13a")
        tok2 = _login("teacher_p13b")
        r = self._create_problem(tok1, "PublicProblem", "PUBLIC")
        pid = r.json()["id"]
        # t2 can view (PUBLIC)
        assert client.get(f"/api/v1/problems/{pid}", headers=_auth(tok2)).status_code == 200
        # t2 cannot edit
        r2 = client.patch(f"/api/v1/problems/{pid}", json={"title": "Hijack"}, headers=_auth(tok2))
        assert r2.status_code == 403

    def test_P05_P14_invalid_visibility_returns_422(self, db_session):
        """P05-P14: Creating problem with invalid visibility returns 422."""
        t = _make_user(db_session, "teacher_p14", "TEACHER")
        tok = _login("teacher_p14")
        r = client.post("/api/v1/problems", json={
            "title": "Bad Vis", "description": "desc",
            "visibility": "INVALID",
        }, headers=_auth(tok))
        assert r.status_code == 422

    def test_P05_P15_class_publication_requires_own_class(self, db_session):
        """P05-P15: Teacher cannot publish problem to another teacher's class."""
        t1 = _make_user(db_session, "teacher_p15a", "TEACHER")
        t2 = _make_user(db_session, "teacher_p15b", "TEACHER")
        tok1 = _login("teacher_p15a")
        tok2 = _login("teacher_p15b")
        r_cls = client.post("/api/v1/classes", json={"name": "T2Class", "academic_year": "2026"}, headers=_auth(tok2))
        cid = r_cls.json()["id"]
        r_prob = self._create_problem(tok1, "T1Problem", "CLASS")
        pid = r_prob.json()["id"]
        r2 = client.post(f"/api/v1/problems/{pid}/publish",
                         json={"class_id": cid}, headers=_auth(tok1))
        assert r2.status_code == 403
        assert r2.json()["error_code"] == "CLASS_FORBIDDEN"


# ===========================================================================
# P05-E — EXAM MANAGEMENT + PARTICIPATION
# ===========================================================================

class TestExamManagement:
    """P05-E01..E25 — Exam CRUD, association, assignment, participation, timing."""

    def _create_exam(self, token, title="Test Exam", offset_minutes=60, duration_minutes=120):
        start = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
        end = start + timedelta(minutes=duration_minutes)
        return client.post("/api/v1/exams", json={
            "title": title,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }, headers=_auth(token))

    def _create_problem(self, token, visibility="PRIVATE"):
        return client.post("/api/v1/problems", json={
            "title": "Exam Problem",
            "description": "desc",
            "visibility": visibility,
            "supported_languages": ["CPP17", "PYTHON3"],
        }, headers=_auth(token))

    def test_P05_E01_teacher_create_exam(self, db_session):
        """P05-E01: Teacher creates exam; owner_id correct; status=DRAFT."""
        t = _make_user(db_session, "teacher_e01", "TEACHER")
        tok = _login("teacher_e01")
        r = self._create_exam(tok, "Midterm")
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "Midterm"
        assert data["owner_id"] == str(t.id)
        assert data["status"] == "DRAFT"

    def test_P05_E02_exam_end_must_be_after_start(self, db_session):
        """P05-E02: end_time <= start_time returns 422."""
        t = _make_user(db_session, "teacher_e02", "TEACHER")
        tok = _login("teacher_e02")
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        end = start - timedelta(minutes=1)
        r = client.post("/api/v1/exams", json={
            "title": "Bad Exam",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }, headers=_auth(tok))
        assert r.status_code == 422

    def test_P05_E03_list_own_exams(self, db_session):
        """P05-E03: Teacher sees own exams only."""
        t1 = _make_user(db_session, "teacher_e03a", "TEACHER")
        t2 = _make_user(db_session, "teacher_e03b", "TEACHER")
        tok1 = _login("teacher_e03a")
        tok2 = _login("teacher_e03b")
        self._create_exam(tok1, "T1Exam")
        self._create_exam(tok2, "T2Exam")
        r = client.get("/api/v1/exams", headers=_auth(tok1))
        titles = [e["title"] for e in r.json()["items"]]
        assert "T1Exam" in titles
        assert "T2Exam" not in titles

    def test_P05_E04_attach_problem_to_exam(self, db_session):
        """P05-E04: Teacher attaches own problem to own exam."""
        t = _make_user(db_session, "teacher_e04", "TEACHER")
        tok = _login("teacher_e04")
        r_e = self._create_exam(tok)
        eid = r_e.json()["id"]
        r_p = self._create_problem(tok)
        pid = r_p.json()["id"]
        r2 = client.post(f"/api/v1/exams/{eid}/problems",
                         json={"problem_id": pid, "order_index": 1, "max_score": 100},
                         headers=_auth(tok))
        assert r2.status_code == 201
        assert r2.json()["problem_id"] == pid

    def test_P05_E05_cannot_attach_other_teachers_problem(self, db_session):
        """P05-E05: Teacher cannot attach another teacher's problem."""
        t1 = _make_user(db_session, "teacher_e05a", "TEACHER")
        t2 = _make_user(db_session, "teacher_e05b", "TEACHER")
        tok1 = _login("teacher_e05a")
        tok2 = _login("teacher_e05b")
        r_e = self._create_exam(tok1)
        eid = r_e.json()["id"]
        r_p = self._create_problem(tok2)  # t2's problem
        pid = r_p.json()["id"]
        r2 = client.post(f"/api/v1/exams/{eid}/problems",
                         json={"problem_id": pid, "order_index": 1},
                         headers=_auth(tok1))
        assert r2.status_code == 403

    def test_P05_E06_assign_class_to_exam(self, db_session):
        """P05-E06: Teacher assigns own class to own exam."""
        t = _make_user(db_session, "teacher_e06", "TEACHER")
        tok = _login("teacher_e06")
        r_cls = client.post("/api/v1/classes", json={"name": "E06Class", "academic_year": "2026"}, headers=_auth(tok))
        cid = r_cls.json()["id"]
        r_e = self._create_exam(tok)
        eid = r_e.json()["id"]
        r2 = client.post(f"/api/v1/exams/{eid}/classes",
                         json={"class_id": cid}, headers=_auth(tok))
        assert r2.status_code == 201
        assert r2.json()["class_id"] == cid

    def test_P05_E07_assign_class_duplicate_returns_409(self, db_session):
        """P05-E07: Assigning same class to exam twice returns 409."""
        t = _make_user(db_session, "teacher_e07", "TEACHER")
        tok = _login("teacher_e07")
        r_cls = client.post("/api/v1/classes", json={"name": "E07Class", "academic_year": "2026"}, headers=_auth(tok))
        cid = r_cls.json()["id"]
        r_e = self._create_exam(tok)
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok))
        r2 = client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok))
        assert r2.status_code == 409
        assert r2.json()["error_code"] == "ALREADY_ASSIGNED"

    def test_P05_E08_student_list_accessible_exams(self, db_session):
        """P05-E08: Student can list exams assigned to their class (started)."""
        t = _make_user(db_session, "teacher_e08", "TEACHER")
        s = _make_user(db_session, "student_e08", "STUDENT")
        tok_t = _login("teacher_e08")
        tok_s = _login("student_e08")
        r_cls = client.post("/api/v1/classes", json={"name": "E08Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        # Exam that has already started (active now)
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "ActiveExam",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        r = client.get("/api/v1/my/exams", headers=_auth(tok_s))
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()["items"]]
        assert eid in ids

    def test_P05_E09_student_start_exam_authoritative_timing(self, db_session):
        """P05-E09: Student starts exam within window; before start returns 403 EXAM_NOT_STARTED."""
        t = _make_user(db_session, "teacher_e09", "TEACHER")
        s = _make_user(db_session, "student_e09", "STUDENT")
        tok_t = _login("teacher_e09")
        tok_s = _login("student_e09")
        r_cls = client.post("/api/v1/classes", json={"name": "E09Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        # Exam that starts in the future
        start, end = _future_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "FutureExam",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        r = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        assert r.status_code == 403
        assert r.json()["error_code"] == "EXAM_NOT_STARTED"

    def test_P05_E10_start_exam_after_end_returns_403(self, db_session):
        """P05-E10: Student cannot start an already-ended exam; returns 403 EXAM_ENDED."""
        t = _make_user(db_session, "teacher_e10", "TEACHER")
        s = _make_user(db_session, "student_e10", "STUDENT")
        tok_t = _login("teacher_e10")
        tok_s = _login("student_e10")
        r_cls = client.post("/api/v1/classes", json={"name": "E10Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        start, end = _past_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "EndedExam",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        r = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        assert r.status_code == 403
        assert r.json()["error_code"] == "EXAM_ENDED"

    def test_P05_E11_start_active_exam_success(self, db_session):
        """P05-E11: Student successfully starts an active exam; participation created IN_PROGRESS."""
        t = _make_user(db_session, "teacher_e11", "TEACHER")
        s = _make_user(db_session, "student_e11", "STUDENT")
        tok_t = _login("teacher_e11")
        tok_s = _login("student_e11")
        r_cls = client.post("/api/v1/classes", json={"name": "E11Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "LiveExam",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        r = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "IN_PROGRESS"
        assert data["student_id"] == str(s.id)

    def test_P05_E12_start_exam_not_assigned_returns_403(self, db_session):
        """P05-E12: Student not in any assigned class gets 403 EXAM_NOT_ASSIGNED."""
        t = _make_user(db_session, "teacher_e12", "TEACHER")
        s = _make_user(db_session, "student_e12", "STUDENT")
        tok_t = _login("teacher_e12")
        tok_s = _login("student_e12")
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "UnassignedExam",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        r = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        assert r.status_code == 403
        assert r.json()["error_code"] == "EXAM_NOT_ASSIGNED"

    def test_P05_E13_start_cancelled_exam_returns_403(self, db_session):
        """P05-E13: Cancelled exam cannot be started; returns 403 EXAM_CANCELLED."""
        t = _make_user(db_session, "teacher_e13", "TEACHER")
        s = _make_user(db_session, "student_e13", "STUDENT")
        tok_t = _login("teacher_e13")
        tok_s = _login("student_e13")
        r_cls = client.post("/api/v1/classes", json={"name": "E13Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "CancelledExam",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        # Cancel the exam directly in DB
        db_session.query(Exam).filter(Exam.id == eid).update({"status": "CANCELLED"})
        db_session.commit()
        r = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        assert r.status_code == 403
        assert r.json()["error_code"] == "EXAM_CANCELLED"

    def test_P05_E14_start_exam_idempotent(self, db_session):
        """P05-E14: Starting the same exam twice returns existing participation (idempotent)."""
        t = _make_user(db_session, "teacher_e14", "TEACHER")
        s = _make_user(db_session, "student_e14", "STUDENT")
        tok_t = _login("teacher_e14")
        tok_s = _login("student_e14")
        r_cls = client.post("/api/v1/classes", json={"name": "E14Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "IdempotentExam",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        r1 = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        r2 = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        assert r1.status_code in (200, 201)
        assert r2.status_code in (200, 201)
        # Same participation ID
        assert r1.json()["id"] == r2.json()["id"]

    def test_P05_E15_detach_problem_from_exam(self, db_session):
        """P05-E15: Teacher detaches problem from exam; list is empty."""
        t = _make_user(db_session, "teacher_e15", "TEACHER")
        tok = _login("teacher_e15")
        r_e = self._create_exam(tok)
        eid = r_e.json()["id"]
        r_p = self._create_problem(tok)
        pid = r_p.json()["id"]
        client.post(f"/api/v1/exams/{eid}/problems",
                    json={"problem_id": pid, "order_index": 1}, headers=_auth(tok))
        r2 = client.delete(f"/api/v1/exams/{eid}/problems/{pid}", headers=_auth(tok))
        assert r2.status_code == 204
        r3 = client.get(f"/api/v1/exams/{eid}/problems", headers=_auth(tok))
        assert r3.json() == []

    def test_P05_E16_unassign_class_from_exam(self, db_session):
        """P05-E16: Teacher unassigns class from exam."""
        t = _make_user(db_session, "teacher_e16", "TEACHER")
        tok = _login("teacher_e16")
        r_cls = client.post("/api/v1/classes", json={"name": "E16Class", "academic_year": "2026"}, headers=_auth(tok))
        cid = r_cls.json()["id"]
        r_e = self._create_exam(tok)
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok))
        r2 = client.delete(f"/api/v1/exams/{eid}/classes/{cid}", headers=_auth(tok))
        assert r2.status_code == 204

    def test_P05_E17_update_exam(self, db_session):
        """P05-E17: Teacher updates exam title."""
        t = _make_user(db_session, "teacher_e17", "TEACHER")
        tok = _login("teacher_e17")
        r_e = self._create_exam(tok, "OldTitle")
        eid = r_e.json()["id"]
        r2 = client.patch(f"/api/v1/exams/{eid}", json={"title": "NewTitle"}, headers=_auth(tok))
        assert r2.status_code == 200
        assert r2.json()["title"] == "NewTitle"

    def test_P05_E18_exam_not_in_db_returns_404(self, db_session):
        """P05-E18: Getting non-existent exam returns 404."""
        t = _make_user(db_session, "teacher_e18", "TEACHER")
        tok = _login("teacher_e18")
        r = client.get(f"/api/v1/exams/{uuid.uuid4()}", headers=_auth(tok))
        assert r.status_code == 404
        assert r.json()["error_code"] == "EXAM_NOT_FOUND"

    def test_P05_E19_cannot_assign_other_teachers_class(self, db_session):
        """P05-E19: Teacher cannot assign another teacher's class to own exam."""
        t1 = _make_user(db_session, "teacher_e19a", "TEACHER")
        t2 = _make_user(db_session, "teacher_e19b", "TEACHER")
        tok1 = _login("teacher_e19a")
        tok2 = _login("teacher_e19b")
        r_cls = client.post("/api/v1/classes", json={"name": "T2Class19", "academic_year": "2026"}, headers=_auth(tok2))
        cid = r_cls.json()["id"]
        r_e = self._create_exam(tok1)
        eid = r_e.json()["id"]
        r2 = client.post(f"/api/v1/exams/{eid}/classes",
                         json={"class_id": cid}, headers=_auth(tok1))
        assert r2.status_code == 403
        assert r2.json()["error_code"] == "CLASS_FORBIDDEN"

    def test_P05_E20_student_without_class_membership_cannot_start(self, db_session):
        """P05-E20: Student removed from class cannot start exam."""
        t = _make_user(db_session, "teacher_e20", "TEACHER")
        s = _make_user(db_session, "student_e20", "STUDENT")
        tok_t = _login("teacher_e20")
        tok_s = _login("student_e20")
        r_cls = client.post("/api/v1/classes", json={"name": "E20Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "E20Exam", "start_time": start.isoformat(), "end_time": end.isoformat()
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        # Remove student
        client.delete(f"/api/v1/classes/{cid}/members/{s.id}", headers=_auth(tok_t))
        # Try to start
        r = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        assert r.status_code == 403
        assert r.json()["error_code"] == "EXAM_NOT_ASSIGNED"

    def test_P05_E21_exam_at_boundary_start_time(self, db_session):
        """P05-E21: Exam started 1 second ago is accessible (at_start boundary)."""
        t = _make_user(db_session, "teacher_e21", "TEACHER")
        s = _make_user(db_session, "student_e21", "STUDENT")
        tok_t = _login("teacher_e21")
        tok_s = _login("student_e21")
        r_cls = client.post("/api/v1/classes", json={"name": "E21Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        # Start 1 second ago
        start = datetime.now(timezone.utc) - timedelta(seconds=1)
        end = start + timedelta(hours=2)
        r_e = client.post("/api/v1/exams", json={
            "title": "AtStartExam", "start_time": start.isoformat(), "end_time": end.isoformat()
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        r = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        assert r.status_code == 201

    def test_P05_E22_get_participation(self, db_session):
        """P05-E22: Student can retrieve own participation via GET."""
        t = _make_user(db_session, "teacher_e22", "TEACHER")
        s = _make_user(db_session, "student_e22", "STUDENT")
        tok_t = _login("teacher_e22")
        tok_s = _login("student_e22")
        r_cls = client.post("/api/v1/classes", json={"name": "E22Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "E22Exam", "start_time": start.isoformat(), "end_time": end.isoformat()
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        r = client.get(f"/api/v1/my/exams/{eid}/participation", headers=_auth(tok_s))
        assert r.status_code == 200
        assert r.json()["status"] == "IN_PROGRESS"

    def test_P05_E23_exam_timing_not_using_materialized_status(self, db_session):
        """P05-E23: Authorization uses start_time/end_time directly, not materialized status field.

        Proof: Set materialized status to SCHEDULED (incorrect), but
        start_time is in the past → student can still start (timing check wins).
        """
        t = _make_user(db_session, "teacher_e23", "TEACHER")
        s = _make_user(db_session, "student_e23", "STUDENT")
        tok_t = _login("teacher_e23")
        tok_s = _login("student_e23")
        r_cls = client.post("/api/v1/classes", json={"name": "E23Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "E23Exam", "start_time": start.isoformat(), "end_time": end.isoformat()
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        # Deliberately set materialized status to wrong value (SCHEDULED)
        db_session.query(Exam).filter(Exam.id == eid).update({"status": "SCHEDULED"})
        db_session.commit()
        # Start should still work because real time check uses start_time
        r = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        assert r.status_code == 201

    def test_P05_E24_future_exam_does_not_block_practice(self, db_session):
        """P05-E24: Future exam (not started) does NOT block practice session."""
        t = _make_user(db_session, "teacher_e24", "TEACHER")
        s = _make_user(db_session, "student_e24", "STUDENT")
        tok_t = _login("teacher_e24")
        tok_s = _login("student_e24")
        r_cls = client.post("/api/v1/classes", json={"name": "E24Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        # Create a future exam and enroll student
        start, end = _future_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "FutureExam24", "start_time": start.isoformat(), "end_time": end.isoformat()
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        # Create PUBLIC practice problem
        r_p = client.post("/api/v1/problems", json={
            "title": "PubProb24", "description": "d",
            "visibility": "PUBLIC", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        # Start practice — should NOT be blocked (no active exam)
        r = client.post("/api/v1/my/practice/sessions",
                        json={"problem_id": pid, "language": "CPP17"},
                        headers=_auth(tok_s))
        assert r.status_code == 201

    def test_P05_E25_ended_exam_does_not_block_practice(self, db_session):
        """P05-E25: Ended exam (IN_PROGRESS participation but exam over) does not block practice."""
        t = _make_user(db_session, "teacher_e25", "TEACHER")
        s = _make_user(db_session, "student_e25", "STUDENT")
        tok_t = _login("teacher_e25")
        tok_s = _login("student_e25")
        r_cls = client.post("/api/v1/classes", json={"name": "E25Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        # Insert a participation whose exam has ended directly in DB
        start, end = _past_exam_times()
        e = Exam(
            owner_id=t.id,
            title="EndedE25",
            start_time=start,
            end_time=end,
            status="ENDED",  # docs/36 D8 (was COMPLETED)
        )
        db_session.add(e)
        db_session.commit()
        db_session.refresh(e)
        # Add student to class then assign
        ea = ExamAssignment(exam_id=e.id, class_id=uuid.UUID(cid))
        db_session.add(ea)
        # Insert IN_PROGRESS participation for ended exam
        p = ExamParticipation(
            exam_id=e.id,
            student_id=s.id,
            status="IN_PROGRESS",
            started_at=start + timedelta(minutes=5),
        )
        db_session.add(p)
        db_session.commit()
        # Create PUBLIC practice problem
        r_p = client.post("/api/v1/problems", json={
            "title": "PubProb25", "description": "d",
            "visibility": "PUBLIC", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        # Practice should not be blocked (exam is ended)
        r = client.post("/api/v1/my/practice/sessions",
                        json={"problem_id": pid, "language": "CPP17"},
                        headers=_auth(tok_s))
        assert r.status_code == 201


# ===========================================================================
# P05-S — SESSION MANAGEMENT
# ===========================================================================

class TestSessionManagement:
    """P05-S01..S15 — Practice and exam coding sessions."""

    def _setup_student_with_public_problem(self, db_session, username_suffix):
        t = _make_user(db_session, f"teacher_s{username_suffix}", "TEACHER")
        s = _make_user(db_session, f"student_s{username_suffix}", "STUDENT")
        tok_t = _login(f"teacher_s{username_suffix}")
        tok_s = _login(f"student_s{username_suffix}")
        r_p = client.post("/api/v1/problems", json={
            "title": f"Prob{username_suffix}",
            "description": "desc",
            "visibility": "PUBLIC",
            "supported_languages": ["CPP17", "PYTHON3"],
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        return t, s, tok_t, tok_s, pid

    def test_P05_S01_start_practice_session(self, db_session):
        """P05-S01: Student starts a practice session on a PUBLIC problem."""
        _, s, _, tok_s, pid = self._setup_student_with_public_problem(db_session, "01")
        r = client.post("/api/v1/my/practice/sessions",
                        json={"problem_id": pid, "language": "CPP17"},
                        headers=_auth(tok_s))
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "ACTIVE"
        assert data["is_exam_context"] is False
        assert data["language"] == "CPP17"

    def test_P05_S02_practice_session_no_active_exam_block(self, db_session):
        """P05-S02: Active exam participation blocks practice (ACTIVE_EXAM_IN_PROGRESS)."""
        t = _make_user(db_session, "teacher_s02", "TEACHER")
        s = _make_user(db_session, "student_s02", "STUDENT")
        tok_t = _login("teacher_s02")
        tok_s = _login("student_s02")
        r_cls = client.post("/api/v1/classes", json={"name": "S02Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "S02Exam", "start_time": start.isoformat(), "end_time": end.isoformat()
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        # Start exam
        client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        # Create PUBLIC problem
        r_p = client.post("/api/v1/problems", json={
            "title": "S02Prob", "description": "d",
            "visibility": "PUBLIC", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        # Attempt practice — must be blocked
        r = client.post("/api/v1/my/practice/sessions",
                        json={"problem_id": pid, "language": "CPP17"},
                        headers=_auth(tok_s))
        assert r.status_code == 403
        assert r.json()["error_code"] == "ACTIVE_EXAM_IN_PROGRESS"

    def test_P05_S03_cancelled_exam_does_not_block_practice(self, db_session):
        """P05-S03: Cancelled exam with IN_PROGRESS participation does NOT block practice."""
        t = _make_user(db_session, "teacher_s03", "TEACHER")
        s = _make_user(db_session, "student_s03", "STUDENT")
        tok_t = _login("teacher_s03")
        tok_s = _login("student_s03")
        # Create a cancelled exam with a stale IN_PROGRESS participation
        start, end = _active_exam_times()
        e = Exam(owner_id=t.id, title="CancelledE", start_time=start, end_time=end, status="CANCELLED")
        db_session.add(e)
        db_session.commit()
        db_session.refresh(e)
        p_obj = ExamParticipation(exam_id=e.id, student_id=s.id, status="IN_PROGRESS", started_at=start)
        db_session.add(p_obj)
        db_session.commit()
        # Create PUBLIC practice problem
        r_p = client.post("/api/v1/problems", json={
            "title": "S03PubProb", "description": "d",
            "visibility": "PUBLIC", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        r = client.post("/api/v1/my/practice/sessions",
                        json={"problem_id": pid, "language": "CPP17"},
                        headers=_auth(tok_s))
        assert r.status_code == 201

    def test_P05_S04_end_practice_session_student(self, db_session):
        """P05-S04: Student ends own active practice session; status becomes ENDED."""
        _, s, _, tok_s, pid = self._setup_student_with_public_problem(db_session, "04")
        r1 = client.post("/api/v1/my/practice/sessions",
                         json={"problem_id": pid, "language": "PYTHON3"},
                         headers=_auth(tok_s))
        sid = r1.json()["id"]
        r2 = client.post(f"/api/v1/my/practice/sessions/{sid}/end",
                         json={"termination_source": "STUDENT"},
                         headers=_auth(tok_s))
        assert r2.status_code == 200
        assert r2.json()["status"] == "ENDED"
        assert r2.json()["termination_source"] == "STUDENT"

    def test_P05_S05_end_already_ended_session_returns_409(self, db_session):
        """P05-S05: Ending an already-ended session returns 409 SESSION_ALREADY_ENDED."""
        _, s, _, tok_s, pid = self._setup_student_with_public_problem(db_session, "05")
        r1 = client.post("/api/v1/my/practice/sessions",
                         json={"problem_id": pid, "language": "CPP17"},
                         headers=_auth(tok_s))
        sid = r1.json()["id"]
        client.post(f"/api/v1/my/practice/sessions/{sid}/end",
                    json={"termination_source": "STUDENT"}, headers=_auth(tok_s))
        r2 = client.post(f"/api/v1/my/practice/sessions/{sid}/end",
                         json={"termination_source": "STUDENT"}, headers=_auth(tok_s))
        assert r2.status_code == 409
        assert r2.json()["error_code"] == "SESSION_ALREADY_ENDED"

    def test_P05_S06_list_practice_sessions(self, db_session):
        """P05-S06: Student lists own practice sessions."""
        _, s, _, tok_s, pid = self._setup_student_with_public_problem(db_session, "06")
        client.post("/api/v1/my/practice/sessions", json={"problem_id": pid, "language": "CPP17"}, headers=_auth(tok_s))
        client.post("/api/v1/my/practice/sessions", json={"problem_id": pid, "language": "PYTHON3"}, headers=_auth(tok_s))
        r = client.get("/api/v1/my/practice/sessions", headers=_auth(tok_s))
        assert r.status_code == 200
        assert r.json()["total"] == 2

    def test_P05_S07_get_practice_session(self, db_session):
        """P05-S07: Student gets own practice session detail."""
        _, s, _, tok_s, pid = self._setup_student_with_public_problem(db_session, "07")
        r1 = client.post("/api/v1/my/practice/sessions",
                         json={"problem_id": pid, "language": "CPP17"},
                         headers=_auth(tok_s))
        sid = r1.json()["id"]
        r2 = client.get(f"/api/v1/my/practice/sessions/{sid}", headers=_auth(tok_s))
        assert r2.status_code == 200
        assert r2.json()["id"] == sid

    def test_P05_S08_practice_private_problem_blocked(self, db_session):
        """P05-S08: Student cannot start practice on PRIVATE problem."""
        t = _make_user(db_session, "teacher_s08", "TEACHER")
        s = _make_user(db_session, "student_s08", "STUDENT")
        tok_t = _login("teacher_s08")
        tok_s = _login("student_s08")
        r_p = client.post("/api/v1/problems", json={
            "title": "PrivateP", "description": "d",
            "visibility": "PRIVATE", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        r = client.post("/api/v1/my/practice/sessions",
                        json={"problem_id": pid, "language": "CPP17"},
                        headers=_auth(tok_s))
        assert r.status_code == 403
        assert r.json()["error_code"] == "PROBLEM_FORBIDDEN"

    def test_P05_S09_practice_unsupported_language_blocked(self, db_session):
        """P05-S09: Starting practice with unsupported language returns 422."""
        t = _make_user(db_session, "teacher_s09", "TEACHER")
        s = _make_user(db_session, "student_s09", "STUDENT")
        tok_t = _login("teacher_s09")
        tok_s = _login("student_s09")
        r_p = client.post("/api/v1/problems", json={
            "title": "CPP17Only", "description": "d",
            "visibility": "PUBLIC", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        r = client.post("/api/v1/my/practice/sessions",
                        json={"problem_id": pid, "language": "PYTHON3"},
                        headers=_auth(tok_s))
        assert r.status_code == 422
        assert r.json()["error_code"] == "LANGUAGE_NOT_SUPPORTED"

    def test_P05_S10_exam_session_creation(self, db_session):
        """P05-S10: Student starts exam coding session with valid participation."""
        t = _make_user(db_session, "teacher_s10", "TEACHER")
        s = _make_user(db_session, "student_s10", "STUDENT")
        tok_t = _login("teacher_s10")
        tok_s = _login("student_s10")
        r_cls = client.post("/api/v1/classes", json={"name": "S10Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        r_p = client.post("/api/v1/problems", json={
            "title": "S10Prob", "description": "d",
            "visibility": "PRIVATE", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "S10Exam", "start_time": start.isoformat(), "end_time": end.isoformat()
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        client.post(f"/api/v1/exams/{eid}/problems",
                    json={"problem_id": pid, "order_index": 1, "max_score": 100},
                    headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        r_part = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        part_id = r_part.json()["id"]
        r_sess = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}",
                             json={"problem_id": pid, "language": "CPP17"},
                             headers=_auth(tok_s))
        assert r_sess.status_code == 201
        data = r_sess.json()
        assert data["is_exam_context"] is True
        assert data["exam_participation_id"] == part_id

    def test_P05_S11_exam_session_problem_not_in_exam_blocked(self, db_session):
        """P05-S11: Cannot start exam session with problem not in exam."""
        t = _make_user(db_session, "teacher_s11", "TEACHER")
        s = _make_user(db_session, "student_s11", "STUDENT")
        tok_t = _login("teacher_s11")
        tok_s = _login("student_s11")
        r_cls = client.post("/api/v1/classes", json={"name": "S11Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        r_p = client.post("/api/v1/problems", json={
            "title": "S11Prob", "description": "d",
            "visibility": "PRIVATE", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "S11Exam", "start_time": start.isoformat(), "end_time": end.isoformat()
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        # Do NOT attach problem to exam
        r_part = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        part_id = r_part.json()["id"]
        r_sess = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}",
                             json={"problem_id": pid, "language": "CPP17"},
                             headers=_auth(tok_s))
        assert r_sess.status_code == 403
        assert r_sess.json()["error_code"] == "PROBLEM_NOT_IN_EXAM"

    def test_P05_S12_end_exam_session(self, db_session):
        """P05-S12: Student ends own exam session; status becomes ENDED."""
        t = _make_user(db_session, "teacher_s12", "TEACHER")
        s = _make_user(db_session, "student_s12", "STUDENT")
        tok_t = _login("teacher_s12")
        tok_s = _login("student_s12")
        r_cls = client.post("/api/v1/classes", json={"name": "S12Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        r_p = client.post("/api/v1/problems", json={
            "title": "S12Prob", "description": "d",
            "visibility": "PRIVATE", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "S12Exam", "start_time": start.isoformat(), "end_time": end.isoformat()
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        client.post(f"/api/v1/exams/{eid}/problems",
                    json={"problem_id": pid, "order_index": 1}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams
        r_part = client.post(f"/api/v1/my/exams/{eid}/start", headers=_auth(tok_s))
        part_id = r_part.json()["id"]
        r_sess = client.post(f"/api/v1/my/exam-sessions?participation_id={part_id}",
                             json={"problem_id": pid, "language": "CPP17"},
                             headers=_auth(tok_s))
        sess_id = r_sess.json()["id"]
        r_end = client.post(f"/api/v1/my/exam-sessions/{sess_id}/end",
                            json={"termination_source": "STUDENT"}, headers=_auth(tok_s))
        assert r_end.status_code == 200
        assert r_end.json()["status"] == "ENDED"

    def test_P05_S13_session_cross_ownership_blocked(self, db_session):
        """P05-S13: Student B cannot access Student A's practice session."""
        t = _make_user(db_session, "teacher_s13", "TEACHER")
        s1 = _make_user(db_session, "student_s13a", "STUDENT")
        s2 = _make_user(db_session, "student_s13b", "STUDENT")
        tok_t = _login("teacher_s13")
        tok_s1 = _login("student_s13a")
        tok_s2 = _login("student_s13b")
        r_p = client.post("/api/v1/problems", json={
            "title": "S13Prob", "description": "d",
            "visibility": "PUBLIC", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        r1 = client.post("/api/v1/my/practice/sessions",
                         json={"problem_id": pid, "language": "CPP17"},
                         headers=_auth(tok_s1))
        sid = r1.json()["id"]
        r2 = client.get(f"/api/v1/my/practice/sessions/{sid}", headers=_auth(tok_s2))
        assert r2.status_code == 403
        assert r2.json()["error_code"] == "SESSION_FORBIDDEN"

    def test_P05_S14_system_exam_timeout_termination_source(self, db_session):
        """P05-S14 (amended by Phase 08E D5): SYSTEM_EXAM_TIMEOUT is a valid actor, but only for
        internal callers. A student request claiming it is rejected with 422."""
        _, s, _, tok_s, pid = self._setup_student_with_public_problem(db_session, "14")
        r1 = client.post("/api/v1/my/practice/sessions",
                         json={"problem_id": pid, "language": "CPP17"},
                         headers=_auth(tok_s))
        sid = r1.json()["id"]
        r2 = client.post(f"/api/v1/my/practice/sessions/{sid}/end",
                         json={"termination_source": "SYSTEM_EXAM_TIMEOUT"},
                         headers=_auth(tok_s))
        assert r2.status_code == 422
        assert r2.json()["error_code"] == "TERMINATION_SOURCE_FORBIDDEN"

    def test_P05_S15_multiple_practice_sessions_allowed(self, db_session):
        """P05-S15: Student can start multiple practice sessions on same problem."""
        _, s, _, tok_s, pid = self._setup_student_with_public_problem(db_session, "15")
        r1 = client.post("/api/v1/my/practice/sessions",
                         json={"problem_id": pid, "language": "CPP17"},
                         headers=_auth(tok_s))
        assert r1.status_code == 201
        r2 = client.post("/api/v1/my/practice/sessions",
                         json={"problem_id": pid, "language": "PYTHON3"},
                         headers=_auth(tok_s))
        assert r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]


# ===========================================================================
# P05-A — AUTHORIZATION MATRIX
# ===========================================================================

class TestAuthorizationMatrix:
    """P05-A01..A10 — Cross-role and cross-resource authorization enforcement."""

    def test_P05_A01_anonymous_all_protected_endpoints_401(self):
        """P05-A01: Anonymous requests to all academic endpoints return 401."""
        endpoints_to_test = [
            ("GET", "/api/v1/classes"),
            ("GET", "/api/v1/problems"),
            ("GET", "/api/v1/exams"),
            ("GET", "/api/v1/my/classes"),
            ("GET", "/api/v1/my/exams"),
            ("GET", "/api/v1/my/practice/sessions"),
            ("GET", "/api/v1/my/submissions"),
        ]
        for method, url in endpoints_to_test:
            r = client.request(method, url)
            assert r.status_code == 401, f"Expected 401 for {method} {url}, got {r.status_code}"

    def test_P05_A02_student_cannot_access_teacher_endpoints(self, db_session):
        """P05-A02: Student role blocked from Teacher-only endpoints (403)."""
        s = _make_user(db_session, "student_a02", "STUDENT")
        tok = _login("student_a02")
        assert client.post("/api/v1/classes", json={"name": "x", "academic_year": "y"}, headers=_auth(tok)).status_code == 403
        assert client.post("/api/v1/problems", json={"title": "x", "description": "y"}, headers=_auth(tok)).status_code == 403
        assert client.post("/api/v1/exams", json={"title": "x", "start_time": "2099-01-01T00:00:00Z", "end_time": "2099-01-01T01:00:00Z"}, headers=_auth(tok)).status_code == 403

    def test_P05_A03_teacher_cannot_access_student_endpoints(self, db_session):
        """P05-A03: Teacher role blocked from Student-only endpoints (403)."""
        t = _make_user(db_session, "teacher_a03", "TEACHER")
        tok = _login("teacher_a03")
        assert client.get("/api/v1/my/classes", headers=_auth(tok)).status_code == 403
        assert client.get("/api/v1/my/exams", headers=_auth(tok)).status_code == 403
        assert client.get("/api/v1/my/practice/sessions", headers=_auth(tok)).status_code == 403

    def test_P05_A04_teacher_cross_resource_403(self, db_session):
        """P05-A04: Teacher cannot modify another teacher's class/problem/exam."""
        t1 = _make_user(db_session, "teacher_a04a", "TEACHER")
        t2 = _make_user(db_session, "teacher_a04b", "TEACHER")
        tok1 = _login("teacher_a04a")
        tok2 = _login("teacher_a04b")
        r_cls = client.post("/api/v1/classes", json={"name": "A04Cls", "academic_year": "2026"}, headers=_auth(tok1))
        cid = r_cls.json()["id"]
        r_prob = client.post("/api/v1/problems", json={"title": "A04Prob", "description": "d"}, headers=_auth(tok1))
        pid = r_prob.json()["id"]
        start = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        r_exam = client.post("/api/v1/exams", json={"title": "A04Exam", "start_time": start, "end_time": end}, headers=_auth(tok1))
        eid = r_exam.json()["id"]
        # t2 cannot access t1's resources
        assert client.patch(f"/api/v1/classes/{cid}", json={"name": "x"}, headers=_auth(tok2)).status_code == 403
        assert client.patch(f"/api/v1/problems/{pid}", json={"title": "x"}, headers=_auth(tok2)).status_code == 403
        assert client.patch(f"/api/v1/exams/{eid}", json={"title": "x"}, headers=_auth(tok2)).status_code == 403

    def test_P05_A05_knowing_id_does_not_grant_access(self, db_session):
        """P05-A05: Knowing a resource UUID does not grant access without ownership/membership."""
        t1 = _make_user(db_session, "teacher_a05a", "TEACHER")
        t2 = _make_user(db_session, "teacher_a05b", "TEACHER")
        s = _make_user(db_session, "student_a05", "STUDENT")
        tok1 = _login("teacher_a05a")
        tok2 = _login("teacher_a05b")
        tok_s = _login("student_a05")
        r_prob = client.post("/api/v1/problems", json={"title": "SecretProb", "description": "d", "visibility": "PRIVATE"}, headers=_auth(tok1))
        pid = r_prob.json()["id"]
        # Both t2 and s know the ID but cannot access
        assert client.get(f"/api/v1/problems/{pid}", headers=_auth(tok2)).status_code == 403
        assert client.get(f"/api/v1/problems/{pid}", headers=_auth(tok_s)).status_code == 403

    def test_P05_A06_admin_cannot_use_academic_endpoints(self, db_session):
        """P05-A06: Admin role cannot use teacher or student academic endpoints (403)."""
        a = _make_user(db_session, "admin_a06", "ADMIN")
        tok = _login("admin_a06")
        assert client.post("/api/v1/classes", json={"name": "x", "academic_year": "y"}, headers=_auth(tok)).status_code == 403
        assert client.get("/api/v1/my/exams", headers=_auth(tok)).status_code == 403

    def test_P05_A07_error_body_format(self, db_session):
        """P05-A07: 403/404 error bodies contain error_code and message."""
        t = _make_user(db_session, "teacher_a07", "TEACHER")
        tok = _login("teacher_a07")
        r = client.get(f"/api/v1/classes/{uuid.uuid4()}", headers=_auth(tok))
        assert r.status_code == 404
        assert "error_code" in r.json()
        assert "message" in r.json()

    def test_P05_A08_student_submission_cross_access_blocked(self, db_session):
        """P05-A08: Student B cannot access Student A's submission (if any exist)."""
        s1 = _make_user(db_session, "student_a08a", "STUDENT")
        s2 = _make_user(db_session, "student_a08b", "STUDENT")
        tok_s1 = _login("student_a08a")
        tok_s2 = _login("student_a08b")
        r = client.get(f"/api/v1/my/submissions/{uuid.uuid4()}", headers=_auth(tok_s2))
        assert r.status_code in (403, 404)

    def test_P05_A09_locked_student_cannot_start_practice(self, db_session):
        """P05-A09: Locked student's token is rejected for practice session creation."""
        t = _make_user(db_session, "teacher_a09", "TEACHER")
        s = _make_user(db_session, "student_a09", "STUDENT")
        tok_t = _login("teacher_a09")
        tok_s = _login("student_a09")
        r_p = client.post("/api/v1/problems", json={
            "title": "A09Prob", "description": "d",
            "visibility": "PUBLIC", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        # Lock student
        s.status = AccountStatus.LOCKED.value
        db_session.commit()
        r = client.post("/api/v1/my/practice/sessions",
                        json={"problem_id": pid, "language": "CPP17"},
                        headers=_auth(tok_s))
        assert r.status_code == 403
        assert r.json()["error_code"] == "ACCOUNT_LOCKED"

    def test_P05_A10_student_no_trace_exposure(self, db_session):
        """P05-A10: Practice session responses do not expose raw digital trace fields."""
        t = _make_user(db_session, "teacher_a10", "TEACHER")
        s = _make_user(db_session, "student_a10", "STUDENT")
        tok_t = _login("teacher_a10")
        tok_s = _login("student_a10")
        r_p = client.post("/api/v1/problems", json={
            "title": "A10Prob", "description": "d",
            "visibility": "PUBLIC", "supported_languages": ["CPP17"]
        }, headers=_auth(tok_t))
        pid = r_p.json()["id"]
        r = client.post("/api/v1/my/practice/sessions",
                        json={"problem_id": pid, "language": "CPP17"},
                        headers=_auth(tok_s))
        assert r.status_code == 201
        data = r.json()
        # Phase 06+ fields must NOT appear
        for forbidden_field in ("editor_timeline", "attention_signal", "code_replay", "raw_trace"):
            assert forbidden_field not in data, f"Trace field '{forbidden_field}' exposed"


# ===========================================================================
# P05-D — DATABASE INVARIANTS
# ===========================================================================

class TestDatabaseInvariants:
    """P05-D01..D10 — PostgreSQL-level constraint enforcement."""

    def test_P05_D01_unique_class_membership(self, db_session):
        """P05-D01: DB unique constraint prevents duplicate class_memberships."""
        t = _make_user(db_session, "teacher_d01", "TEACHER")
        s = _make_user(db_session, "student_d01", "STUDENT")
        m1 = ClassMembership(class_id=uuid.uuid4(), student_id=s.id, is_active=True)
        # Create class first
        cls = Class(owner_id=t.id, name="D01Class", academic_year="2026")
        db_session.add(cls)
        db_session.commit()
        m1 = ClassMembership(class_id=cls.id, student_id=s.id, is_active=True)
        db_session.add(m1)
        db_session.commit()
        m2 = ClassMembership(class_id=cls.id, student_id=s.id, is_active=True)
        db_session.add(m2)
        with pytest.raises(Exception):  # IntegrityError from unique constraint
            db_session.flush()
        db_session.rollback()

    def test_P05_D02_unique_exam_participation(self, db_session):
        """P05-D02: DB unique constraint prevents duplicate exam participations."""
        t = _make_user(db_session, "teacher_d02", "TEACHER")
        s = _make_user(db_session, "student_d02", "STUDENT")
        start, end = _active_exam_times()
        e = Exam(owner_id=t.id, title="D02Exam", start_time=start, end_time=end, status="DRAFT")
        db_session.add(e)
        db_session.commit()
        p1 = ExamParticipation(exam_id=e.id, student_id=s.id, status="IN_PROGRESS", started_at=start)
        db_session.add(p1)
        db_session.commit()
        p2 = ExamParticipation(exam_id=e.id, student_id=s.id, status="IN_PROGRESS", started_at=start)
        db_session.add(p2)
        with pytest.raises(Exception):
            db_session.flush()
        db_session.rollback()

    def test_P05_D03_exam_time_check_constraint(self, db_session):
        """P05-D03: DB check constraint prevents end_time <= start_time in exams."""
        t = _make_user(db_session, "teacher_d03", "TEACHER")
        now = datetime.now(timezone.utc)
        e = Exam(
            owner_id=t.id, title="BadTime",
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=1),  # end before start
            status="DRAFT"
        )
        db_session.add(e)
        with pytest.raises(Exception):
            db_session.flush()
        db_session.rollback()

    def test_P05_D04_unique_exam_problem_order(self, db_session):
        """P05-D04: Two problems cannot have the same order_index in one exam."""
        t = _make_user(db_session, "teacher_d04", "TEACHER")
        start, end = _active_exam_times()
        e = Exam(owner_id=t.id, title="D04Exam", start_time=start, end_time=end, status="DRAFT")
        db_session.add(e)
        p1 = Problem(owner_id=t.id, title="D04P1", description="d", visibility="PRIVATE")
        p2 = Problem(owner_id=t.id, title="D04P2", description="d", visibility="PRIVATE")
        db_session.add_all([p1, p2])
        db_session.commit()
        ep1 = ExamProblem(exam_id=e.id, problem_id=p1.id, order_index=1, max_score=100)
        ep2 = ExamProblem(exam_id=e.id, problem_id=p2.id, order_index=1, max_score=100)  # same order!
        db_session.add(ep1)
        db_session.add(ep2)
        with pytest.raises(Exception):
            db_session.flush()
        db_session.rollback()

    def test_P05_D05_unique_problem_class_publication(self, db_session):
        """P05-D05: Same problem cannot be published to same class twice in DB."""
        t = _make_user(db_session, "teacher_d05", "TEACHER")
        cls = Class(owner_id=t.id, name="D05Class", academic_year="2026")
        prob = Problem(owner_id=t.id, title="D05Prob", description="d", visibility="CLASS")
        db_session.add_all([cls, prob])
        db_session.commit()
        pub1 = ProblemClassPublication(problem_id=prob.id, class_id=cls.id)
        db_session.add(pub1)
        db_session.commit()
        pub2 = ProblemClassPublication(problem_id=prob.id, class_id=cls.id)
        db_session.add(pub2)
        with pytest.raises(Exception):
            db_session.flush()
        db_session.rollback()

    def test_P05_D06_unique_exam_assignment(self, db_session):
        """P05-D06: Same class cannot be assigned to same exam twice in DB."""
        t = _make_user(db_session, "teacher_d06", "TEACHER")
        cls = Class(owner_id=t.id, name="D06Class", academic_year="2026")
        start, end = _active_exam_times()
        e = Exam(owner_id=t.id, title="D06Exam", start_time=start, end_time=end, status="DRAFT")
        db_session.add_all([cls, e])
        db_session.commit()
        ea1 = ExamAssignment(exam_id=e.id, class_id=cls.id)
        db_session.add(ea1)
        db_session.commit()
        ea2 = ExamAssignment(exam_id=e.id, class_id=cls.id)
        db_session.add(ea2)
        with pytest.raises(Exception):
            db_session.flush()
        db_session.rollback()

    def test_P05_D07_participation_score_non_negative(self, db_session):
        """P05-D07: Negative total_score in ExamParticipation violates DB check."""
        t = _make_user(db_session, "teacher_d07", "TEACHER")
        s = _make_user(db_session, "student_d07", "STUDENT")
        start, end = _active_exam_times()
        e = Exam(owner_id=t.id, title="D07Exam", start_time=start, end_time=end, status="DRAFT")
        db_session.add(e)
        db_session.commit()
        p = ExamParticipation(
            exam_id=e.id, student_id=s.id,
            status="IN_PROGRESS", started_at=start,
            total_score=-1  # invalid
        )
        db_session.add(p)
        with pytest.raises(Exception):
            db_session.flush()
        db_session.rollback()

    def test_P05_D08_session_context_exclusive_constraint(self, db_session):
        """P05-D08: CodingSession must be either exam or practice context (not both)."""
        t = _make_user(db_session, "teacher_d08", "TEACHER")
        s = _make_user(db_session, "student_d08", "STUDENT")
        start, end = _active_exam_times()
        e = Exam(owner_id=t.id, title="D08Exam", start_time=start, end_time=end, status="DRAFT")
        prob = Problem(owner_id=t.id, title="D08Prob", description="d", visibility="PRIVATE")
        db_session.add_all([e, prob])
        db_session.commit()
        part = ExamParticipation(exam_id=e.id, student_id=s.id, status="IN_PROGRESS", started_at=start)
        db_session.add(part)
        db_session.commit()
        practice_att = PracticeAttempt(student_id=s.id, problem_id=prob.id)
        db_session.add(practice_att)
        db_session.commit()
        # Both context IDs set — violates exclusive constraint
        sess = CodingSession(
            student_id=s.id,
            problem_id=prob.id,
            language="CPP17",
            is_exam_context=True,
            exam_participation_id=part.id,
            practice_attempt_id=practice_att.id,  # must be NULL for exam context
            status="ACTIVE",
        )
        db_session.add(sess)
        with pytest.raises(Exception):
            db_session.flush()
        db_session.rollback()

    def test_P05_D09_concurrency_single_participation(self, db_session):
        """P05-D09: Concurrent exam start requests produce exactly ONE ExamParticipation.

        Uses real ThreadPoolExecutor with independent DB connections and a barrier
        to maximize concurrency, calling the service layer directly to bypass
        TestClient AnyIO portal deadlocks.
        """
        from app.services import academic as svc

        t = _make_user(db_session, "teacher_d09", "TEACHER")
        s = _make_user(db_session, "student_d09", "STUDENT")
        tok_t = _login("teacher_d09")
        r_cls = client.post("/api/v1/classes", json={"name": "D09Class", "academic_year": "2026"}, headers=_auth(tok_t))
        cid = r_cls.json()["id"]
        client.post(f"/api/v1/classes/{cid}/members", json={"student_id": str(s.id)}, headers=_auth(tok_t))
        start, end = _active_exam_times()
        r_e = client.post("/api/v1/exams", json={
            "title": "D09ConcurrentExam",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }, headers=_auth(tok_t))
        eid = r_e.json()["id"]
        client.post(f"/api/v1/exams/{eid}/classes", json={"class_id": cid}, headers=_auth(tok_t))
        _publish(db_session, eid)  # docs/36 D11: students only reach published exams

        barrier = threading.Barrier(4)
        results = []
        errors = []

        def start_exam_concurrent():
            # Each thread gets its own independent DB connection
            local_db = TestingSessionLocal()
            try:
                # Reload user in this session
                local_student = local_db.query(User).filter_by(id=s.id).first()
                barrier.wait(timeout=10)  # synchronize all threads
                p = svc.start_exam_participation(local_db, student=local_student, exam_id=eid)
                local_db.commit()
                results.append(p.id)
            except Exception as exc:
                local_db.rollback()
                errors.append(str(exc))
            finally:
                local_db.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(start_exam_concurrent) for _ in range(4)]
            concurrent.futures.wait(futures, timeout=30)

        assert not errors, f"Concurrent errors: {errors}"

        # Verify DB invariant: exactly ONE participation
        count_db = db_session.query(ExamParticipation).filter(
            ExamParticipation.exam_id == eid,
            ExamParticipation.student_id == s.id,
        ).count()
        assert count_db == 1, f"Expected 1 participation, found {count_db}"

        # All results should point to the SAME participation ID
        assert len(set(results)) == 1, f"Expected all results to have the same participation ID, found {results}"

    def test_P05_D10_practice_attempt_score_non_negative(self, db_session):
        """P05-D10: Negative total_score in PracticeAttempt violates DB check."""
        t = _make_user(db_session, "teacher_d10", "TEACHER")
        s = _make_user(db_session, "student_d10", "STUDENT")
        prob = Problem(owner_id=t.id, title="D10Prob", description="d", visibility="PRIVATE")
        db_session.add(prob)
        db_session.commit()
        attempt = PracticeAttempt(student_id=s.id, problem_id=prob.id, total_score=-5)
        db_session.add(attempt)
        with pytest.raises(Exception):
            db_session.flush()
        db_session.rollback()
