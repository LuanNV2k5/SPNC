"""Phase 18 — Backup / restore tool (docs/44; AC-18-01 … AC-18-04, D3, D5).

Drives deploy/backup/spnc_backup.py against a real PostgreSQL and MinIO:
- PostgreSQL: the server of DATABASE_URL. The test creates its own databases
  spnc_p18_backup_src (migrated, seeded) and spnc_p18_backup_dst_* (restore targets).
- MinIO: the disposable test container on 127.0.0.1:19000 (see test_storage_s3.py).
- pg_dump / pg_restore: run in postgres:16-alpine through Docker, so the test needs no
  PostgreSQL client on the host (docs/44 F7). The container reaches the database through
  host.docker.internal (SPNC_BACKUP_PG_TOOLS_HOST overrides it).
"""
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models.problem import Problem
from app.models.session import CodingSession, PracticeAttempt
from app.models.trace import CodeSnapshot, TraceEvent
from app.models.user import User

ROOT = Path(__file__).resolve().parents[4]
API_DIR = ROOT / "apps" / "api"
_spec = importlib.util.spec_from_file_location("spnc_backup", ROOT / "deploy" / "backup" / "spnc_backup.py")
bk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bk)

S3_ENDPOINT = os.environ.get("PHASE11_S3_ENDPOINT", "127.0.0.1:19000")
S3_ACCESS = os.environ.get("PHASE11_S3_ACCESS_KEY", "spnc-test")
S3_SECRET = os.environ.get("PHASE11_S3_SECRET_KEY", "spnc-test-password")
TOOLS_HOST = os.environ.get("SPNC_BACKUP_PG_TOOLS_HOST", "host.docker.internal")
PG_PREFIX = ["docker", "run", "--rm", "-i", "--add-host=host.docker.internal:host-gateway",
             "-e", "PGHOST", "-e", "PGPORT", "-e", "PGUSER", "-e", "PGPASSWORD", "-e", "PGDATABASE",
             "postgres:16-alpine"]

SERVER = make_url(os.environ["DATABASE_URL"])
SRC_DB = "spnc_p18_backup_src"
CODES = ["a, b = map(int, input().split())\nprint(a + b)\n", "print('xin chao')\n", "x = 1\n"]


def _url(db):
    return SERVER.set(database=db).render_as_string(hide_password=False)


def _recreate(db):
    eng = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}"'))
    eng.dispose()


def _drop(db):
    eng = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
    eng.dispose()


def _minio():
    from minio import Minio
    return Minio(S3_ENDPOINT, access_key=S3_ACCESS, secret_key=S3_SECRET, secure=False)


def _put(client, bucket, key, content):
    data = content.encode()
    client.put_object(bucket, key, io.BytesIO(data), len(data))


def _cfg(db, bucket, backup_dir, **kw):
    return bk.Config(database_url=_url(db), s3_endpoint=S3_ENDPOINT, s3_access_key=S3_ACCESS,
                     s3_secret_key=S3_SECRET, s3_bucket=bucket, backup_dir=str(backup_dir),
                     pg_cmd_prefix=PG_PREFIX, pg_tools_host=TOOLS_HOST, connect_timeout_seconds=5, **kw)


def _add_snapshot(s, session_id, code, key=None):
    h = hashlib.sha256(code.encode()).hexdigest()
    key = key or f"snapshots/{session_id}/{h}.txt"
    s.add(CodeSnapshot(session_id=session_id, reason="RUN", language="PYTHON3", source_hash=h,
                       object_key=key, line_count=code.count("\n")))
    return key


@pytest.fixture(scope="module")
def source():
    """Migrated source database with users, a problem, a session, snapshots, trace, and its bucket."""
    _recreate(SRC_DB)
    env = dict(os.environ, DATABASE_URL=_url(SRC_DB))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_DIR, env=env,
                   check=True, capture_output=True)
    bucket = f"spnc-p18-src-{uuid.uuid4().hex[:10]}"
    client = _minio()
    client.make_bucket(bucket)

    eng = create_engine(_url(SRC_DB))
    with Session(eng) as s:
        teacher = User(username="p18_teacher", email="t@p18.test", password_hash="x", full_name="T", role="TEACHER")
        student = User(username="p18_student", email="s@p18.test", password_hash="x", full_name="S", role="STUDENT")
        s.add_all([teacher, student])
        s.flush()
        problem = Problem(title="Sum", description="a+b", owner_id=teacher.id)
        s.add(problem)
        s.flush()
        attempt = PracticeAttempt(student_id=student.id, problem_id=problem.id)
        s.add(attempt)
        s.flush()
        cs = CodingSession(student_id=student.id, problem_id=problem.id, language="PYTHON3", practice_attempt_id=attempt.id)
        s.add(cs)
        s.flush()
        keys = []
        for code in CODES:
            key = _add_snapshot(s, cs.id, code)
            _put(client, bucket, key, code)
            keys.append(key)
        _add_snapshot(s, cs.id, CODES[0])                     # second row sharing one blob (docs/39 D1)
        for i in range(1, 6):
            s.add(TraceEvent(session_id=cs.id, sequence_number=i, event_type="EDITOR_CHANGED",
                             canonical_fingerprint=f"fp{i}", client_timestamp=datetime.now(timezone.utc),
                             payload={"i": i}))
        s.commit()
        session_id = cs.id
    _put(client, bucket, f"snapshots/{session_id}/orphan.txt", "orphan\n")   # unreferenced
    yield {"engine": eng, "bucket": bucket, "keys": keys, "session_id": session_id}
    eng.dispose()
    _drop(SRC_DB)


