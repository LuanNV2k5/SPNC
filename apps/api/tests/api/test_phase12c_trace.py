"""Phase 12C — Run record in the timeline, first-code fact, reserved types (docs/38 D9-D11; AC-12-09).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.run_submit import RunStatus
from app.models.session import CodingSession
from app.models.trace import TraceEvent
from app.repositories.run import run_repository
from tests.api.test_exam_lifecycle import _class_with
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _practice_session, _snapshot, client,
    clean_db, db, enqueued, setup_database, world,
)


def _batch(h, sid, items):
    events = [{"sequence_number": n, "event_type": t, "client_timestamp": datetime.now(timezone.utc).isoformat(), "payload": {"n": n}}
              for n, t in items]
    return client.post(f"/api/v1/my/coding-sessions/{sid}/trace-events/batch", json={"events": events}, headers=h)


def _first_code(db, sid):
    db.expire_all()
    return db.get(CodingSession, uuid.UUID(sid)).first_code_at


def test_first_code_at_set_once_at_first_editor_change(db, world):
    w = world
    sid = _practice_session(w)
    assert _batch(w["h_s"], sid, [(1, "PROBLEM_OPENED")]).status_code == 200
    assert _first_code(db, sid) is None

    before = datetime.now(timezone.utc)
    assert _batch(w["h_s"], sid, [(2, "EDITOR_CHANGED"), (3, "EDITOR_CHANGED")]).status_code == 200
    first = _first_code(db, sid)
    assert first is not None and first >= before          # server clock, not client timestamps

    assert _batch(w["h_s"], sid, [(4, "EDITOR_CHANGED")]).status_code == 200
    assert _batch(w["h_s"], sid, [(2, "EDITOR_CHANGED"), (3, "EDITOR_CHANGED")]).status_code == 200   # retry
    assert _first_code(db, sid) == first                  # once per session

    body = client.get(f"/api/v1/my/practice/sessions/{sid}", headers=w["h_s"]).json()
    assert body["first_code_at"] is not None


def test_submission_created_and_session_ended_are_reserved(db, world):
    w = world
    sid = _practice_session(w)
    for reserved in ("SUBMISSION_CREATED", "SESSION_ENDED"):
        r = _batch(w["h_s"], sid, [(1, "EDITOR_CHANGED"), (2, reserved)])
        assert r.status_code == 422 and r.json()["error_code"] == "TRACE_EVENT_TYPE_RESERVED" and reserved in r.json()["message"]
    assert db.scalars(select(TraceEvent).where(TraceEvent.session_id == uuid.UUID(sid))).all() == []   # whole batch refused


def test_teacher_timeline_lists_runs_and_first_code(db, world):
    w = world
    cid = _class_with(w, w["student_id"])
    sid = _practice_session(w)                             # problem owned by the teacher -> visible in the class
    _batch(w["h_s"], sid, [(1, "EDITOR_CHANGED")])
    snap = _snapshot(w["h_s"], sid, "print(42)\n")
    with TestingSessionLocal() as s:
        run = run_repository.create(s, session_id=uuid.UUID(sid), snapshot_id=uuid.UUID(snap), input_data="7\n")
        claimed = run_repository.claim_run_for_execution(s, run.id)
        run_repository.write_result(s, run.id, claimed.execution_generation, status=RunStatus.COMPLETED, verdict="ACCEPTED",
                                    time_ms=37, memory_kb=0,
                                    testcase_results={"input": "7\n", "stdout": "42\n", "stderr": "", "compile_error_message": None,
                                                      "runtime_error_message": None})

    r = client.get(f"/api/v1/classes/{cid}/students/{w['student_id']}/sessions/{sid}/timeline", headers=w["h_t"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session"]["first_code_at"] is not None
    assert len(body["runs"]) == 1
    run_row = body["runs"][0]
    # REQ-TRACE-011 fields: snapshot, input, output, result, error, execution time
    assert run_row["snapshot_id"] == snap and run_row["verdict"] == "ACCEPTED" and run_row["execution_time_ms"] == 37
    assert run_row["testcase_results"]["input"] == "7\n" and run_row["testcase_results"]["stdout"] == "42\n"
    assert "runtime_error_message" in run_row["testcase_results"]
