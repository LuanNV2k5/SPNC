"""Phase 13A — Orphan snapshot blob cleanup (ADR-007, docs/39 D2).

Upload-first means a blob can exist without a metadata row when the insert fails. After a
grace period such blobs are deleted. A blob referenced by any code_snapshots row is never
touched (rows may share a blob, docs/39 D1).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import settings
from app.models.trace import CodeSnapshot
from app.services.storage import StorageUnavailable, storage_adapter

logger = logging.getLogger(__name__)


def sweep_orphans(db: Session, now: Optional[datetime] = None, storage=storage_adapter) -> Dict[str, int]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=settings.SNAPSHOT_ORPHAN_GRACE_HOURS)
    result = {"scanned": 0, "deleted": 0, "errors": 0}
    try:
        candidates = storage.list_code_snapshots(older_than=cutoff, limit=settings.SNAPSHOT_ORPHAN_BATCH_SIZE)
    except StorageUnavailable as e:
        logger.warning(f"Orphan sweep skipped: {e}")
        metrics.ORPHAN_CLEANUP_FAILURES.inc()
        result["errors"] += 1
        return result
    result["scanned"] = len(candidates)
    if not candidates:
        return result
    referenced = set(db.scalars(select(CodeSnapshot.object_key).where(CodeSnapshot.object_key.in_(candidates))).all())
    for key in candidates:
        if key in referenced:
            continue
        metrics.ORPHANS_DETECTED.inc()
        try:
            storage.delete_code_snapshot(key)
            result["deleted"] += 1
            metrics.ORPHANS_CLEANED.inc()
        except StorageUnavailable as e:
            logger.warning(f"Orphan delete failed for {key}: {e}")
            metrics.ORPHAN_CLEANUP_FAILURES.inc()
            result["errors"] += 1
    if result["deleted"] or result["errors"]:
        logger.info(f"Orphan sweep: {result}")
    return result
