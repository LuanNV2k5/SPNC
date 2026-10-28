"""Phase 13A — Content-addressed snapshot keys and orphan cleanup (docs/39 D1, D2; AC-13-01, AC-13-02).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test); memory storage backend.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app import reconciler
from app.models.run_submit import Submission
from app.models.trace import CodeSnapshot
from app.services import snapshot_cleanup
from app.services.storage import StorageUnavailable, storage_adapter
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _judge, _practice_session, client,
    clean_db, db, enqueued, setup_database, world,
)

BODY = {"reason": "RUN", "language": "PYTHON3", "source_code": "SUM\n", "line_count": 1}


def _snap(h, sid, body=BODY):
    return client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots", json=body, headers=h)


def test_identical_code_snapshots_twice_and_shares_blob(db, world):
    """F1 regression: the second identical snapshot used to fail with 500."""
    w = world
    sid = _practice_session(w)
    r1, r2 = _snap(w["h_s"], sid), _snap(w["h_s"], sid)
    assert r1.status_code == 200 and r2.status_code == 200, r2.text
    assert r1.json()["id"] != r2.json()["id"]
    rows = db.scalars(select(CodeSnapshot).where(CodeSnapshot.session_id == uuid.UUID(sid))).all()
    assert len(rows) == 2 and rows[0].object_key == rows[1].object_key
    assert rows[0].object_key == f"snapshots/{sid}/{rows[0].source_hash}.txt"

    # Both snapshots are usable: a Run of each would read the same blob; submit the second one
    sub = client.post(f"/api/v1/my/coding-sessions/{sid}/submissions", json={"snapshot_id": r2.json()["id"]}, headers=w["h_s"])
    assert sub.status_code == 201
    assert _judge(sub.json()["id"]) is True
    assert db.get(Submission, uuid.UUID(sub.json()["id"])).verdict == "ACCEPTED"


def test_old_format_keys_still_readable(db, world):
    w = world
    sid = _practice_session(w)
    snap_id = _snap(w["h_s"], sid).json()["id"]
    old_key = f"snapshots/{sid}/0_deadbeef.txt"           # Phase 06 format
    storage_adapter._memory_store[old_key] = "SUM\n"
    with TestingSessionLocal() as s:
        s.execute(text("UPDATE code_snapshots SET object_key = :k WHERE id = :id"), {"k": old_key, "id": snap_id})
        s.commit()
    sub_id = client.post(f"/api/v1/my/coding-sessions/{sid}/submissions", json={"snapshot_id": snap_id}, headers=w["h_s"]).json()["id"]
    assert _judge(sub_id) is True
    assert db.get(Submission, uuid.UUID(sub_id)).verdict == "ACCEPTED"


def _age(key, hours):
    storage_adapter._memory_created[key] = datetime.now(timezone.utc) - timedelta(hours=hours)


def test_orphan_sweep_deletes_only_old_unreferenced_blobs(db, world):
    w = world
    sid = _practice_session(w)
    referenced_key = db.get(CodeSnapshot, uuid.UUID(_snap(w["h_s"], sid).json()["id"])).object_key
    _, old_orphan = storage_adapter.upload_code_snapshot(sid, 0, "orphan, old\n")
    _, new_orphan = storage_adapter.upload_code_snapshot(sid, 0, "orphan, recent\n")
    _age(referenced_key, 48)
    _age(old_orphan, 25)
    _age(new_orphan, 1)

    with TestingSessionLocal() as s:
        result = snapshot_cleanup.sweep_orphans(s)
    assert result["deleted"] == 1 and result["errors"] == 0
    assert storage_adapter.exists_code_snapshot(old_orphan) is False
    assert storage_adapter.exists_code_snapshot(referenced_key) is True      # referenced: never deleted
    assert storage_adapter.exists_code_snapshot(new_orphan) is True          # inside the grace period


def test_orphan_sweep_survives_storage_errors(db, world, monkeypatch):
    def down(*a, **k):
        raise StorageUnavailable("minio down")
    monkeypatch.setattr(storage_adapter, "list_code_snapshots", down)
    with TestingSessionLocal() as s:
        assert snapshot_cleanup.sweep_orphans(s) == {"scanned": 0, "deleted": 0, "errors": 1}

    monkeypatch.undo()
    _, key = storage_adapter.upload_code_snapshot("s", 0, "x\n")
    _age(key, 30)
    monkeypatch.setattr(storage_adapter, "delete_code_snapshot", down)
    with TestingSessionLocal() as s:
        result = snapshot_cleanup.sweep_orphans(s)
    assert result["errors"] >= 1 and result["deleted"] == 0


def test_reconciler_sweeps_at_most_once_per_interval(monkeypatch):
    calls = []
    monkeypatch.setattr(reconciler, "sweep_orphans", lambda db: calls.append(1) or {})
    monkeypatch.setattr(reconciler, "_last_orphan_sweep", 0.0)
    t = {"now": 1000.0}
    clock = lambda: t["now"]  # noqa: E731
    reconciler.maybe_sweep_orphans(None, clock)
    t["now"] += 10
    reconciler.maybe_sweep_orphans(None, clock)
    t["now"] += 3600
    reconciler.maybe_sweep_orphans(None, clock)
    assert len(calls) == 2
