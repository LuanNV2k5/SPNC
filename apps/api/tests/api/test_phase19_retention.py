"""Phase 19 — Retention purge of raw trace data (docs/45; AC-19-01 … AC-19-10).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test); memory storage backend.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import func, select, text

from app import cli, reconciler
from app.core.config import settings
from app.models.observation import AttentionSignal
from app.models.run_submit import Submission
from app.models.session import CodingSession
from app.models.trace import CodeSnapshot, ScratchpadRevision, TraceEvent
from app.models.user import AuditLog, RefreshSession, User
from app.services import retention, snapshot_cleanup
from app.services.storage import StorageUnavailable, storage_adapter
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _auth, _exam_session, _judge, _make_user, _practice_session, _snapshot, _submit,
    client, clean_db, db, enqueued, setup_database, world,
)

DAY = timedelta(days=1)


def _snap(h, sid, code, reason="CHECKPOINT"):
    r = client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots", json={
        "reason": reason, "language": "PYTHON3", "source_code": code, "line_count": len(code.splitlines()),
    }, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _add_raw_trace(sid, events=3, revisions=2, keep_outbox=False):
    """Trace rows written directly; the materializer is simulated by clearing the outbox."""
    now = datetime.now(timezone.utc)
    with TestingSessionLocal() as s:
        start = (s.scalar(select(func.max(TraceEvent.sequence_number)).where(TraceEvent.session_id == sid)) or 0) + 1
        for i in range(events):
            s.add(TraceEvent(session_id=sid, sequence_number=start + i, event_type="EDITOR_CHANGED",
                             canonical_fingerprint=f"fp-{sid}-{start + i}", client_timestamp=now, payload={"k": i}))
        for i in range(revisions):
            s.add(ScratchpadRevision(session_id=sid, revision_sequence=i + 1, canonical_fingerprint=f"sp-{sid}-{i}",
                                     content="notes", client_timestamp=now))
        s.commit()
        if not keep_outbox:
            s.execute(text("DELETE FROM trace_signal_outbox WHERE session_id = :s"), {"s": sid})
            s.commit()


def _end(sid, days_ago, status="ENDED"):
    with TestingSessionLocal() as s:
        s.execute(text("UPDATE coding_sessions SET status = :st, ended_at = :t WHERE id = :id"),
                  {"st": status, "t": datetime.now(timezone.utc) - days_ago * DAY, "id": sid})
        s.execute(text("DELETE FROM trace_signal_outbox WHERE session_id = :s"), {"s": sid})
        s.commit()


def _count(model, sid):
    with TestingSessionLocal() as s:
        return s.scalar(select(func.count()).select_from(model).where(model.session_id == sid))


def _purge(apply=True, **kw):
    with TestingSessionLocal() as s:
        return retention.purge(s, apply=apply, **kw)


def _sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def old_session(world):
    """A practice session that ended 200 days ago with: a checkpoint snapshot (own blob), a checkpoint
    with the submitted content (shared blob), a judged submission, raw trace and one signal."""
    w = world
    sid = _practice_session(w)
    cp = _snap(w["h_s"], sid, "draft\n")
    shared_cp = _snap(w["h_s"], sid, "SUM\n")
    sub_snap = _snapshot(w["h_s"], sid, "SUM\n")
    sub = _submit(w["h_s"], sid, sub_snap)
    assert sub.status_code == 201, sub.text
    assert _judge(sub.json()["id"]) is True
    _add_raw_trace(uuid.UUID(sid))
    with TestingSessionLocal() as s:
        s.add(AttentionSignal(session_id=uuid.UUID(sid), student_id=w["student_id"], signal_type="IDLE_DETECTED",
                              evidence={"gap_seconds": 400}))
        s.commit()
    _end(sid, 200)
    with TestingSessionLocal() as s:
        keys = {i: s.get(CodeSnapshot, uuid.UUID(i)).object_key for i in (cp, shared_cp, sub_snap)}
    return {**w, "sid": sid, "cp": cp, "shared_cp": shared_cp, "sub_snap": sub_snap,
            "sub_id": sub.json()["id"], "keys": keys}


# ---------------------------------------------------------------------------
# AC-19-01 / AC-19-03 — what is purged and what stays
# ---------------------------------------------------------------------------

def test_purge_removes_raw_trace_and_keeps_academic_records(old_session):
    o = old_session
    sid = uuid.UUID(o["sid"])
    result = _purge()
    assert result["sessions_purged"] == 1 and result["mode"] == "apply"
    assert _count(TraceEvent, sid) == 0 and _count(ScratchpadRevision, sid) == 0

    with TestingSessionLocal() as s:
        remaining = {str(r.id) for r in s.scalars(select(CodeSnapshot).where(CodeSnapshot.session_id == sid))}
        session = s.get(CodingSession, sid)
        assert remaining == {o["sub_snap"]}                      # only the graded code stays
        assert session is not None and session.trace_purged_at is not None and session.status == "ENDED"
        sub = s.get(Submission, uuid.UUID(o["sub_id"]))
        assert sub.verdict == "ACCEPTED" and sub.score is not None
        assert s.scalar(select(func.count()).select_from(AttentionSignal).where(AttentionSignal.session_id == sid)) == 1

    assert storage_adapter.exists_code_snapshot(o["keys"][o["cp"]]) is False        # own blob deleted
    assert storage_adapter.exists_code_snapshot(o["keys"][o["sub_snap"]]) is True   # shared with the submission
    assert result["code_snapshots"] == 2 and result["blobs_deleted"] == 1
    # The submission still judges from its blob: no row points at a missing blob
    with TestingSessionLocal() as s:
        for key in s.scalars(select(CodeSnapshot.object_key)):
            assert storage_adapter.exists_code_snapshot(key)


def test_failed_blob_delete_is_left_for_the_orphan_sweep(old_session, monkeypatch):
    o = old_session
    before = _sample("retention_purge_blob_delete_total", outcome="failed")

    def down(key):
        raise StorageUnavailable("minio down")
    monkeypatch.setattr(storage_adapter, "delete_code_snapshot", down)
    result = _purge()
    assert result["blob_delete_failures"] == 1 and result["blobs_deleted"] == 0
    assert _sample("retention_purge_blob_delete_total", outcome="failed") == before + 1
    monkeypatch.undo()

    orphan = o["keys"][o["cp"]]
    assert storage_adapter.exists_code_snapshot(orphan)
    storage_adapter._memory_created[orphan] = datetime.now(timezone.utc) - timedelta(hours=48)
    with TestingSessionLocal() as s:
        assert snapshot_cleanup.sweep_orphans(s)["deleted"] >= 1
    assert storage_adapter.exists_code_snapshot(orphan) is False


# ---------------------------------------------------------------------------
# AC-19-02 — what is never touched
# ---------------------------------------------------------------------------

def test_not_eligible_sessions_are_untouched(db, world):
    w = world
    active = _practice_session(w)
    _add_raw_trace(uuid.UUID(active))
    with TestingSessionLocal() as s:     # ACTIVE but opened long ago: still never purged
        s.execute(text("UPDATE coding_sessions SET opened_at = :t WHERE id = :id"),
                  {"t": datetime.now(timezone.utc) - 400 * DAY, "id": active})
        s.commit()

    recent = _practice_session(w)
    _add_raw_trace(uuid.UUID(recent))
    _end(recent, 100)                    # inside 180 days

    pending = _practice_session(w)
    _end(pending, 200)
    _add_raw_trace(uuid.UUID(pending), keep_outbox=True)   # outbox not processed yet

    result = _purge()
    assert result["sessions_purged"] == 0
    for sid in (active, recent, pending):
        assert _count(TraceEvent, uuid.UUID(sid)) > 0


def _age_exam(eid, status, end_days_ago):
    with TestingSessionLocal() as s:
        t = datetime.now(timezone.utc) - end_days_ago * DAY
        s.execute(text("UPDATE exams SET status = :st, start_time = :a, end_time = :b WHERE id = :id"),
                  {"st": status, "a": t - DAY, "b": t, "id": eid})
        s.commit()


def test_exam_sessions_need_a_finished_old_exam_without_hold(db, world):
    w = world
    eid, _, sid = _exam_session(w)
    _add_raw_trace(uuid.UUID(sid))
    _end(sid, 200)

    _age_exam(eid, "ONGOING", 200)       # exam not finished
    assert _purge()["sessions_purged"] == 0
    _age_exam(eid, "ENDED", 100)         # finished inside the window
    assert _purge()["sessions_purged"] == 0
    _age_exam(eid, "ENDED", 200)
    with TestingSessionLocal() as s:
        s.execute(text("UPDATE exams SET retention_hold = true WHERE id = :id"), {"id": eid})
        s.commit()
    assert _purge()["sessions_purged"] == 0      # on hold
    with TestingSessionLocal() as s:
        s.execute(text("UPDATE exams SET retention_hold = false WHERE id = :id"), {"id": eid})
        s.commit()
    assert _purge()["sessions_purged"] == 1
    assert _count(TraceEvent, uuid.UUID(sid)) == 0


# ---------------------------------------------------------------------------
# AC-19-04 / AC-19-09 — dry run, idempotence, audit, metrics
# ---------------------------------------------------------------------------

def test_dry_run_matches_apply_and_second_apply_is_empty(old_session):
    sid = uuid.UUID(old_session["sid"])
    dry = _purge(apply=False)
    assert dry["mode"] == "dry_run" and dry["sessions_purged"] == 1
    assert _count(TraceEvent, sid) > 0
    with TestingSessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "RETENTION_PURGE")) == 0
        assert s.get(CodingSession, sid).trace_purged_at is None

    rows_before = _sample("retention_purge_rows_total", data_class="trace_event")
    applied = _purge()
    for key in ("sessions_purged", "trace_events", "scratchpad_revisions", "code_snapshots"):
        assert applied[key] == dry[key], key
    assert _sample("retention_purge_rows_total", data_class="trace_event") == rows_before + applied["trace_events"]
    assert _sample("retention_purge_eligible_sessions") == 1

    with TestingSessionLocal() as s:
        audit = s.scalars(select(AuditLog).where(AuditLog.action == "RETENTION_PURGE")).all()
        assert len(audit) == 1 and audit[0].actor_id is None
        assert audit[0].metadata_payload["session_ids"] == [str(sid)]
        assert audit[0].metadata_payload["trace_events"] == applied["trace_events"]

    again = _purge()
    assert again["sessions_purged"] == 0 and again["trace_events"] == 0 and again["batches"] == 0


def test_batches_are_bounded(db, world):
    w = world
    sids = [_practice_session(w) for _ in range(3)]
    for sid in sids:
        _add_raw_trace(uuid.UUID(sid), events=1, revisions=0)
        _end(sid, 200)
    first = _purge(batch_size=1, max_batches=2)
    assert first["sessions_purged"] == 2 and first["batches"] == 2
    assert _purge(batch_size=1, max_batches=2)["sessions_purged"] == 1


def test_concurrent_purge_is_skipped_while_lock_held(old_session):
    """Two runners never work at once (advisory lock, docs/45 §3.4)."""
    holder = TestingSessionLocal()
    try:
        holder.execute(select(func.pg_advisory_xact_lock(retention.ADVISORY_LOCK_KEY)))
        result = _purge()
        assert result["sessions_purged"] == 0
    finally:
        holder.rollback()
        holder.close()
    assert _purge()["sessions_purged"] == 1


# ---------------------------------------------------------------------------
# AC-19-05 — retention setting
# ---------------------------------------------------------------------------

def test_retention_comes_from_admin_setting_with_floor(db, world):
    _make_user(db, "admin", "ADMIN")
    h_a = _auth("admin")
    assert client.get("/api/v1/admin/settings", headers=h_a).json()["retention_days"] == settings.RETENTION_DEFAULT_DAYS == 180
    with TestingSessionLocal() as s:
        assert retention.retention_days(s) == 180

    sid = _practice_session(world)
    _add_raw_trace(uuid.UUID(sid), events=1, revisions=0)
    _end(sid, 60)
    assert _purge()["sessions_purged"] == 0                  # 60 < 180

    assert client.patch("/api/v1/admin/settings", json={"retention_days": 45}, headers=h_a).status_code == 200
    with TestingSessionLocal() as s:
        assert retention.retention_days(s) == 45
    assert _purge(apply=False)["retention_days"] == 45

    assert client.patch("/api/v1/admin/settings", json={"retention_days": 5}, headers=h_a).status_code == 200
    with TestingSessionLocal() as s:
        assert retention.retention_days(s) == settings.RETENTION_MIN_DAYS == 30   # clamped
    assert _purge()["sessions_purged"] == 1                  # 60 > 45 and > 30


# ---------------------------------------------------------------------------
# AC-19-06 — refresh tokens
# ---------------------------------------------------------------------------

def test_expired_refresh_tokens_older_than_grace_are_deleted(db, world):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with TestingSessionLocal() as s:
        uid = s.scalar(select(User.id).where(User.username == "stu"))
        for name, exp in (("old", now - 10 * DAY), ("recent", now - 2 * DAY), ("valid", now + DAY)):
            s.add(RefreshSession(user_id=uid, token_hash=f"hash-{name}", expires_at=exp))
        s.commit()
    assert _purge(apply=False)["refresh_sessions"] == 1
    assert _purge()["refresh_sessions"] == 1
    with TestingSessionLocal() as s:
        left = set(s.scalars(select(RefreshSession.token_hash).where(RefreshSession.token_hash.like("hash-%"))))
    assert left == {"hash-recent", "hash-valid"}


# ---------------------------------------------------------------------------
# AC-19-07 — retention hold endpoint
# ---------------------------------------------------------------------------

def test_retention_hold_endpoint(db, world):
    w = world
    _make_user(db, "admin", "ADMIN")
    h_a = _auth("admin")
    eid, _, _ = _exam_session(w)
    url = f"/api/v1/admin/exams/{eid}/retention-hold"

    assert client.put(url, json={"hold": True, "reason": "grade dispute"}, headers=w["h_t"]).status_code == 403
    assert client.put(url, json={"hold": True, "reason": "grade dispute"}, headers=w["h_s"]).status_code == 403

    r = client.put(url, json={"hold": True, "reason": "grade dispute"}, headers=h_a)
    assert r.status_code == 200, r.text
    assert r.json()["retention_hold"] is True
    assert client.get(f"/api/v1/admin/exams/{eid}", headers=h_a).json()["retention_hold"] is True
    with TestingSessionLocal() as s:
        a = s.scalars(select(AuditLog).where(AuditLog.action == "RETENTION_HOLD_CHANGED")).one()
        assert a.target_id == eid and a.metadata_payload == {"old": False, "new": True, "reason": "grade dispute"}

    missing = client.put(f"/api/v1/admin/exams/{uuid.uuid4()}/retention-hold", json={"hold": True, "reason": "x"}, headers=h_a)
    assert missing.status_code == 404
    body = missing.json()
    assert body["error_code"] == "EXAM_NOT_FOUND" and "request_id" in body and "message" in body
    assert client.put(url, json={"hold": True, "reason": ""}, headers=h_a).status_code == 422


# ---------------------------------------------------------------------------
# AC-19-08 — visibility of a purge
# ---------------------------------------------------------------------------

def test_timeline_of_purged_session_reports_trace_purged_at(old_session):
    o = old_session
    url = f"/api/v1/classes/{o['home_class']}/students/{o['student_id']}/sessions/{o['sid']}/timeline"
    before = client.get(url, headers=o["h_t"])
    assert before.status_code == 200, before.text
    assert before.json()["session"]["trace_purged_at"] is None and before.json()["total_events"] > 0

    _purge()
    after = client.get(url, headers=o["h_t"]).json()
    assert after["session"]["trace_purged_at"] is not None
    assert after["total_events"] == 0 and after["events"] == []
    assert [s["id"] for s in after["snapshots"]] == [o["sub_snap"]]


# ---------------------------------------------------------------------------
# AC-19-10 — runners
# ---------------------------------------------------------------------------

def test_reconciler_hook_is_off_by_default_and_rate_limited(monkeypatch):
    calls = []
    monkeypatch.setattr(reconciler, "retention_purge", lambda db, apply: calls.append(apply) or {})
    monkeypatch.setattr(reconciler, "_last_retention_purge", 0.0)
    t = {"now": 1000.0}
    clock = lambda: t["now"]  # noqa: E731
    assert settings.RETENTION_PURGE_ENABLED is False
    assert reconciler.maybe_purge_retention(None, clock) is None and calls == []

    monkeypatch.setattr(settings, "RETENTION_PURGE_ENABLED", True)
    reconciler.maybe_purge_retention(None, clock)
    t["now"] += 60
    reconciler.maybe_purge_retention(None, clock)
    t["now"] += settings.RETENTION_PURGE_INTERVAL_SECONDS
    reconciler.maybe_purge_retention(None, clock)
    assert calls == [True, True]


def test_cli_dry_runs_by_default(old_session, monkeypatch, capsys):
    monkeypatch.setattr(cli, "SessionLocal", TestingSessionLocal)
    sid = uuid.UUID(old_session["sid"])
    assert cli.main(["retention-purge"]) == 0
    assert '"mode": "dry_run"' in capsys.readouterr().out
    assert _count(TraceEvent, sid) > 0
    assert cli.main(["retention-purge", "--apply"]) == 0
    assert '"sessions_purged": 1' in capsys.readouterr().out
    assert _count(TraceEvent, sid) == 0
