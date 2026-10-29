"""Phase 13B — Admin-configurable idle threshold for new sessions (REQ-USER-007; docs/39 D3; AC-13-03).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test).
"""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.core.config import settings
from app.models.session import CodingSession
from app.models.user import AuditLog
from app.services.judge.signals import evaluate_idle_detected
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _auth, _make_user, _practice_session, client,
    clean_db, db, enqueued, setup_database, world,
)

DEFAULT_MIN = settings.SIGNAL_IDLE_THRESHOLD_SECONDS // 60


@pytest.fixture(autouse=True)
def reset_settings():
    """system_settings is not reached by the users TRUNCATE CASCADE."""
    with TestingSessionLocal() as s:
        s.execute(text("DELETE FROM system_settings"))
        s.commit()
    yield


def _admin(db):
    _make_user(db, "admin", "ADMIN")
    return _auth("admin")


def test_admin_reads_and_changes_threshold_with_audit(db, world):
    h = _admin(db)
    assert client.get("/api/v1/admin/settings", headers=h).json()["idle_threshold_minutes"] == DEFAULT_MIN

    r = client.patch("/api/v1/admin/settings", json={"idle_threshold_minutes": 10}, headers=h)
    assert r.status_code == 200 and r.json()["idle_threshold_minutes"] == 10
    assert client.get("/api/v1/admin/settings", headers=h).json() == {"retention_days": 180, "idle_threshold_minutes": 10}

    log = db.scalar(select(AuditLog).where(AuditLog.action == "CONFIG_CHANGED"))
    assert log.metadata_payload == {"key": "idle_threshold_minutes", "old": DEFAULT_MIN, "new": 10}

    for bad in (0, 61):
        r = client.patch("/api/v1/admin/settings", json={"idle_threshold_minutes": bad}, headers=h)
        assert r.status_code == 422 and r.json()["error_code"] == "INVALID_SETTING"
    assert client.patch("/api/v1/admin/settings", json={}, headers=h).status_code == 422
    assert client.patch("/api/v1/admin/settings", json={"idle_threshold_minutes": 5}, headers=world["h_t"]).status_code == 403
    # Phase 04 retention setting still works on its own
    assert client.patch("/api/v1/admin/settings", json={"retention_days": 45}, headers=h).json()["retention_days"] == 45


def test_change_applies_to_new_sessions_only(db, world):
    w = world
    h = _admin(db)
    before = _practice_session(w)
    assert client.patch("/api/v1/admin/settings", json={"idle_threshold_minutes": 10}, headers=h).status_code == 200
    after = _practice_session(w)

    db.expire_all()
    old_s, new_s = db.get(CodingSession, uuid.UUID(before)), db.get(CodingSession, uuid.UUID(after))
    assert old_s.idle_threshold_seconds == DEFAULT_MIN * 60
    assert new_s.idle_threshold_seconds == 600

    # Same idle gap (7 min): old session signals with its 5-min threshold, new one does not yet
    for s, expect in ((old_s, True), (new_s, False)):
        sig = evaluate_idle_detected(s, db, evaluated_at=s.opened_at + timedelta(minutes=7))
        assert (sig is not None) is expect
    sig = evaluate_idle_detected(new_s, db, evaluated_at=new_s.opened_at + timedelta(minutes=11))
    assert sig is not None and sig.evidence["threshold_used"] == 600


def test_pre_phase13_sessions_keep_deployment_default(db, world):
    w = world
    sid = _practice_session(w)
    s = db.get(CodingSession, uuid.UUID(sid))
    s.idle_threshold_seconds = None          # a session created before this phase
    db.commit()
    sig = evaluate_idle_detected(s, db, evaluated_at=s.opened_at + timedelta(seconds=settings.SIGNAL_IDLE_THRESHOLD_SECONDS + 1))
    assert sig is not None and sig.evidence["threshold_used"] == settings.SIGNAL_IDLE_THRESHOLD_SECONDS
