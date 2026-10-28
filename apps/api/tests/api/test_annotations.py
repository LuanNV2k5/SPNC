"""Phase 09B — Signal status transitions & TeacherAnnotation CRUD (docs/35 AC-09-09, AC-09-10).

Database:
    spnc_phase09_observation_test  (PostgreSQL only; guarded)
"""
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

PHASE09_DB_URL = os.environ.get(
    "PHASE09_DATABASE_URL",
    "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase09_observation_test",
)
os.environ["DATABASE_URL"] = PHASE09_DB_URL

from app.main import app
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models.user import User, AccountStatus, AuditLog
from app.models.observation import AttentionSignal, TeacherAnnotation
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
    """T1 owns C1 with students S and S2. T2 owns C2 (no members). P1 owned by T1; S and S2 each have a practice session."""
    t1, t2 = _make_user(db, "t1", "TEACHER"), _make_user(db, "t2", "TEACHER")
    s, s2 = _make_user(db, "stu", "STUDENT"), _make_user(db, "stu2", "STUDENT")
    outsider = _make_user(db, "outsider", "STUDENT")
    h1, h2, hs, hs2 = _auth("t1"), _auth("t2"), _auth("stu"), _auth("stu2")
    c1 = client.post("/api/v1/classes", json={"name": "C1", "academic_year": "2026"}, headers=h1).json()["id"]
    c2 = client.post("/api/v1/classes", json={"name": "C2", "academic_year": "2026"}, headers=h2).json()["id"]
    for sid in (s.id, s2.id):
        client.post(f"/api/v1/classes/{c1}/members", json={"student_id": str(sid)}, headers=h1)
    p1 = client.post("/api/v1/problems", json={"title": "P1", "description": "d", "visibility": "PUBLIC",
                                               "supported_languages": ["PYTHON3"]}, headers=h1).json()["id"]
    sess = client.post("/api/v1/my/practice/sessions", json={"problem_id": p1, "language": "PYTHON3"}, headers=hs).json()["id"]
    sess2 = client.post("/api/v1/my/practice/sessions", json={"problem_id": p1, "language": "PYTHON3"}, headers=hs2).json()["id"]
    sig = AttentionSignal(student_id=s.id, session_id=uuid.UUID(sess), signal_type="IDLE_DETECTED", status="NEW",
                          rule_version="1.1.0", evidence={"duration_seconds": 400.0, "threshold_used": 300},
                          dedup_key=f"TEST:{uuid.uuid4()}")
    sig2 = AttentionSignal(student_id=s2.id, session_id=uuid.UUID(sess2), signal_type="FAST_FIRST_CODE", status="NEW",
                           rule_version="1.1.0", evidence={"delta_seconds": 5.0}, dedup_key=f"TEST:{uuid.uuid4()}")
    db.add_all([sig, sig2])
    db.commit()
    return {"t1": t1, "t2": t2, "s": s, "s2": s2, "outsider": outsider, "h1": h1, "h2": h2,
            "c1": c1, "c2": c2, "sess": sess, "sess2": sess2, "sig": sig, "sig2": sig2}


def _signal_url(w, signal_id=None, student=None):
    return f"/api/v1/classes/{w['c1']}/students/{(student or w['s']).id}/signals/{signal_id or w['sig'].id}"


