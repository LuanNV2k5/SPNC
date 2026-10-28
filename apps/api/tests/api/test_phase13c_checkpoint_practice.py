"""Phase 13C — Checkpoint linkage and the student practice list (docs/39 D4-D6; AC-13-04, AC-13-05).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.trace import TraceEvent
from tests.api.test_exam_lifecycle import _class_with
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _auth, _make_user, _practice_session, client,
    clean_db, db, enqueued, setup_database, world,
)


def _snap(h, sid, reason, code="x = 1\n"):
    r = client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots",
                    json={"reason": reason, "language": "PYTHON3", "source_code": code, "line_count": 1}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _checkpoint(h, sid, seq, snapshot_id):
    return client.post(f"/api/v1/my/coding-sessions/{sid}/trace-events/batch", json={"events": [{
        "sequence_number": seq, "event_type": "SESSION_CHECKPOINT", "client_timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"code_snapshot_id": snapshot_id, "trigger_reason": "CHECKPOINT"}}]}, headers=h)


# ---------------------------------------------------------------------------
# AC-13-04 — checkpoints
# ---------------------------------------------------------------------------
def test_checkpoint_must_reference_own_checkpoint_snapshot(db, world):
    w = world
    sid = _practice_session(w)
    other = _practice_session(w)
    good = _snap(w["h_s"], sid, "CHECKPOINT")
    run_snap = _snap(w["h_s"], sid, "RUN", "y = 2\n")
    foreign = _snap(w["h_s"], other, "CHECKPOINT")

    for bad in (run_snap, foreign, str(uuid.uuid4()), "not-a-uuid", None):
        r = _checkpoint(w["h_s"], sid, 1, bad)
        assert r.status_code == 422, (bad, r.text)
        assert r.json()["error_code"] == "CHECKPOINT_SNAPSHOT_INVALID"
    assert db.scalars(select(TraceEvent).where(TraceEvent.session_id == uuid.UUID(sid))).all() == []

    r = _checkpoint(w["h_s"], sid, 1, good)
    assert r.status_code == 200, r.text
    stored = db.scalar(select(TraceEvent).where(TraceEvent.session_id == uuid.UUID(sid)))
    assert stored.event_type == "SESSION_CHECKPOINT" and stored.payload["code_snapshot_id"] == good


def test_trace_state_advertises_checkpoint_interval(world):
    w = world
    sid = _practice_session(w)
    body = client.get(f"/api/v1/my/coding-sessions/{sid}/trace-state", headers=w["h_s"]).json()
    assert body["checkpoint_interval_seconds"] == 60


# ---------------------------------------------------------------------------
# AC-13-05 — practice list
# ---------------------------------------------------------------------------
def _problem(h, title, visibility, **extra):
    r = client.post("/api/v1/problems", json={"title": title, "description": "d", "visibility": visibility,
                                              "supported_languages": extra.pop("langs", ["PYTHON3"]), **extra}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _titles(h, query=""):
    r = client.get(f"/api/v1/my/practice/problems{query}", headers=h)
    assert r.status_code == 200, r.text
    return sorted(i["title"] for i in r.json()["items"]), r.json()["total"]


def test_practice_list_scope_and_filters(db, world):
    w = world
    mine = _class_with(w, w["student_id"])
    other_class = _class_with(w)                     # stu is not a member
    removed_class = _class_with(w, w["student_id"])

    class_mine = _problem(w["h_t"], "class-mine", "CLASS", difficulty="HARD")
    class_other = _problem(w["h_t"], "class-other", "CLASS")
    class_removed = _problem(w["h_t"], "class-removed", "CLASS")
    _problem(w["h_t"], "private", "PRIVATE")
    deleted = _problem(w["h_t"], "public-deleted", "PUBLIC")
    _problem(w["h_t"], "public-cpp", "PUBLIC", langs=["CPP17"], difficulty="EASY")
    for pid, cid in ((class_mine, mine), (class_other, other_class), (class_removed, removed_class)):
        assert client.post(f"/api/v1/problems/{pid}/publish", json={"class_id": cid}, headers=w["h_t"]).status_code == 201
    assert client.post(f"/api/v1/problems/{class_mine}/publish", json={"class_id": removed_class}, headers=w["h_t"]).status_code == 201
    client.delete(f"/api/v1/classes/{removed_class}/members/{w['student_id']}", headers=w["h_t"])
    assert client.delete(f"/api/v1/problems/{deleted}", headers=w["h_t"]).status_code == 204

    # world() owns "Sum" (PUBLIC, PYTHON3). class-mine is published to two classes: listed once.
    assert _titles(w["h_s"]) == (["Sum", "class-mine", "public-cpp"], 3)
    assert _titles(w["h_s"], "?difficulty=HARD") == (["class-mine"], 1)
    assert _titles(w["h_s"], "?language=CPP17") == (["public-cpp"], 1)
    assert client.get("/api/v1/my/practice/problems?difficulty=X", headers=w["h_s"]).status_code == 422
    assert client.get("/api/v1/my/practice/problems", headers=w["h_t"]).status_code == 403

    # A student in no class sees PUBLIC only
    assert _titles(w["h_s2"]) == (["Sum", "public-cpp"], 2)
