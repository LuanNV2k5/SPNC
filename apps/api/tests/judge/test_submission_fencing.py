"""Phase 10A — Submission judge fencing (docs/36 AC-10-04, invariant 5).

Reuses the Phase 10 submission fixtures (same guarded database
spnc_phase10_submission_test) and drives the judge in-process.
"""
import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import worker
from app.models.run_submit import RunStatus, RunVerdict, Submission
from app.repositories import submission as submission_repo
from app.services import submission as submission_svc
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    FakeAdapter, TestingSessionLocal, _practice_session, _snapshot, _submit,
    clean_db, db, enqueued, setup_database, world,
)


def _pending_submission(w) -> uuid.UUID:
    sid = _practice_session(w)
    r = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n"))
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


def _age(sub_id: uuid.UUID, seconds: int = 3600):
    with TestingSessionLocal() as s:
        s.execute(text("UPDATE submissions SET updated_at = :t WHERE id = :id"),
                  {"t": datetime.now(timezone.utc) - timedelta(seconds=seconds), "id": sub_id})
        s.commit()


def test_stale_generation_cannot_write_result(world):
    sub_id = _pending_submission(world)
    with TestingSessionLocal() as s:
        claimed = submission_repo.claim_for_judging(s, sub_id)
        old_gen = claimed.execution_generation
        assert claimed.status == RunStatus.RUNNING.value and old_gen == 1

        recovered = submission_repo.recover_stale(s, sub_id, old_gen)
        assert recovered.status == RunStatus.PENDING.value and recovered.execution_generation == old_gen + 1

        assert submission_repo.write_result(s, sub_id, old_gen, RunStatus.COMPLETED, RunVerdict.ACCEPTED.value, 100, {}) is False
        s.commit()
        s.expire_all()
        sub = s.get(Submission, sub_id)
        assert sub.status == RunStatus.PENDING.value and sub.verdict is None and sub.score is None


def test_judge_drops_result_when_recovered_mid_run(world):
    """The reconciler takes the job while the sandbox is running; the late result is discarded."""
    sub_id = _pending_submission(world)

    class RecoveringAdapter(FakeAdapter):
        def execute(self, source_code, input_data, memory_limit_mb=None):
            if not self.calls:
                with TestingSessionLocal() as other:
                    current = other.get(Submission, sub_id)
                    assert submission_repo.recover_stale(other, sub_id, current.execution_generation) is not None
            return super().execute(source_code, input_data, memory_limit_mb)

    with TestingSessionLocal() as s:
        assert submission_svc.judge_submission(s, sub_id, adapters={"PYTHON3": RecoveringAdapter()}) is False
    with TestingSessionLocal() as s:
        sub = s.get(Submission, sub_id)
        assert sub.status == RunStatus.PENDING.value and sub.execution_generation == 2 and sub.judge_result is None
        # The recovered generation judges normally
        assert submission_svc.judge_submission(s, sub_id, adapters={"PYTHON3": FakeAdapter()}) is True
        s.expire_all()
        assert s.get(Submission, sub_id).verdict == RunVerdict.ACCEPTED.value


def test_two_workers_claim_only_one_wins(world):
    sub_id = _pending_submission(world)
    barrier = threading.Barrier(4)
    results = []

    def claim():
        with TestingSessionLocal() as s:
            barrier.wait()
            got = submission_repo.claim_for_judging(s, sub_id)
            results.append(got.execution_generation if got else None)

    threads = [threading.Thread(target=claim) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results, key=lambda g: g is not None) == [None, None, None, 1]


def test_duplicate_delivery_judges_once(world):
    sub_id = _pending_submission(world)
    adapter = FakeAdapter()
    with TestingSessionLocal() as s:
        assert submission_svc.judge_submission(s, sub_id, adapters={"PYTHON3": adapter}) is True
        assert submission_svc.judge_submission(s, sub_id, adapters={"PYTHON3": adapter}) is False
    assert len(adapter.calls) == 3


def test_reconciler_recovers_stuck_running_and_pending(world, enqueued):
    stuck_running = _pending_submission(world)
    stuck_pending = _pending_submission(world)
    fresh = _pending_submission(world)
    with TestingSessionLocal() as s:
        submission_repo.claim_for_judging(s, stuck_running)
    _age(stuck_running)
    _age(stuck_pending)
    enqueued.clear()

    with TestingSessionLocal() as s:
        assert submission_svc.recover_stale_submissions(s, 600) == 2
    assert sorted(enqueued) == sorted([stuck_running, stuck_pending])

    with TestingSessionLocal() as s:
        running = s.get(Submission, stuck_running)
        pending = s.get(Submission, stuck_pending)
        assert (running.status, running.execution_generation) == (RunStatus.PENDING.value, 2)
        assert (pending.status, pending.execution_generation) == (RunStatus.PENDING.value, 1)
        assert s.get(Submission, fresh).execution_generation == 0
        # Re-delivered jobs complete
        for sub_id in (stuck_running, stuck_pending):
            assert submission_svc.judge_submission(s, sub_id, adapters={"PYTHON3": FakeAdapter()}) is True

    # A finished submission is never swept again
    _age(stuck_running)
    with TestingSessionLocal() as s:
        assert submission_svc.recover_stale_submissions(s, 600) == 0


def test_worker_dispatches_by_kind(monkeypatch):
    seen = []
    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "judge_submission", lambda db, sid: seen.append(("submission", sid)))
    monkeypatch.setattr(worker, "process_run", lambda db, rid: seen.append(("run", rid)))
    sub_id, run_id = uuid.uuid4(), uuid.uuid4()

    worker.handle_message({"kind": "submission", "submission_id": str(sub_id)})
    worker.handle_message({"run_id": str(run_id)})
    worker.handle_message({"kind": "submission"})
    worker.handle_message({})
    assert seen == [("submission", sub_id), ("run", run_id)]
