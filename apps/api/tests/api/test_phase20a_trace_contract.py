"""Phase 20A — the web client's trace payloads against the real ingest endpoint (docs/46 AC-20A-09).

The batch comes from apps/web/src/trace/contract-fixtures.json, which a Vitest test keeps equal to
what the client's payload builders produce. No application code is involved beyond the API.
Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test).
"""
import json
import uuid
from pathlib import Path

from sqlalchemy import select

from app.models.session import CodingSession
from app.models.trace import TraceEvent
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _practice_session, client,
    clean_db, db, enqueued, setup_database, world,
)

FIXTURE = Path(__file__).resolve().parents[3] / "web" / "src" / "trace" / "contract-fixtures.json"


def _snap(h, sid, reason):
    r = client.post(f"/api/v1/my/coding-sessions/{sid}/snapshots",
                    json={"reason": reason, "language": "PYTHON3", "source_code": "print(42)\n", "line_count": 1}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _batch(w, sid):
    text = FIXTURE.read_text(encoding="utf-8")
    for placeholder, value in {
        "{{PROBLEM_ID}}": str(w["pid"]),
        "{{CHECKPOINT_SNAPSHOT_ID}}": _snap(w["h_s"], sid, "CHECKPOINT"),
        "{{RUN_SNAPSHOT_ID}}": _snap(w["h_s"], sid, "RUN"),
        "{{RUN_ID}}": str(uuid.uuid4()),
    }.items():
        text = text.replace(placeholder, value)
    assert "{{" not in text
    return json.loads(text)


def test_client_batch_is_accepted_and_a_resend_is_a_duplicate(db, world):
    w = world
    sid = _practice_session(w)
    batch = _batch(w, sid)
    n = len(batch["events"])
    assert {e["event_type"] for e in batch["events"]} == {
        "PROBLEM_OPENED", "EDITOR_CHANGED", "SESSION_CHECKPOINT", "RUN_REQUESTED", "RUN_COMPLETED"}

    url = f"/api/v1/my/coding-sessions/{sid}/trace-events/batch"
    r = client.post(url, json=batch, headers=w["h_s"])
    assert r.status_code == 200, r.text
    assert r.json()["accepted_count"] == n
    assert r.json()["state"] == {"highest_contiguous_sequence": n, "next_expected_sequence": n + 1,
                                 "checkpoint_interval_seconds": 60}

    # The client's retry after a lost response: identical batch, nothing new stored
    r = client.post(url, json=batch, headers=w["h_s"])
    assert r.status_code == 200, r.text
    assert r.json()["accepted_count"] == 0

    stored = db.scalars(select(TraceEvent).where(TraceEvent.session_id == uuid.UUID(sid))
                        .order_by(TraceEvent.sequence_number)).all()
    assert [e.sequence_number for e in stored] == list(range(1, n + 1))
    assert [e.payload for e in stored] == [e["payload"] for e in batch["events"]]
    db.expire_all()
    assert db.get(CodingSession, uuid.UUID(sid)).first_code_at is not None   # REQ-TRACE-002


def test_changed_payload_under_a_sent_sequence_is_a_conflict(db, world):
    w = world
    sid = _practice_session(w)
    batch = _batch(w, sid)
    url = f"/api/v1/my/coding-sessions/{sid}/trace-events/batch"
    assert client.post(url, json=batch, headers=w["h_s"]).status_code == 200
    batch["events"][1]["payload"]["text"] = "changed"
    r = client.post(url, json=batch, headers=w["h_s"])
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "TRACE_SEQUENCE_CONFLICT" and r.json()["request_id"]
