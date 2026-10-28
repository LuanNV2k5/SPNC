"""Snapshot content storage (ADR-007; docs/37 Phase 11).

PostgreSQL keeps metadata only; content lives in object storage. Upload-first: callers write
the blob before the metadata row. Blobs are immutable.

Backends (docs/37 D2): "memory" keeps content in a per-process dict (tests and local dev);
"s3" uses MinIO/S3 so the API, workers and schedulers share content across processes.
"""
import hashlib
import io
import logging
from typing import Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageUnavailable(Exception):
    """Object storage could not be reached or the object is missing (callers never fall back to empty code)."""


class StorageConflict(Exception):
    """A different blob already exists under the same key (immutability, docs/37 §3.1)."""


class StorageAdapter:
    def __init__(self, bucket_name: Optional[str] = None, backend: Optional[str] = None):
        self.backend = (backend or settings.STORAGE_BACKEND).lower()
        self.bucket_name = bucket_name or settings.S3_BUCKET
        self._memory_store = {}
        self._client = None
        self._bucket_ready = False

    # -- S3 plumbing -----------------------------------------------------------
    def _s3(self):
        if self._client is None:
            import urllib3
            from minio import Minio
            # Bounded timeouts/retries: an outage must surface as 503 quickly, not hang requests
            http = urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=settings.S3_CONNECT_TIMEOUT_SECONDS, read=settings.S3_READ_TIMEOUT_SECONDS),
                retries=urllib3.Retry(total=settings.S3_MAX_RETRIES, backoff_factor=0.2,
                                      status_forcelist=[500, 502, 503, 504]),
            )
            self._client = Minio(
                settings.S3_ENDPOINT,
                access_key=settings.S3_ACCESS_KEY,
                secret_key=settings.S3_SECRET_KEY,
                secure=settings.S3_SECURE,
                region=settings.S3_REGION,
                http_client=http,
            )
        if not self._bucket_ready:
            try:
                if not self._client.bucket_exists(self.bucket_name):
                    self._client.make_bucket(self.bucket_name)
            except Exception as e:
                # Another process may have created it concurrently; anything else is an outage
                if getattr(e, "code", None) not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    raise StorageUnavailable(f"Bucket unavailable: {e}") from e
            self._bucket_ready = True
        return self._client

    @staticmethod
    def _is_missing(err: Exception) -> bool:
        return getattr(err, "code", None) in ("NoSuchKey", "NoSuchObject", "ResourceNotFound")

    def _s3_read(self, object_key: str) -> str:
        response = None
        try:
            response = self._s3().get_object(self.bucket_name, object_key)
            return response.read().decode("utf-8")
        except StorageUnavailable:
            raise
        except Exception as e:
            raise StorageUnavailable(f"Cannot read {object_key}: {e}") from e
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    # -- Public API (unchanged since Phase 06) -----------------------------------
    def upload_code_snapshot(self, session_id: str, sequence: int, content: str) -> Tuple[str, str]:
        """Stores content and returns (source_hash, object_key)."""
        source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        # Key format is persisted in code_snapshots.object_key; unchanged (docs/37 F6)
        object_key = f"snapshots/{session_id}/{sequence}_{source_hash[:8]}.txt"

        if self.backend != "s3":
            existing = self._memory_store.get(object_key)
            if existing is not None and existing != content:
                raise StorageConflict(object_key)
            self._memory_store[object_key] = content
            return source_hash, object_key

        if self.exists_code_snapshot(object_key):
            # Identical re-upload is a no-op; a different blob is never overwritten
            if hashlib.sha256(self._s3_read(object_key).encode("utf-8")).hexdigest() != source_hash:
                raise StorageConflict(object_key)
            return source_hash, object_key
        data = content.encode("utf-8")
        try:
            self._s3().put_object(self.bucket_name, object_key, io.BytesIO(data), len(data),
                                  content_type="text/plain; charset=utf-8", metadata={"sha256": source_hash})
        except StorageUnavailable:
            raise
        except Exception as e:
            raise StorageUnavailable(f"Cannot store {object_key}: {e}") from e
        return source_hash, object_key

    def download_code_snapshot(self, object_key: str) -> str:
        """Returns content. Memory backend keeps its Phase 06 behaviour ("" when absent);
        callers check exists_code_snapshot first. S3 raises StorageUnavailable when absent."""
        if self.backend != "s3":
            return self._memory_store.get(object_key, "")
        return self._s3_read(object_key)

    def exists_code_snapshot(self, object_key: str) -> bool:
        """True when content is retrievable. Raises StorageUnavailable when storage cannot answer."""
        if self.backend != "s3":
            return object_key in self._memory_store
        try:
            self._s3().stat_object(self.bucket_name, object_key)
            return True
        except StorageUnavailable:
            raise
        except Exception as e:
            if self._is_missing(e):
                return False
            raise StorageUnavailable(f"Cannot stat {object_key}: {e}") from e


# Singleton instance for injection/usage
storage_adapter = StorageAdapter()
