"""Phase 14B — Production judge isolation pieces (OQ-26 resolved by docs/40 Q4).

1. JUDGE_CONTAINER_RUNTIME reaches container creation (gVisor "runsc" on judge hosts); default unchanged.
2. deploy/sql/judge_worker_role.sql is sufficient for every worker path and denies everything else:
   the judge runs in-process as the spnc_judge role.

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test; the test user is a superuser).
"""
import pathlib
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker

from app import worker
from app.core.config import settings
from app.models.exam import ExamParticipation
from app.models.observation import PointTransaction
from app.models.run_submit import Run, Submission
from app.repositories.run import run_repository
from app.services import submission as submission_svc
from app.services.judge import sandbox as sandbox_mod
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    PHASE10_DB_URL, FakeAdapter, TestingSessionLocal, _exam_session, _practice_session, _snapshot, _submit,
    client, clean_db, db, engine, enqueued, setup_database, world,
)

ROLE_SQL = pathlib.Path(__file__).resolve().parents[4] / "deploy" / "sql" / "judge_worker_role.sql"
JUDGE_PASSWORD = "judge-role-test-password"


# ---------------------------------------------------------------------------
# 1. Container runtime setting
# ---------------------------------------------------------------------------
class _FakeContainer:
    def start(self): pass
    def wait(self, timeout=None): return {"StatusCode": 0}
    def logs(self, stdout=True, stderr=True, stream=False): return b""
    def kill(self): pass
    def remove(self, force=True): pass


def _capture_create(monkeypatch, runtime):
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return _FakeContainer()

    box = sandbox_mod.Sandbox.__new__(sandbox_mod.Sandbox)
    box.client = SimpleNamespace(containers=SimpleNamespace(create=create))
    monkeypatch.setattr(settings, "JUDGE_CONTAINER_RUNTIME", runtime)
    box.execute(image="python:3.10-slim", command="true", workdir="/workspace", mounts={})
    return captured


def test_runtime_passed_to_container_creation(monkeypatch):
    created = _capture_create(monkeypatch, "runsc")
    assert created["runtime"] == "runsc"
    # Existing limits are untouched
    assert created["network_disabled"] is True and created["user"] == "1000:1000"


def test_default_runtime_is_left_to_the_daemon(monkeypatch):
    assert "runtime" not in _capture_create(monkeypatch, "")


# ---------------------------------------------------------------------------
# 2. Least-privilege role
# ---------------------------------------------------------------------------
@pytest.fixture
def judge_session():
    with engine.connect() as conn:
        conn.execute(text(ROLE_SQL.read_text(encoding="utf-8")))
        conn.execute(text(f"ALTER ROLE spnc_judge PASSWORD '{JUDGE_PASSWORD}'"))
        conn.commit()
    url = PHASE10_DB_URL.replace("spnc_test:spnc_test_password@", f"spnc_judge:{JUDGE_PASSWORD}@")
    judge_engine = create_engine(url)
    Session = sessionmaker(bind=judge_engine, autoflush=False)
    yield Session
    judge_engine.dispose()


def test_role_runs_every_worker_path(db, world, judge_session, monkeypatch):
    w = world
    # Practice submission -> result + points
    sid = _practice_session(w)
    practice_sub = uuid.UUID(_submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n")).json()["id"])
    with judge_session() as s:
        assert submission_svc.judge_submission(s, practice_sub, adapters={"PYTHON3": FakeAdapter()}) is True

    # Exam submission -> result + exam total (D5)
    eid, part_id, esid = _exam_session(w)
    exam_sub = uuid.UUID(_submit(w["h_s"], esid, _snapshot(w["h_s"], esid, "SUM\n")).json()["id"])
    with judge_session() as s:
        assert submission_svc.judge_submission(s, exam_sub, adapters={"PYTHON3": FakeAdapter()}) is True

    # Run job
    rsid = _practice_session(w, w["h_s2"])
    snap = _snapshot(w["h_s2"], rsid, "print(1)\n")
    with TestingSessionLocal() as s:
        run_id = run_repository.create(s, session_id=uuid.UUID(rsid), snapshot_id=uuid.UUID(snap), input_data="").id
    monkeypatch.setitem(worker.ADAPTERS, "PYTHON3", type("A", (), {"execute": lambda self, code, inp, **k: {
        "verdict": "ACCEPTED", "stdout": "1\n", "stderr": "", "time_ms": 5, "memory_kb": 0,
        "compile_error_message": None, "runtime_error_message": None}})())
    with judge_session() as s:
        worker.process_run(s, run_id)

    db.expire_all()
    assert db.get(Submission, practice_sub).verdict == "ACCEPTED"
    assert db.get(Submission, exam_sub).status == "COMPLETED"
    assert db.get(ExamParticipation, uuid.UUID(part_id)).total_score == 50
    assert db.get(Run, run_id).status == "COMPLETED"
    assert len(db.query(PointTransaction).all()) == 1


@pytest.mark.parametrize("statement", [
    "SELECT * FROM users",
    "SELECT * FROM trace_events",
    "SELECT final_loc FROM coding_sessions",          # only id/student_id are readable
    "UPDATE problems SET title = 'x'",
    "DELETE FROM submissions",
    "UPDATE submissions SET student_id = student_id",
    "INSERT INTO audit_logs (id, action, timestamp) VALUES (gen_random_uuid(), 'X', now())",
    "CREATE TABLE judge_owned (id int)",
])
def test_role_denies_everything_else(judge_session, statement):
    with judge_session() as s:
        with pytest.raises(ProgrammingError) as err:
            s.execute(text(statement))
        assert "permission denied" in str(err.value).lower()
