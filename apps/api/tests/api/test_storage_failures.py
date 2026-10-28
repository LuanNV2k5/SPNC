"""Phase 11 — Behaviour when snapshot storage fails (docs/37 §3.1, §4; AC-11-02, AC-11-04).

Storage outages are simulated on the shared adapter; no MinIO needed. Reuses the Phase 10
fixtures (guarded database spnc_phase10_submission_test).
"""
import uuid

import pytest
from sqlalchemy import select

from app import cli
from app.models.run_submit import Run, Submission
from app.models.session import CodingSession
from app.models.trace import CodeSnapshot
from app.models.user import AuditLog, User
from app.repositories.run import run_repository
from app.services import bootstrap
from app.services.storage import StorageUnavailable, storage_adapter
from app import worker
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    FakeAdapter, TestingSessionLocal, _judge, _practice_session, _snapshot, _submit, client,
    clean_db, db, enqueued, setup_database, world,
)


@pytest.fixture
def outage(monkeypatch):
    """Every storage call raises, as when MinIO is unreachable."""
    def down(*args, **kwargs):
        raise StorageUnavailable("connection refused")
    def arm():
        for name in ("upload_code_snapshot", "download_code_snapshot", "exists_code_snapshot"):
            monkeypatch.setattr(storage_adapter, name, down)
    return arm


def test_snapshot_upload_outage_returns_503_without_metadata(db, world, outage):
    w = world
    sid = _practice_session(w)
    outage()
    r = client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots", json={
        "reason": "RUN", "language": "PYTHON3", "source_code": "print(1)\n", "line_count": 1}, headers=w["h_s"])
    assert r.status_code == 503
    body = r.json()
    assert body["error_code"] == "STORAGE_UNAVAILABLE" and body["request_id"]
    assert db.scalars(select(CodeSnapshot)).all() == []          # upload-first: no dangling metadata


def test_session_end_during_outage_records_null_loc(db, world, outage):
    w = world
    sid = _practice_session(w)
    snap = _snapshot(w["h_s"], sid, "a = 1\n")
    outage()
    r = client.post(f"/api/v1/my/practice/sessions/{sid}/end", json={}, headers=w["h_s"])
    assert r.status_code == 200
    assert r.json()["final_loc"] is None and r.json()["final_code_snapshot_id"] == snap   # never a fabricated LOC


def test_judge_during_outage_is_failed_internal(db, world, outage):
    w = world
    sid = _practice_session(w)
    sub_id = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n")).json()["id"]
    outage()
    adapter = FakeAdapter()
    assert _judge(sub_id, adapter) is True
    assert adapter.calls == []                                     # never ran empty code
    sub = db.get(Submission, uuid.UUID(sub_id))
    assert sub.status == "FAILED_INTERNAL" and sub.judge_result == {"internal_error": "Snapshot content unavailable"}


def test_run_worker_during_outage_is_failed_internal(db, world, outage, monkeypatch):
    w = world
    sid = _practice_session(w)
    snap = _snapshot(w["h_s"], sid, "print(1)\n")
    with TestingSessionLocal() as s:
        run_id = run_repository.create(s, session_id=uuid.UUID(sid), snapshot_id=uuid.UUID(snap)).id
    outage()
    called = []
    monkeypatch.setitem(worker.ADAPTERS, "PYTHON3", type("A", (), {"execute": lambda self, *a, **k: called.append(a)})())
    with TestingSessionLocal() as s:
        worker.process_run(s, run_id)
    assert called == []
    run = db.get(Run, run_id)
    assert run.status == "FAILED_INTERNAL" and run.testcase_results == {"stderr": "Snapshot content unavailable"}


# ---------------------------------------------------------------------------
# AC-11-04 — first-admin bootstrap
# ---------------------------------------------------------------------------
def test_bootstrap_creates_single_admin_with_forced_change(db, monkeypatch, capsys):
    monkeypatch.setenv(cli.PASSWORD_ENV, "a-strong-bootstrap-pw")
    monkeypatch.setattr(cli, "SessionLocal", TestingSessionLocal)
    assert cli.main(["create-admin", "--username", "root", "--email", "root@spnc.io"]) == 0
    out = capsys.readouterr()
    assert "a-strong-bootstrap-pw" not in out.out + out.err      # never echoed

    admin = db.scalar(select(User).where(User.username == "root"))
    assert admin.role == "ADMIN" and admin.status == "ACTIVE" and admin.force_password_change is True
    log = db.scalar(select(AuditLog).where(AuditLog.action == "ADMIN_BOOTSTRAPPED"))
    assert log.actor_id is None and log.target_id == str(admin.id)

    r = client.post("/api/v1/auth/login", data={"username": "root", "password": "a-strong-bootstrap-pw"})
    assert r.status_code == 200
    r = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert r.status_code == 403 and r.json()["error_code"] == "PASSWORD_CHANGE_REQUIRED"

    # A second run is refused whatever the username
    assert cli.main(["create-admin", "--username", "root2", "--email", "root2@spnc.io"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert db.scalar(select(User).where(User.username == "root2")) is None


def test_bootstrap_refuses_weak_or_missing_password(db, monkeypatch):
    monkeypatch.setattr(cli, "SessionLocal", TestingSessionLocal)
    monkeypatch.delenv(cli.PASSWORD_ENV, raising=False)
    assert cli.main(["create-admin", "--username", "root", "--email", "root@spnc.io"]) == 1
    monkeypatch.setenv(cli.PASSWORD_ENV, "short")
    assert cli.main(["create-admin", "--username", "root", "--email", "root@spnc.io"]) == 1
    assert db.scalars(select(User)).all() == []


def test_bootstrap_refuses_taken_username(db, world):
    with TestingSessionLocal() as s, pytest.raises(bootstrap.BootstrapRefused):
        bootstrap.create_first_admin(s, "teacher", "new@spnc.io", "a-strong-bootstrap-pw")
