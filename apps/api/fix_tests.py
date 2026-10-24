import os
import re

fixture_code = """
import os
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.user import User, RoleEnum
from app.models.problem import Problem, SupportedLanguage
from app.models.session import CodingSession, SessionStatus

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL must be set")
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture(scope="function")
def student_user(db):
    student = User(email=f"stu_{uuid.uuid4()}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"stu_{uuid.uuid4()}", full_name="Student")
    db.add(student)
    db.commit()
    return student

@pytest.fixture(scope="function")
def problem(db, student_user):
    prob = Problem(title="Test", description="Test", owner_id=student_user.id)
    db.add(prob)
    db.commit()
    return prob

@pytest.fixture(scope="function")
def active_session(db, student_user, problem):
    from datetime import datetime, timezone, timedelta
    from app.models.session import PracticeAttempt
    attempt = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    db.add(attempt)
    db.commit()
    
    sess = CodingSession(
        student_id=student_user.id, 
        problem_id=problem.id, 
        language=SupportedLanguage.PYTHON3, 
        opened_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status=SessionStatus.ACTIVE,
        practice_attempt_id=attempt.id
    )
    db.add(sess)
    db.commit()
    return sess
"""

files = [
    "d:/SPNC/apps/api/tests/judge/test_scheduler_cycle.py",
    "d:/SPNC/apps/api/tests/judge/test_scheduler_idle.py",
    "d:/SPNC/apps/api/tests/judge/test_scheduler_fast.py",
    "d:/SPNC/apps/api/tests/judge/test_scheduler_rf.py",
    "d:/SPNC/apps/api/tests/judge/test_scheduler_loc.py",
    "d:/SPNC/apps/api/tests/judge/test_scheduler_concurrency.py"
]

for f in files:
    with open(f, "r") as file:
        content = file.read()
    
    # insert after pytestmark
    content = content.replace('pytestmark = pytest.mark.asyncio(loop_scope="function")', 'pytestmark = pytest.mark.asyncio(loop_scope="function")\n' + fixture_code)
    
    with open(f, "w") as file:
        file.write(content)

print("Tests fixed")