@pytest.fixture
def target():
    db = f"spnc_p18_backup_dst_{uuid.uuid4().hex[:8]}"
    _recreate(db)
    yield db, f"spnc-p18-dst-{uuid.uuid4().hex[:10]}"
    _drop(db)


def test_backup_set_is_complete_and_consistent(source, tmp_path):
    """AC-18-01: manifest lists exactly the referenced keys, with content hashes; orphans are left out."""
    path = bk.create_backup(_cfg(SRC_DB, source["bucket"], tmp_path))
    assert bk.SET_RE.match(os.path.basename(path))
    assert bk.verify_set(path) == []
    m = bk.load_manifest(path)
    assert sorted(b["key"] for b in m["blobs"]) == sorted(source["keys"])
    for b in m["blobs"]:
        content = (Path(path) / "blobs" / b["key"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == b["sha256"] == Path(b["key"]).stem
    assert m["row_counts"]["code_snapshots"] == 4 and m["row_counts"]["trace_events"] == 5
    assert m["row_counts"]["users"] == 2
    with source["engine"].connect() as c:
        assert m["alembic_revision"] == c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert not any(n.endswith(bk.PARTIAL_SUFFIX) for n in os.listdir(tmp_path))


def test_missing_referenced_blob_fails_backup(source, tmp_path):
    """AC-18-02 (docs/44 F4): a referenced blob that vanished fails the backup; no final set remains."""
    with Session(source["engine"]) as s:
        lost = _add_snapshot(s, source["session_id"], "never uploaded\n")
        s.commit()
    try:
        with pytest.raises(bk.BackupError, match="missing"):
            bk.create_backup(_cfg(SRC_DB, source["bucket"], tmp_path))
        assert os.listdir(tmp_path) == []
    finally:
        with source["engine"].begin() as c:
            c.execute(text("DELETE FROM code_snapshots WHERE object_key = :k"), {"k": lost})


def test_tampered_blob_fails_backup(source, tmp_path):
    client = _minio()
    key = source["keys"][1]
    _put(client, source["bucket"], key, "tampered\n")
    try:
        with pytest.raises(bk.BackupError, match="source_hash"):
            bk.create_backup(_cfg(SRC_DB, source["bucket"], tmp_path))
        assert os.listdir(tmp_path) == []
    finally:
        _put(client, source["bucket"], key, CODES[1])


def test_dump_and_key_list_share_one_snapshot(source, tmp_path, monkeypatch):
    """D3: a snapshot row committed while the backup runs is in neither the key list nor the dump."""
    real = bk._run_pg_tool
    late = {}

    def insert_then_dump(cfg, args, **kw):
        if args[0] == "pg_dump":
            with Session(source["engine"]) as s:
                late["key"] = _add_snapshot(s, source["session_id"], "committed during backup\n")
                s.commit()                               # its blob is never uploaded
        return real(cfg, args, **kw)

    monkeypatch.setattr(bk, "_run_pg_tool", insert_then_dump)
    try:
        path = bk.create_backup(_cfg(SRC_DB, source["bucket"], tmp_path))   # does not fail on the late key
        m = bk.load_manifest(path)
        assert late["key"] not in {b["key"] for b in m["blobs"]}
        assert m["row_counts"]["code_snapshots"] == 4
    finally:
        with source["engine"].begin() as c:
            c.execute(text("DELETE FROM code_snapshots WHERE object_key = :k"), {"k": late["key"]})


def test_verify_set_detects_corruption(source, tmp_path):
    """AC-18-03"""
    path = bk.create_backup(_cfg(SRC_DB, source["bucket"], tmp_path / "sets"))
    dump_copy, blob_copy = tmp_path / "dump", tmp_path / "blob"
    shutil.copytree(path, dump_copy)
    shutil.copytree(path, blob_copy)

    with open(dump_copy / "db.dump", "r+b") as f:
        f.seek(100)
        byte = f.read(1)
        f.seek(100)
        f.write(bytes([byte[0] ^ 0xFF]))
    assert bk.verify_set(str(dump_copy)) == ["db.dump checksum mismatch"]

    key = source["keys"][2]
    (blob_copy / "blobs" / key).write_text("changed\n")
    assert bk.verify_set(str(blob_copy)) == [f"blob checksum mismatch: {key}"]
    (blob_copy / "blobs" / key).unlink()
    assert bk.verify_set(str(blob_copy)) == [f"blob missing: {key}"]
    assert bk.verify_set(str(tmp_path / "nowhere"))[0].startswith("Unreadable manifest")


def test_restore_round_trip(source, target, tmp_path):
    """AC-18-04: revision, every row count and every key match; restored blobs are readable."""
    path = bk.create_backup(_cfg(SRC_DB, source["bucket"], tmp_path))
    db, bucket = target
    cfg = _cfg(db, bucket, tmp_path)
    m = bk.restore(cfg, path)
    assert bk.verify_restored(cfg, m) == []
    assert bk.verify_live(cfg) == []
    eng = create_engine(_url(db))
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM code_snapshots")).scalar() == 4
        assert c.execute(text("SELECT username FROM users ORDER BY username")).scalars().all() == ["p18_student", "p18_teacher"]
    eng.dispose()
    restored = {o.object_name for o in _minio().list_objects(bucket, recursive=True)}
    assert restored == set(source["keys"])                 # the orphan was not carried over


def test_restore_refuses_non_empty_targets(source, target, tmp_path):
    path = bk.create_backup(_cfg(SRC_DB, source["bucket"], tmp_path))
    db, bucket = target
    # Non-empty database: the source itself
    with pytest.raises(bk.BackupError, match="not empty"):
        bk.restore(_cfg(SRC_DB, bucket, tmp_path), path)
    # Empty database, non-empty bucket
    with pytest.raises(bk.BackupError, match="bucket"):
        bk.restore(_cfg(db, source["bucket"], tmp_path), path)
    eng = create_engine(_url(db))
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar() == 0
    eng.dispose()


def test_restore_refuses_corrupted_set(source, target, tmp_path):
    path = bk.create_backup(_cfg(SRC_DB, source["bucket"], tmp_path))
    (Path(path) / "blobs" / source["keys"][0]).write_text("changed\n")
    db, bucket = target
    with pytest.raises(bk.BackupError, match="nothing restored"):
        bk.restore(_cfg(db, bucket, tmp_path), path)
    assert not _minio().bucket_exists(bucket)


def test_verify_live_reports_missing_and_changed_blobs(source, tmp_path):
    client = _minio()
    cfg = _cfg(SRC_DB, source["bucket"], tmp_path)
    assert bk.verify_live(cfg) == []
    gone, changed = source["keys"][1], source["keys"][2]
    client.remove_object(source["bucket"], gone)
    _put(client, source["bucket"], changed, "changed\n")
    try:
        problems = bk.verify_live(cfg)
        assert any(gone in p and p.startswith("unreadable") for p in problems)
        assert f"content mismatch: {changed}" in problems
    finally:
        _put(client, source["bucket"], gone, CODES[1])
        _put(client, source["bucket"], changed, CODES[2])


def test_prune_keeps_newest_and_partial_sets_are_removed(source, tmp_path):
    """D5: keep the newest N; a crashed run's .partial directory is cleaned up by the next run."""
    for name in ["spnc-20261001T190000Z", "spnc-20261002T190000Z", "spnc-20261003T190000Z", "notes"]:
        (tmp_path / name).mkdir()
    (tmp_path / "spnc-20261004T190000Z.partial").mkdir()
    cfg = _cfg(SRC_DB, source["bucket"], tmp_path, keep=2)
    path = bk.create_backup(cfg, now=datetime(2026, 10, 5, 19, 0, tzinfo=timezone.utc))
    assert os.path.basename(path) == "spnc-20261005T190000Z"
    assert not (tmp_path / "spnc-20261004T190000Z.partial").exists()
    assert bk.prune(cfg) == ["spnc-20261001T190000Z", "spnc-20261002T190000Z"]
    assert bk.list_sets(str(tmp_path)) == ["spnc-20261003T190000Z", "spnc-20261005T190000Z"]
    assert (tmp_path / "notes").exists()                   # unrelated directories are never touched


def test_scheduled_backup_writes_status(source, tmp_path):
    cfg = _cfg(SRC_DB, source["bucket"], tmp_path)
    assert bk.run_scheduled_backup(cfg) is True
    status = json.loads((tmp_path / "last-backup.json").read_text())
    assert status["status"] == "ok" and status["set"] in bk.list_sets(str(tmp_path))

    broken = _cfg(SRC_DB, f"spnc-p18-none-{uuid.uuid4().hex[:8]}", tmp_path)   # bucket has none of the blobs
    assert bk.run_scheduled_backup(broken) is False
    status = json.loads((tmp_path / "last-backup.json").read_text())
    assert status["status"] == "failed" and "missing" in status["error"]


def test_next_run():
    now = datetime(2026, 10, 29, 18, 30, tzinfo=timezone.utc)
    assert bk.next_run(now, "19:00") == datetime(2026, 10, 29, 19, 0, tzinfo=timezone.utc)
    assert bk.next_run(now, "18:30") == datetime(2026, 10, 30, 18, 30, tzinfo=timezone.utc)
    assert bk.next_run(now + timedelta(hours=1), "19:00") == datetime(2026, 10, 30, 19, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("key", ["../etc/passwd", "/abs/key", "snapshots//x", "snapshots/../../x", "a\\b", ""])
def test_unsafe_keys_are_refused(tmp_path, key):
    with pytest.raises(bk.BackupError, match="Unsafe"):
        bk._safe_blob_path(str(tmp_path), key)
