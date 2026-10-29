"""Phase 17 — Observability (docs/43; AC-17-01 … AC-17-06).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test); memory storage
backend, real Redis. The S3 readiness check uses the disposable MinIO on 127.0.0.1:19000
(see tests/infra/test_storage_s3.py).
"""
import io
import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import redis
from prometheus_client import REGISTRY
from sqlalchemy import text

from app import reconciler, worker
from app.core.config import settings
from app.core.logging import JsonFormatter, configure_logging, redact
from app.core.metrics import start_metrics_server
from app.models.run_submit import Run
from app.models.trace import CodeSnapshot
from app.repositories import submission as submission_repo
from app.repositories.run import run_repository
from app.services import health as health_svc
from app.services import snapshot_cleanup
from app.services.queue import judge_queue
from app.services.storage import StorageAdapter, StorageUnavailable, storage_adapter
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    FakeAdapter, TestingSessionLocal, _judge, _make_user, _practice_session, _snapshot, _submit, client,
    clean_db, db, enqueued, setup_database, world,
)

API_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def metric(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def logs():
    """Captures every log record as the containers would emit it (JSON lines)."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    from app.core.logging import _ContextFilter
    handler.addFilter(_ContextFilter())
    # alembic's fileConfig (test database setup) disables loggers that already exist
    for lg in logging.Logger.manager.loggerDict.values():
        if isinstance(lg, logging.Logger):
            lg.disabled = False
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield lambda: [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]
    root.removeHandler(handler)
    root.setLevel(old_level)


@pytest.fixture(autouse=True)
def probe_headroom(monkeypatch):
    """On Windows a new connection to "localhost" tries ::1 first and needs about 2 s to fall
    back to 127.0.0.1 (where the test containers listen), which equals the default probe timeout."""
    monkeypatch.setattr(settings, "READY_CHECK_TIMEOUT_SECONDS", 5.0)


@pytest.fixture
def no_redis_runs(monkeypatch):
    ids = []
    monkeypatch.setattr(judge_queue, "enqueue_run", lambda rid: ids.append(rid) or True)
    return ids


def _batch(h, sid, items):
    events = [{"sequence_number": n, "event_type": "EDITOR_CHANGED", "client_timestamp": datetime.now(timezone.utc).isoformat(),
               "payload": payload} for n, payload in items]
    return client.post(f"/api/v1/my/coding-sessions/{sid}/trace-events/batch", json={"events": events}, headers=h)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# AC-17-01 — /health and /ready
# ---------------------------------------------------------------------------
def test_health_needs_nothing_and_metrics_not_on_public_app():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert client.get("/metrics").status_code == 404                      # docs/43 D5


def test_ready_when_all_dependencies_up():
    r = client.get("/ready")
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ready", "checks": {"database": "ok", "redis": "ok", "storage": "ok"}}


@pytest.mark.parametrize("broken", ["database", "redis", "storage"])
def test_ready_503_when_one_dependency_unreachable(broken, monkeypatch, logs):
    if broken == "database":
        monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://spnc_test:secretpw@127.0.0.1:1/nowhere")
    elif broken == "redis":
        monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:1/0")
    else:
        monkeypatch.setattr(settings, "S3_ENDPOINT", "127.0.0.1:1")
        monkeypatch.setattr(settings, "S3_MAX_RETRIES", 0)
        monkeypatch.setattr(health_svc, "storage_adapter", StorageAdapter(bucket_name="spnc-ready", backend="s3"))
    started = time.monotonic()
    r = client.get("/ready", headers={"X-Request-ID": f"ready-{broken}"})
    assert time.monotonic() - started < settings.READY_CHECK_TIMEOUT_SECONDS + 3
    assert r.status_code == 503
    body = r.json()
    assert body["error_code"] == "NOT_READY" and body["message"] and body["request_id"] == f"ready-{broken}"
    assert body["checks"][broken] == "fail"
    assert [k for k, v in body["checks"].items() if v == "fail"] == [broken]
    assert "127.0.0.1" not in r.text and "secretpw" not in r.text           # no detail in the body
    warning = [l for l in logs() if l["logger"] == "app.services.health"]
    assert warning and warning[0]["request_id"] == f"ready-{broken}"      # detail goes to the log
    assert "secretpw" not in json.dumps(logs())


def test_ready_storage_check_against_real_minio(monkeypatch):
    monkeypatch.setattr(settings, "S3_ENDPOINT", os.environ.get("PHASE11_S3_ENDPOINT", "127.0.0.1:19000"))
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", os.environ.get("PHASE11_S3_ACCESS_KEY", "spnc-test"))
    monkeypatch.setattr(settings, "S3_SECRET_KEY", os.environ.get("PHASE11_S3_SECRET_KEY", "spnc-test-password"))
    monkeypatch.setattr(health_svc, "storage_adapter",
                        StorageAdapter(bucket_name=f"spnc-ready-{uuid.uuid4().hex[:10]}", backend="s3"))
    assert health_svc.readiness()["storage"] == "ok"


# ---------------------------------------------------------------------------
# AC-17-02 — integrity counters
# ---------------------------------------------------------------------------
def test_trace_ingest_outcomes(world):
    w = world
    sid = _practice_session(w)
    before = {o: metric("trace_ingest_batch_total", outcome=o) for o in ("accepted", "duplicate", "rejected")}
    conflicts, retries = metric("trace_conflicting_duplicate_total"), metric("trace_batch_retry_total")
    latency_count = metric("trace_ingest_latency_seconds_count")

    assert _batch(w["h_s"], sid, [(1, {"k": "a"}), (2, {"k": "b"})]).status_code == 200
    assert _batch(w["h_s"], sid, [(1, {"k": "a"}), (2, {"k": "b"})]).status_code == 200   # client retry
    assert _batch(w["h_s"], sid, [(2, {"k": "DIFFERENT"})]).status_code == 409

    assert metric("trace_ingest_batch_total", outcome="accepted") == before["accepted"] + 1
    assert metric("trace_ingest_batch_total", outcome="duplicate") == before["duplicate"] + 1
    assert metric("trace_ingest_batch_total", outcome="rejected") == before["rejected"] + 1
    assert metric("trace_batch_retry_total") == retries + 1
    assert metric("trace_conflicting_duplicate_total") == conflicts + 1
    assert metric("trace_ingest_latency_seconds_count") == latency_count + 3


def test_snapshot_upload_failure_counted(world, monkeypatch):
    w = world
    sid = _practice_session(w)
    before = metric("snapshot_upload_failure_total")
    def down(*a, **k):
        raise StorageUnavailable("connection refused")
    monkeypatch.setattr(storage_adapter, "_upload", down)
    r = client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots", json={
        "reason": "RUN", "language": "PYTHON3", "source_code": "print(1)\n", "line_count": 1}, headers=w["h_s"])
    assert r.status_code == 503
    assert metric("snapshot_upload_failure_total") == before + 1


def test_missing_blob_counted_for_run_and_submission(db, world, monkeypatch):
    w = world
    sid = _practice_session(w)
    snap = _snapshot(w["h_s"], sid, "SUM\n")
    sub_id = _submit(w["h_s"], sid, snap).json()["id"]
    with TestingSessionLocal() as s:
        run_id = run_repository.create(s, session_id=uuid.UUID(sid), snapshot_id=uuid.UUID(snap)).id
    storage_adapter.delete_code_snapshot(db.get(CodeSnapshot, uuid.UUID(snap)).object_key)   # blob lost
    run_missing = metric("snapshot_blob_missing_total", reader="worker_run")
    sub_missing = metric("snapshot_blob_missing_total", reader="worker_submission")
    run_fail, sub_fail = metric("judge_worker_failure_total", kind="run"), metric("judge_worker_failure_total", kind="submission")

    with TestingSessionLocal() as s:
        worker.process_run(s, run_id)
    assert _judge(sub_id) is True

    assert metric("snapshot_blob_missing_total", reader="worker_run") == run_missing + 1
    assert metric("snapshot_blob_missing_total", reader="worker_submission") == sub_missing + 1
    assert metric("judge_worker_failure_total", kind="run") == run_fail + 1
    assert metric("judge_worker_failure_total", kind="submission") == sub_fail + 1


def test_orphan_sweep_counters(world, monkeypatch):
    w = world
    sid = _practice_session(w)
    _, orphan = storage_adapter.upload_code_snapshot(sid, 0, f"orphan {uuid.uuid4()}\n")
    storage_adapter._memory_created[orphan] = datetime.now(timezone.utc) - timedelta(hours=48)
    detected, cleaned, failed = (metric("snapshot_orphan_detected_total"), metric("snapshot_orphan_cleanup_total"),
                                 metric("snapshot_orphan_cleanup_failure_total"))
    with TestingSessionLocal() as s:
        snapshot_cleanup.sweep_orphans(s)
    assert metric("snapshot_orphan_detected_total") >= detected + 1
    assert metric("snapshot_orphan_cleanup_total") >= cleaned + 1
    assert metric("snapshot_orphan_cleanup_failure_total") == failed

    def down(*a, **k):
        raise StorageUnavailable("connection refused")
    monkeypatch.setattr(storage_adapter, "list_code_snapshots", down)
    with TestingSessionLocal() as s:
        snapshot_cleanup.sweep_orphans(s)
    assert metric("snapshot_orphan_cleanup_failure_total") == failed + 1


def test_claim_conflict_and_fencing_rejection_for_runs(world, monkeypatch):
    w = world
    sid = _practice_session(w)
    snap = _snapshot(w["h_s"], sid, "print(1)\n")
    with TestingSessionLocal() as s:
        run_id = run_repository.create(s, session_id=uuid.UUID(sid), snapshot_id=uuid.UUID(snap)).id
    claims, fenced = metric("run_claim_conflict_total", kind="run"), metric("run_fencing_rejection_total", kind="run")

    class ReconcilerStrikesMidRun:
        """While the sandbox runs, the reconciler recovers the job (generation bump)."""
        def execute(self, code, inp, **k):
            with TestingSessionLocal() as s2:
                current = s2.get(Run, run_id)
                assert run_repository.recover_stale_run(s2, run_id, current.execution_generation)
            return {"verdict": "ACCEPTED", "stdout": "1\n", "stderr": "", "time_ms": 1, "memory_kb": 1,
                    "compile_error_message": None, "runtime_error_message": None}
    monkeypatch.setitem(worker.ADAPTERS, "PYTHON3", ReconcilerStrikesMidRun())
    with TestingSessionLocal() as s:
        worker.process_run(s, run_id)
    assert metric("run_fencing_rejection_total", kind="run") == fenced + 1

    with TestingSessionLocal() as s:                       # recovered back to PENDING: claim, finish
        monkeypatch.setitem(worker.ADAPTERS, "PYTHON3", type("A", (), {"execute": lambda self, c, i, **k: {
            "verdict": "ACCEPTED", "stdout": "", "stderr": "", "time_ms": 1, "memory_kb": 1,
            "compile_error_message": None, "runtime_error_message": None}})())
        worker.process_run(s, run_id)
    with TestingSessionLocal() as s:                       # duplicate delivery: claim lost
        worker.process_run(s, run_id)
    assert metric("run_claim_conflict_total", kind="run") == claims + 1
    assert metric("judge_execution_duration_seconds_count", kind="run") >= 2


def test_submission_claim_conflict_and_fencing(world):
    w = world
    sid = _practice_session(w)
    sub_id = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n")).json()["id"]
    claims = metric("run_claim_conflict_total", kind="submission")
    fenced = metric("run_fencing_rejection_total", kind="submission")

    class Recovering(FakeAdapter):
        def execute(self, source_code, input_data, memory_limit_mb=None):
            if not self.calls:
                with TestingSessionLocal() as s2:
                    sub = submission_repo.get(s2, uuid.UUID(sub_id))
                    assert submission_repo.recover_stale(s2, sub.id, sub.execution_generation)
            return super().execute(source_code, input_data, memory_limit_mb)

    assert _judge(sub_id, Recovering()) is False          # stale result dropped
    assert metric("run_fencing_rejection_total", kind="submission") == fenced + 1
    assert _judge(sub_id) is True
    assert _judge(sub_id) is False                        # already judged: claim lost
    assert metric("run_claim_conflict_total", kind="submission") == claims + 1


def test_reconciler_reenqueue_and_queue_depth(world, no_redis_runs, monkeypatch):
    w = world
    sid = _practice_session(w)
    snap = _snapshot(w["h_s"], sid, "print(1)\n")
    with TestingSessionLocal() as s:
        run_id = run_repository.create(s, session_id=uuid.UUID(sid), snapshot_id=uuid.UUID(snap)).id
        s.execute(text("UPDATE runs SET updated_at = now() - interval '1 day' WHERE id = :id"), {"id": run_id})
        s.commit()
    before = metric("run_reenqueue_total", kind="run")
    monkeypatch.setattr(reconciler, "maybe_sweep_orphans", lambda db: None)
    reconciler.reconcile()
    assert metric("run_reenqueue_total", kind="run") == before + 1
    assert run_id in no_redis_runs
    depth = redis.Redis.from_url(settings.REDIS_URL).llen("judge_queue")
    assert metric("judge_queue_depth") == depth


def test_enqueue_failure_logged_with_context(monkeypatch, logs):
    monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:1/0")
    q = type(judge_queue)()
    before = metric("judge_enqueue_failure_total", kind="run")
    rid = uuid.uuid4()
    assert q.enqueue_run(rid) is False
    assert metric("judge_enqueue_failure_total", kind="run") == before + 1
    line = [l for l in logs() if l["logger"] == "app.services.queue"][0]
    assert line["level"] == "ERROR" and line["run_id"] == str(rid)        # F4: logger, not print


def test_websocket_auth_rejections_and_active_gauge(db):
    _make_user(db, "wsteacher", "TEACHER")
    _make_user(db, "wsstudent", "STUDENT")
    def token(u):
        return client.post("/api/v1/auth/login", data={"username": u, "password": "Password123!"}).json()["access_token"]
    invalid, forbidden = (metric("websocket_auth_rejection_total", reason="invalid_token"),
                          metric("websocket_auth_rejection_total", reason="forbidden_role"))
    for tok in ("not-a-token", token("wsstudent")):
        with client.websocket_connect("/api/v1/ws/teacher") as ws:
            ws.send_json({"type": "auth", "access_token": tok})
            with pytest.raises(Exception):
                ws.receive_json()
    assert metric("websocket_auth_rejection_total", reason="invalid_token") == invalid + 1
    assert metric("websocket_auth_rejection_total", reason="forbidden_role") == forbidden + 1

    active = metric("websocket_active_connections")
    with client.websocket_connect("/api/v1/ws/teacher") as ws:
        ws.send_json({"type": "auth", "access_token": token("wsteacher")})
        assert ws.receive_json() == {"type": "authenticated"}
        assert metric("websocket_active_connections") == active + 1
    deadline = time.monotonic() + 5
    while metric("websocket_active_connections") != active and time.monotonic() < deadline:
        time.sleep(0.05)
    assert metric("websocket_active_connections") == active


# ---------------------------------------------------------------------------
# AC-17-03 — HTTP metrics by route template
# ---------------------------------------------------------------------------
def test_http_metrics_use_route_template(world):
    w = world
    route = "/api/v1/my/coding-sessions/{session_id}/runs"
    before = metric("http_requests_total", method="GET", route=route, status="200")
    a, b = _practice_session(w), _practice_session(w)
    for sid in (a, b):
        assert client.get(f"/api/v1/my/coding-sessions/{sid}/runs", headers=w["h_s"]).status_code == 200
    assert metric("http_requests_total", method="GET", route=route, status="200") == before + 2
    labels = {s.labels.get("route") for m in REGISTRY.collect() if m.name == "http_requests" for s in m.samples}
    assert not any(a in r or b in r for r in labels if r)                 # no ids in labels
    unmatched = metric("http_requests_total", method="GET", route="unmatched", status="404")
    client.get(f"/no/such/{uuid.uuid4()}")
    assert metric("http_requests_total", method="GET", route="unmatched", status="404") == unmatched + 1


# ---------------------------------------------------------------------------
# AC-17-04 — metrics listener per process
# ---------------------------------------------------------------------------
def test_metrics_port_zero_starts_nothing():
    assert start_metrics_server(0) is False


def test_daemon_serves_metrics_on_internal_port():
    port = _free_port()
    env = {**os.environ, "METRICS_PORT": str(port), "DATABASE_URL": settings.DATABASE_URL,
           "STORAGE_BACKEND": "memory", "LOG_FORMAT": "json", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "app.reconciler"], cwd=API_ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        body, deadline = "", time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2).read().decode()
                if 'spnc_daemon_cycles_total{daemon="reconciler",outcome="ok"} 1.0' in body:
                    break
            except OSError:
                pass
            time.sleep(0.3)
        assert 'spnc_daemon_cycles_total{daemon="reconciler",outcome="ok"} 1.0' in body
        assert 'spnc_daemon_last_success_timestamp_seconds{daemon="reconciler"}' in body
        assert "judge_queue_depth" in body
    finally:
        proc.kill()
        out, _ = proc.communicate(timeout=10)
    lines = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
    assert lines and all(l.get("daemon") == "reconciler" for l in lines)          # JSON logs, daemon tagged
    assert any(l["msg"] == "Reconciler started" for l in lines)


# ---------------------------------------------------------------------------
# AC-17-05 — structured logs, request ids, 500 handler
# ---------------------------------------------------------------------------
def test_request_id_kept_or_replaced_and_in_every_log_line(logs):
    r = client.get("/health", headers={"X-Request-ID": "abc-123.x_y"})
    assert r.headers["X-Request-ID"] == "abc-123.x_y"
    for bad in ("has space", "x" * 65, "evil<script>", "a\"b"):
        r = client.get("/health", headers={"X-Request-ID": bad})
        assert r.headers["X-Request-ID"] != bad and uuid.UUID(r.headers["X-Request-ID"])
    access = [l for l in logs() if l["logger"] == "spnc.access"]
    assert access[0] == {**access[0], "request_id": "abc-123.x_y", "method": "GET", "route": "/health", "status": 200}
    assert isinstance(access[0]["duration_ms"], (int, float)) and "ts" in access[0]


def test_unhandled_exception_returns_internal_error_with_request_id(monkeypatch, logs):
    def boom():
        raise RuntimeError("database password=hunter2 exploded")
    monkeypatch.setattr(health_svc, "readiness", boom)
    r = client.get("/ready", headers={"X-Request-ID": "boom-1"})
    assert r.status_code == 500
    assert r.json() == {"error_code": "INTERNAL_ERROR", "message": "Internal server error", "request_id": "boom-1"}
    assert "hunter2" not in r.text
    err = [l for l in logs() if l["logger"] == "spnc.error"]
    assert len(err) == 1 and err[0]["request_id"] == "boom-1" and "RuntimeError" in err[0]["exc"]
    assert "hunter2" not in err[0]["exc"]                                  # masked by the formatter
    assert metric("http_requests_total", method="GET", route="/ready", status="500") >= 1


def test_text_format_for_local_use():
    buf = io.StringIO()
    root = logging.getLogger()
    saved = list(root.handlers), root.level
    try:
        configure_logging(stream=buf, fmt="text")
        logging.getLogger("t").info("hello token=abc123")
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in saved[0]:
            root.addHandler(h)
        root.setLevel(saved[1])
    assert "INFO t [None] hello token=[REDACTED]" in buf.getvalue()


# ---------------------------------------------------------------------------
# AC-17-06 — log hygiene (PROJECT_RULES #25)
# ---------------------------------------------------------------------------
def test_redaction_patterns():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    assert redact(f"Authorization: Bearer {jwt}") == "Authorization: Bearer [REDACTED]"
    assert redact(f"token {jwt} leaked") == "token [REDACTED_JWT] leaked"
    assert redact("postgresql://spnc:topsecret@db:5432/x") == "postgresql://spnc:[REDACTED]@db:5432/x"
    assert redact("login password=hunter2 ok") == "login password=[REDACTED] ok"
    assert redact('{"refresh_token": "abc.def"}') == '{"refresh_token": "[REDACTED]"}'
    assert redact("run 1234 finished in 5 ms") == "run 1234 finished in 5 ms"   # ordinary text untouched


def test_no_secret_or_student_content_in_logs(db, world, no_redis_runs, logs):
    password, new_password = "Mk-Pass-7f3a9e!", "Mk-NewPass-1b2c8d!"
    source, payload, scratch, stdin = ("print('MARKER_SOURCE_91ab')", "MARKER_PAYLOAD_55cd",
                                       "MARKER_SCRATCH_77ef", "MARKER_STDIN_33aa")
    w = world
    _make_user(db, "hygiene", "STUDENT")
    from app.core.security import get_password_hash
    db.execute(text("UPDATE users SET password_hash = :h WHERE username = 'hygiene'"), {"h": get_password_hash(password)})
    db.commit()
    client.post("/api/v1/auth/login", data={"username": "hygiene", "password": "wrong-" + password})   # failed login
    tokens = client.post("/api/v1/auth/login", data={"username": "hygiene", "password": password}).json()
    access, refresh = tokens["access_token"], tokens["refresh_token"]
    h = {"Authorization": f"Bearer {access}"}
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).json()
    assert client.post("/api/v1/auth/change-password", json={"current_password": password, "new_password": new_password},
                       headers={"Authorization": f"Bearer {refreshed['access_token']}"}).status_code == 200

    sid = _practice_session(w)
    assert _batch(w["h_s"], sid, [(1, {"text": payload})]).status_code == 200
    assert _batch(w["h_s"], sid, [(1, {"text": payload + "x"})]).status_code == 409         # conflict path logs too
    snap = _snapshot(w["h_s"], sid, source)
    assert client.put(f"/api/v1/my/coding-sessions/{sid}/scratchpad", json={
        "content": scratch, "client_timestamp": datetime.now(timezone.utc).isoformat()}, headers=w["h_s"]).status_code == 200
    assert client.post(f"/api/v1/my/coding-sessions/{sid}/runs", json={"snapshot_id": snap, "input": stdin},
                       headers=w["h_s"]).status_code == 200

    captured = json.dumps(logs())
    assert '"spnc.access"' in captured                                     # logs were really captured
    for marker in (password, new_password, access, refresh, refreshed["access_token"], refreshed["refresh_token"],
                   "MARKER_SOURCE_91ab", payload, scratch, stdin, w["h_s"]["Authorization"].split()[1]):
        assert marker not in captured, f"leaked into logs: {marker[:12]}…"