# ---------------------------------------------------------------------------
# AC-09-09 — signal status transitions
# ---------------------------------------------------------------------------
def test_acknowledge_then_reopen_with_audit(db, world):
    w = world
    r = client.patch(_signal_url(w), json={"status": "ACKNOWLEDGED"}, headers=w["h1"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ACKNOWLEDGED"
    assert r.json()["evidence"] == {"duration_seconds": 400.0, "threshold_used": 300}

    r = client.patch(_signal_url(w), json={"status": "NEW"}, headers=w["h1"])
    assert r.status_code == 200 and r.json()["status"] == "NEW"

    logs = db.scalars(select(AuditLog).where(AuditLog.action == "SIGNAL_STATUS_CHANGED").order_by(AuditLog.timestamp)).all()
    assert [(l.metadata_payload["old_status"], l.metadata_payload["new_status"]) for l in logs] == [("NEW", "ACKNOWLEDGED"), ("ACKNOWLEDGED", "NEW")]
    assert all(l.actor_id == w["t1"].id and l.target_id == str(w["sig"].id) for l in logs)


def test_dismiss_removes_student_from_attention(world):
    w = world
    assert client.get(f"/api/v1/classes/{w['c1']}/attention", headers=w["h1"]).json()["total"] == 2
    assert client.patch(_signal_url(w), json={"status": "DISMISSED"}, headers=w["h1"]).status_code == 200
    body = client.get(f"/api/v1/classes/{w['c1']}/attention", headers=w["h1"]).json()
    assert body["total"] == 1
    assert body["items"][0]["student_id"] == str(w["s2"].id)


@pytest.mark.parametrize("first,second", [("ACKNOWLEDGED", "DISMISSED"), ("DISMISSED", "ACKNOWLEDGED"), ("ACKNOWLEDGED", "ACKNOWLEDGED")])
def test_invalid_transitions_rejected(db, world, first, second):
    w = world
    assert client.patch(_signal_url(w), json={"status": first}, headers=w["h1"]).status_code == 200
    r = client.patch(_signal_url(w), json={"status": second}, headers=w["h1"])
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_SIGNAL_TRANSITION"


def test_unknown_status_value_rejected(world):
    r = client.patch(_signal_url(world), json={"status": "VIEWED"}, headers=world["h1"])
    assert r.status_code == 422


def test_evidence_cannot_be_changed_through_patch(db, world):
    w = world
    r = client.patch(_signal_url(w), json={"status": "ACKNOWLEDGED", "evidence": {"hacked": True}}, headers=w["h1"])
    assert r.status_code == 422
    db.refresh(w["sig"])
    assert w["sig"].evidence == {"duration_seconds": 400.0, "threshold_used": 300}
    assert w["sig"].status == "NEW"


def test_signal_patch_authorization(world):
    w = world
    assert client.patch(_signal_url(w), json={"status": "ACKNOWLEDGED"}, headers=w["h2"]).status_code == 403
    # signal of S2 addressed under S's path -> not found
    r = client.patch(_signal_url(w, signal_id=w["sig2"].id), json={"status": "ACKNOWLEDGED"}, headers=w["h1"])
    assert r.status_code == 404
    assert r.json()["error_code"] == "SIGNAL_NOT_FOUND"


# ---------------------------------------------------------------------------
# AC-09-10 — annotation CRUD
# ---------------------------------------------------------------------------
def _create(w, h=None, **body):
    payload = {"student_id": str(w["s"].id), "content": "Spent a long time reading the statement."}
    payload.update(body)
    return client.post("/api/v1/annotations", json=payload, headers=h or w["h1"])


def test_create_and_list_own_annotations_with_filters(world):
    w = world
    r1 = _create(w)
    assert r1.status_code == 201, r1.text
    a1 = r1.json()
    assert a1["teacher_id"] == str(w["t1"].id) and a1["session_id"] is None and a1["signal_id"] is None
    r2 = _create(w, session_id=w["sess"], signal_id=str(w["sig"].id), content="Follow up on idle period.")
    assert r2.status_code == 201
    _create(w, student_id=str(w["s2"].id), content="Other student note.")

    all_items = client.get("/api/v1/annotations", headers=w["h1"]).json()
    assert all_items["total"] == 3
    assert client.get(f"/api/v1/annotations?student_id={w['s'].id}", headers=w["h1"]).json()["total"] == 2
    assert client.get(f"/api/v1/annotations?session_id={w['sess']}", headers=w["h1"]).json()["total"] == 1
    by_signal = client.get(f"/api/v1/annotations?signal_id={w['sig'].id}", headers=w["h1"]).json()
    assert [i["id"] for i in by_signal["items"]] == [r2.json()["id"]]
    future = datetime(2100, 1, 1, tzinfo=timezone.utc).isoformat()
    assert client.get("/api/v1/annotations", params={"created_from": future}, headers=w["h1"]).json()["total"] == 0


def test_other_teacher_cannot_see_update_or_delete(world):
    w = world
    a = _create(w).json()
    assert client.get("/api/v1/annotations", headers=w["h2"]).json()["total"] == 0
    r = client.patch(f"/api/v1/annotations/{a['id']}", json={"content": "x"}, headers=w["h2"])
    assert r.status_code == 403 and r.json()["error_code"] == "ANNOTATION_FORBIDDEN"
    assert client.delete(f"/api/v1/annotations/{a['id']}", headers=w["h2"]).status_code == 403


def test_update_sets_updated_at_and_content(world):
    w = world
    a = _create(w).json()
    r = client.patch(f"/api/v1/annotations/{a['id']}", json={"content": "Revised note."}, headers=w["h1"])
    assert r.status_code == 200
    assert r.json()["content"] == "Revised note."
    assert r.json()["updated_at"] >= a["updated_at"]


def test_soft_delete_hides_annotation(db, world):
    w = world
    a = _create(w).json()
    assert client.delete(f"/api/v1/annotations/{a['id']}", headers=w["h1"]).status_code == 204
    assert client.get("/api/v1/annotations", headers=w["h1"]).json()["total"] == 0
    assert client.patch(f"/api/v1/annotations/{a['id']}", json={"content": "x"}, headers=w["h1"]).status_code == 404
    assert client.delete(f"/api/v1/annotations/{a['id']}", headers=w["h1"]).status_code == 404
    row = db.get(TeacherAnnotation, uuid.UUID(a["id"]))
    assert row is not None and row.deleted_at is not None                      # D7: soft delete


def test_cannot_annotate_student_outside_own_classes(world):
    w = world
    r = _create(w, student_id=str(w["outsider"].id))
    assert r.status_code == 403
    r = _create(w, h=w["h2"])                                                   # S is not in T2's classes
    assert r.status_code == 403


def test_context_must_belong_to_student(world):
    w = world
    r = _create(w, session_id=w["sess2"])                                       # S2's session
    assert r.status_code == 422 and r.json()["error_code"] == "ANNOTATION_CONTEXT_MISMATCH"
    r = _create(w, signal_id=str(w["sig2"].id))                                 # S2's signal
    assert r.status_code == 422 and r.json()["error_code"] == "ANNOTATION_CONTEXT_MISMATCH"
    r = _create(w, student_id=str(w["s2"].id), session_id=w["sess2"], signal_id=str(w["sig"].id))
    assert r.status_code == 422


@pytest.mark.parametrize("content", ["", "   ", "x" * 5001])
def test_content_limits(world, content):
    assert _create(world, content=content).status_code == 422                   # D8


def test_student_role_cannot_use_annotations(world):
    w = world
    hs = _auth("stu")
    assert client.get("/api/v1/annotations", headers=hs).status_code == 403
    assert _create(w, h=hs).status_code == 403
