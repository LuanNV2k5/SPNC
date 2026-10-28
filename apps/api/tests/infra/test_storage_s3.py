"""Phase 11 — S3/MinIO storage backend (docs/37 §3.1; AC-11-01, AC-11-02 storage side).

Needs a real MinIO. Defaults match the disposable test container:
    docker run -d --name spnc-minio-test -p 127.0.0.1:19000:9000 \
        -e MINIO_ROOT_USER=spnc-test -e MINIO_ROOT_PASSWORD=spnc-test-password \
        --tmpfs /data:uid=65532,gid=65532 cgr.dev/chainguard/minio@sha256:... server /data
No database is used.
"""
import hashlib
import io
import os
import uuid

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost:5432/unused")

from app.core.config import settings
from app.services.storage import StorageAdapter, StorageConflict, StorageUnavailable

S3_ENDPOINT = os.environ.get("PHASE11_S3_ENDPOINT", "127.0.0.1:19000")
S3_ACCESS = os.environ.get("PHASE11_S3_ACCESS_KEY", "spnc-test")
S3_SECRET = os.environ.get("PHASE11_S3_SECRET_KEY", "spnc-test-password")


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setattr(settings, "S3_ENDPOINT", S3_ENDPOINT)
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", S3_ACCESS)
    monkeypatch.setattr(settings, "S3_SECRET_KEY", S3_SECRET)
    monkeypatch.setattr(settings, "S3_SECURE", False)
    # A fresh bucket per test: also proves the bucket is created on first use
    return StorageAdapter(bucket_name=f"spnc-test-{uuid.uuid4().hex[:12]}", backend="s3")


def test_round_trip_and_bucket_created_on_first_use(s3):
    code = "print('xin chao')\n"
    source_hash, key = s3.upload_code_snapshot("sess-1", 0, code)
    assert source_hash == hashlib.sha256(code.encode()).hexdigest()
    assert key == f"snapshots/sess-1/0_{source_hash[:8]}.txt"   # persisted key format unchanged (F6)
    assert s3.exists_code_snapshot(key) is True
    assert s3.download_code_snapshot(key) == code

    # A second adapter instance (another process in production) sees the same blob
    other = StorageAdapter(bucket_name=s3.bucket_name, backend="s3")
    assert other.download_code_snapshot(key) == code


def test_identical_reupload_is_noop(s3):
    _, key = s3.upload_code_snapshot("sess-2", 0, "a = 1\n")
    stat_before = s3._s3().stat_object(s3.bucket_name, key)
    assert s3.upload_code_snapshot("sess-2", 0, "a = 1\n")[1] == key
    stat_after = s3._s3().stat_object(s3.bucket_name, key)
    assert stat_after.etag == stat_before.etag and stat_after.last_modified == stat_before.last_modified


def test_different_content_under_existing_key_is_refused(s3):
    code = "b = 2\n"
    source_hash, key = s3.upload_code_snapshot("sess-3", 0, code)
    # Simulate a foreign blob already sitting at the key (prefix collision / tampering)
    tampered = b"something else\n"
    s3._s3().put_object(s3.bucket_name, key, io.BytesIO(tampered), len(tampered))
    with pytest.raises(StorageConflict):
        s3.upload_code_snapshot("sess-3", 0, code)
    assert s3.download_code_snapshot(key) == tampered.decode()   # never overwritten


def test_missing_object(s3):
    s3.upload_code_snapshot("sess-4", 0, "x\n")   # bucket exists
    assert s3.exists_code_snapshot("snapshots/none/0_deadbeef.txt") is False
    with pytest.raises(StorageUnavailable):
        s3.download_code_snapshot("snapshots/none/0_deadbeef.txt")   # never "" (no fabricated code)


def test_unreachable_storage_raises_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "S3_ENDPOINT", "127.0.0.1:1")   # nothing listens here
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "x")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "y")
    adapter = StorageAdapter(bucket_name="spnc-unreachable", backend="s3")
    adapter_client = adapter._client
    assert adapter_client is None
    with pytest.raises(StorageUnavailable):
        adapter.upload_code_snapshot("s", 0, "x\n")
    with pytest.raises(StorageUnavailable):
        adapter.exists_code_snapshot("snapshots/s/0_x.txt")
    with pytest.raises(StorageUnavailable):
        adapter.download_code_snapshot("snapshots/s/0_x.txt")


def test_memory_backend_unchanged_and_immutable():
    mem = StorageAdapter(backend="memory")
    _, key = mem.upload_code_snapshot("m", 0, "y\n")
    assert mem.exists_code_snapshot(key) and mem.download_code_snapshot(key) == "y\n"
    assert mem.download_code_snapshot("absent") == ""          # Phase 06 behaviour kept for callers that check exists first
    mem._memory_store[key] = "other\n"
    with pytest.raises(StorageConflict):
        mem.upload_code_snapshot("m", 0, "y\n")
