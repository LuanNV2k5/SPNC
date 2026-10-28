"""Phase 13B — Admin system settings (REQ-USER-007, docs/39 13B).

`idle_threshold_minutes` (1-60) is read when a session is created and stored on it (D3),
so a change applies to new sessions only.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import AuditLog, SystemSetting, User

RETENTION_KEY = "retention_days"
IDLE_KEY = "idle_threshold"


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def _get(db: Session, key: str) -> Optional[SystemSetting]:
    return db.query(SystemSetting).filter(SystemSetting.key == key).first()


def idle_threshold_minutes(db: Session) -> int:
    s = _get(db, IDLE_KEY)
    if s and isinstance(s.value, dict) and s.value.get("minutes"):
        return int(s.value["minutes"])
    return max(1, settings.SIGNAL_IDLE_THRESHOLD_SECONDS // 60)


def idle_threshold_seconds(db: Session) -> int:
    return idle_threshold_minutes(db) * 60


def read_settings(db: Session) -> dict:
    retention = _get(db, RETENTION_KEY)
    return {
        "retention_days": retention.value.get("days", 30) if retention else 30,
        "idle_threshold_minutes": idle_threshold_minutes(db),
    }


def update_settings(db: Session, admin: User, retention_days: Optional[int], idle_minutes: Optional[int]) -> dict:
    if retention_days is None and idle_minutes is None:
        raise HTTPException(status_code=422, detail=_error("INVALID_SETTING", "No setting to change"))
    if retention_days is not None:
        if retention_days < 1 or retention_days > 3650:
            raise HTTPException(status_code=422, detail=_error("INVALID_SETTING", "Invalid retention days"))
        s = _get(db, RETENTION_KEY)
        if not s:
            db.add(SystemSetting(key=RETENTION_KEY, value={"days": retention_days}))
        else:
            s.value = {"days": retention_days}
        # Phase 04 audit action kept for retention
        db.add(AuditLog(actor_id=admin.id, action="SYSTEM_SETTING_CHANGED", target_type="SETTING", target_id=RETENTION_KEY))
    if idle_minutes is not None:
        if idle_minutes < 1 or idle_minutes > 60:
            raise HTTPException(status_code=422, detail=_error("INVALID_SETTING", "idle_threshold_minutes must be between 1 and 60"))
        old = idle_threshold_minutes(db)
        s = _get(db, IDLE_KEY)
        if not s:
            db.add(SystemSetting(key=IDLE_KEY, value={"minutes": idle_minutes},
                                 description="IDLE_DETECTED threshold for new sessions (REQ-USER-007)"))
        else:
            s.value = {"minutes": idle_minutes}
        db.add(AuditLog(actor_id=admin.id, action="CONFIG_CHANGED", target_type="SETTING", target_id=IDLE_KEY,
                        metadata_payload={"key": "idle_threshold_minutes", "old": old, "new": idle_minutes}))
    db.flush()
    return read_settings(db)
