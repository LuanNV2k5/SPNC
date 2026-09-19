import pytest
import os
from urllib.parse import urlparse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

TEST_DB_URL = "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase04_admin_test"
os.environ["DATABASE_URL"] = TEST_DB_URL

from app.main import app
from app.db.session import get_db
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User, RoleEnum, AccountStatus

def assert_safe_phase04_test_database(db_url: str):
    if not db_url:
        raise ValueError("No database URL provided")
    try:
        parsed = urlparse(db_url)
        db_name = parsed.path.lstrip('/')
    except Exception as e:
        raise ValueError(f"Failed to parse database URL: {e}")
    if db_name != "spnc_phase04_admin_test":
        raise ValueError(f"UNSAFE DATABASE: {db_name}")

TEST_DB_URL = "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase04_admin_test"
engine = create_engine(TEST_DB_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

from alembic.config import Config
from alembic import command

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    os.environ["DATABASE_URL"] = TEST_DB_URL
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

@pytest.fixture(autouse=True)
def clean_db():
    db_url = os.environ.get("DATABASE_URL", TEST_DB_URL)
    assert_safe_phase04_test_database(db_url)
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

def _create_user(db, username, role, status=AccountStatus.ACTIVE.value):
    user = User(
        username=username,
        email=f"{username}@spnc.io",
        password_hash=get_password_hash("secure_password_123"),
        full_name=f"{username} User",
        role=role,
        status=status,
        force_password_change=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@pytest.fixture
def admin_user(db_session):
    return _create_user(db_session, "admin1", RoleEnum.ADMIN.value)

@pytest.fixture
def teacher_user(db_session):
    return _create_user(db_session, "teacher1", RoleEnum.TEACHER.value)

@pytest.fixture
def student_user(db_session):
    return _create_user(db_session, "student1", RoleEnum.STUDENT.value)

def _get_token(username):
    response = client.post("/api/v1/auth/login", data={"username": username, "password": "secure_password_123"})
    return response.json()["access_token"]

def test_admin_access_success(admin_user):
    token = _get_token("admin1")
    response = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

def test_teacher_access_forbidden(teacher_user):
    token = _get_token("teacher1")
    response = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert "error_code" in response.json()
    assert "message" in response.json()

def test_student_access_forbidden(student_user):
    token = _get_token("student1")
    response = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert "error_code" in response.json()
    assert "message" in response.json()

def test_anonymous_access_unauthorized():
    response = client.get("/api/v1/admin/users")
    print(response.status_code, response.json()); assert response.status_code == 401
    assert "error_code" in response.json()
    assert "message" in response.json()
def test_single_admin_role_change(admin_user):
    token = _get_token('admin1')
    response = client.patch(f'/api/v1/admin/users/{admin_user.id}', json={'role': RoleEnum.TEACHER.value}, headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 400
    assert response.json()['error_code'] == 'LAST_ADMIN_PROTECTED'
def test_single_admin_status_change(admin_user):
    token = _get_token('admin1')
    response = client.patch(f'/api/v1/admin/users/{admin_user.id}', json={'status': AccountStatus.LOCKED.value}, headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 400
    assert response.json()['error_code'] == 'LAST_ADMIN_PROTECTED'
def test_two_admin_success(admin_user, db_session):
    admin2 = _create_user(db_session, 'admin2', RoleEnum.ADMIN.value)
    token = _get_token('admin1')
    response = client.patch(f'/api/v1/admin/users/{admin2.id}', json={'role': RoleEnum.TEACHER.value}, headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
def test_unrelated_update(admin_user):
    token = _get_token('admin1')
    response = client.patch(f'/api/v1/admin/users/{admin_user.id}', json={'role': RoleEnum.ADMIN.value}, headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200

import threading
from sqlalchemy import text
from app.services.admin import update_user
from fastapi import HTTPException

def test_concurrent_admin_demotion_preserves_one_usable_admin(admin_user, db_session):
    admin2 = _create_user(db_session, "admin_b", RoleEnum.ADMIN.value)

    # Assert initial state
    count = db_session.query(User).filter(User.role == RoleEnum.ADMIN.value, User.status == AccountStatus.ACTIVE.value).count()
    assert count == 2

    barrier = threading.Barrier(2)
    results = []

    def worker(target_id, actor_id):
        # Create an independent session
        session = TestingSessionLocal()
        try:
            barrier.wait(timeout=5.0)
            update_user(session, actor_id, target_id, role=RoleEnum.TEACHER.value)
            results.append("SUCCESS")
        except HTTPException as e:
            if e.status_code == 400 and e.detail["error_code"] == "LAST_ADMIN_PROTECTED":
                results.append("PROTECTED")
            else:
                results.append(f"HTTP_ERROR_{e.status_code}")
        except Exception as e:
            results.append(f"ERROR_{type(e).__name__}")
        finally:
            session.close()

    t1 = threading.Thread(target=worker, args=(admin_user.id, admin_user.id))
    t2 = threading.Thread(target=worker, args=(admin2.id, admin_user.id))

    t1.start()
    t2.start()

    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    assert not t1.is_alive()
    assert not t2.is_alive()

    # Check outcomes
    success_count = results.count("SUCCESS")
    protected_count = results.count("PROTECTED")

    assert success_count == 1
    assert protected_count == 1

    # Third fresh session check
    final_session = TestingSessionLocal()
    try:
        final_count = final_session.query(User).filter(User.role == RoleEnum.ADMIN.value, User.status == AccountStatus.ACTIVE.value).count()
        assert final_count == 1

        a_final = final_session.query(User).filter(User.id == admin_user.id).first()
        b_final = final_session.query(User).filter(User.id == admin2.id).first()

        roles = [a_final.role, b_final.role]
        assert roles.count(RoleEnum.ADMIN.value) == 1
        assert roles.count(RoleEnum.TEACHER.value) == 1
    finally:
        final_session.close()


# User Admin Tests
def test_list_users(admin_user):
    token = _get_token("admin1")
    response = client.get("/api/v1/admin/users?page=1&size=10", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data
    assert data["page"] == 1
    assert data["size"] == 10
    assert len(data["items"]) >= 1
    # Check no password hash
    assert "password_hash" not in data["items"][0]

def test_get_user(admin_user):
    token = _get_token("admin1")
    response = client.get(f"/api/v1/admin/users/{admin_user.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "admin1"
    assert "password_hash" not in data

def test_get_user_not_found(admin_user):
    token = _get_token("admin1")
    import uuid
    response = client.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404
    assert response.json()["error_code"] == "USER_NOT_FOUND"

def test_create_user(admin_user):
    token = _get_token("admin1")
    req = {
        "username": "new_student",
        "email": "new_student@test.com",
        "password": "secure123",
        "full_name": "New Student",
        "role": "STUDENT"
    }
    response = client.post("/api/v1/admin/users", json=req, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "new_student"
    assert data["role"] == "STUDENT"

def test_create_user_invalid_role(admin_user):
    token = _get_token("admin1")
    req = {
        "username": "bad_role",
        "email": "bad@test.com",
        "password": "secure123",
        "full_name": "Bad",
        "role": "SUPERADMIN"
    }
    response = client.post("/api/v1/admin/users", json=req, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_ROLE"

def test_update_user_role(admin_user, student_user):
    token = _get_token("admin1")
    response = client.patch(f"/api/v1/admin/users/{student_user.id}", json={"role": "TEACHER"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["role"] == "TEACHER"

def test_update_user_not_found(admin_user):
    token = _get_token("admin1")
    import uuid
    response = client.patch(f"/api/v1/admin/users/{uuid.uuid4()}", json={"role": "TEACHER"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404
    assert response.json()["error_code"] == "USER_NOT_FOUND"

# Class Admin Tests
def test_list_classes(admin_user, db_session):
    from app.models.class_org import Class
    c = Class(name="Math 101", owner_id=admin_user.id, academic_year='2026', is_active=True)
    db_session.add(c)
    db_session.commit()

    token = _get_token("admin1")
    response = client.get("/api/v1/admin/classes", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1

def test_get_class(admin_user, db_session):
    from app.models.class_org import Class
    c = Class(name="Math 102", owner_id=admin_user.id, academic_year='2026', is_active=True)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    token = _get_token("admin1")
    response = client.get(f"/api/v1/admin/classes/{c.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["name"] == "Math 102"

# Exam Admin Tests
def test_list_exams(admin_user, db_session):
    from app.models.exam import Exam
    from datetime import datetime, timezone, timedelta
    e = Exam(title="Final", owner_id=admin_user.id, start_time=datetime.now(timezone.utc), end_time=datetime.now(timezone.utc) + timedelta(hours=1))
    db_session.add(e)
    db_session.commit()

    token = _get_token("admin1")
    response = client.get("/api/v1/admin/exams", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["total"] >= 1

def test_cancel_exam(admin_user, db_session):
    from app.models.exam import Exam, ExamStatus
    from datetime import datetime, timezone, timedelta
    e = Exam(title="Final 2", owner_id=admin_user.id, start_time=datetime.now(timezone.utc), end_time=datetime.now(timezone.utc) + timedelta(hours=1), status=ExamStatus.DRAFT)
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)

    token = _get_token("admin1")
    response = client.patch(f"/api/v1/admin/exams/{e.id}/cancel", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    db_session.refresh(e)
    assert e.status == ExamStatus.CANCELLED

def test_cancel_completed_exam(admin_user, db_session):
    from app.models.exam import Exam, ExamStatus
    from datetime import datetime, timezone, timedelta
    e = Exam(title="Final 3", owner_id=admin_user.id, start_time=datetime.now(timezone.utc), end_time=datetime.now(timezone.utc) + timedelta(hours=1), status=ExamStatus.COMPLETED)
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)

    token = _get_token("admin1")
    response = client.patch(f"/api/v1/admin/exams/{e.id}/cancel", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_STATE"

# Settings Tests
def test_get_settings(admin_user):
    token = _get_token("admin1")
    response = client.get("/api/v1/admin/settings", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "retention_days" in response.json()

def test_update_settings(admin_user):
    token = _get_token("admin1")
    response = client.patch("/api/v1/admin/settings", json={"retention_days": 45}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    response2 = client.get("/api/v1/admin/settings", headers={"Authorization": f"Bearer {token}"})
    assert response2.json()["retention_days"] == 45

def test_update_settings_invalid(admin_user):
    token = _get_token("admin1")
    response = client.patch("/api/v1/admin/settings", json={"retention_days": -5}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_SETTING"

# Audit Logs Tests
def test_audit_logs(admin_user):
    token = _get_token("admin1")
    client.patch("/api/v1/admin/settings", json={"retention_days": 10}, headers={"Authorization": f"Bearer {token}"})

    response = client.get("/api/v1/admin/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    found = False
    for log in data["items"]:
        if log["action"] == "SYSTEM_SETTING_CHANGED":
            found = True
            break
    assert found

# Dashboard Tests
def test_dashboard_summary(admin_user, student_user):
    token = _get_token("admin1")
    response = client.get("/api/v1/admin/dashboard/summary", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["total_users"] >= 2
    assert data["users_by_role"]["ADMIN"] >= 1
    assert data["users_by_role"]["STUDENT"] >= 1

# Stale Token Test (Security)
def test_stale_token_rejected(admin_user, db_session):
    user = _create_user(db_session, "stale_user", RoleEnum.ADMIN.value)
    token = _get_token("stale_user")

    user.status = AccountStatus.LOCKED.value
    db_session.commit()

    response = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    data = response.json()
    assert data["error_code"] == "ACCOUNT_LOCKED"
    assert "message" in data
    assert "request_id" in data
