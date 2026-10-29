"""Phase 14A — Practice points (REQ-STU-004; OQ-16 resolved by docs/40 Q1-Q3).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test).
"""
import uuid

from sqlalchemy import select

from app.models.observation import PointTransaction
from app.models.run_submit import Submission
from app.repositories import submission as submission_repo
from app.services import submission as submission_svc
from tests.api.test_exam_lifecycle import _class_with
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    FakeAdapter, TestingSessionLocal, _auth, _exam_session, _judge, _make_user, _practice_session, _snapshot, _submit,
    client, clean_db, db, enqueued, setup_database, world,
)


def _attempt(w, code, h=None, pid=None):
    h = h or w["h_s"]
    r = client.post("/api/v1/my/practice/sessions", json={"problem_id": pid or w["pid"], "language": "PYTHON3"}, headers=h)
    sid = r.json()["id"]
    sub_id = _submit(h, sid, _snapshot(h, sid, code)).json()["id"]
    return sub_id


def _points(h):
    r = client.get("/api/v1/my/points", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_first_accepted_awards_once_by_difficulty(db, world):
    w = world
    assert _points(w["h_s"])["total"] == 0

    _judge(_attempt(w, "WRONG\n"))
    assert _points(w["h_s"])["total"] == 0                 # not ACCEPTED

    first = _attempt(w, "SUM\n")
    _judge(first)
    body = _points(w["h_s"])
    assert body["total"] == 10                              # no difficulty -> 10
    assert body["transactions"] == [{**body["transactions"][0], "amount": 10, "reason": "PRACTICE_ACCEPTED",
                                     "problem_id": w["pid"], "problem_title": "Sum", "submission_id": first}]

    _judge(_attempt(w, "SUM\n"))                            # solving again earns nothing
    assert _points(w["h_s"])["total"] == 10

    for difficulty, expected in (("EASY", 10), ("MEDIUM", 20), ("HARD", 30)):
        pid = client.post("/api/v1/problems", json={"title": difficulty, "description": "d", "visibility": "PUBLIC",
                                                    "difficulty": difficulty, "supported_languages": ["PYTHON3"]}, headers=w["h_t"]).json()["id"]
        client.post(f"/api/v1/problems/{pid}/test-cases", json={"input_data": "1 2\n", "expected_output": "3\n"}, headers=w["h_t"])
        before = _points(w["h_s"])["total"]
        _judge(_attempt(w, "SUM\n", pid=pid))
        assert _points(w["h_s"])["total"] == before + expected


def test_no_points_for_exam_or_internal_failure(db, world):
    w = world
    _judge(_attempt(w, "BOOM\n"))                           # FAILED_INTERNAL
    eid, part_id, sid = _exam_session(w)
    sub_id = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n")).json()["id"]
    assert _judge(sub_id) is True
    assert db.get(Submission, uuid.UUID(sub_id)).verdict == "ACCEPTED"
    assert _points(w["h_s"])["total"] == 0                  # exams never award (D14 visibility)
    assert db.scalars(select(PointTransaction)).all() == []


def test_duplicate_delivery_and_stale_generation_award_once(db, world):
    w = world
    sub_id = uuid.UUID(_attempt(w, "SUM\n"))

    class RecoveringAdapter(FakeAdapter):
        def execute(self, source_code, input_data, memory_limit_mb=None):
            if not self.calls:
                with TestingSessionLocal() as other:
                    current = other.get(Submission, sub_id)
                    submission_repo.recover_stale(other, sub_id, current.execution_generation)
            return super().execute(source_code, input_data, memory_limit_mb)

    with TestingSessionLocal() as s:
        assert submission_svc.judge_submission(s, sub_id, adapters={"PYTHON3": RecoveringAdapter()}) is False
    assert _points(w["h_s"])["total"] == 0                  # stale result: no points
    assert _judge(sub_id) is True
    assert _judge(sub_id) is False                          # duplicate delivery
    assert _points(w["h_s"])["total"] == 10


def test_points_survive_problem_deletion(db, world):
    w = world
    _judge(_attempt(w, "SUM\n"))
    assert client.delete(f"/api/v1/problems/{w['pid']}", headers=w["h_t"]).status_code == 204
    body = _points(w["h_s"])
    assert body["total"] == 10 and body["transactions"][0]["problem_title"] == "Sum"


def test_teacher_sees_class_member_points_only(db, world):
    w = world
    cid = _class_with(w, w["student_id"])
    _judge(_attempt(w, "SUM\n"))
    url = f"/api/v1/classes/{cid}/students/{w['student_id']}/points"
    r = client.get(url, headers=w["h_t"])
    assert r.status_code == 200 and r.json()["total"] == 10

    _make_user(db, "t2", "TEACHER")
    assert client.get(url, headers=_auth("t2")).status_code == 403
    stu2 = client.get("/api/v1/auth/me", headers=w["h_s2"]).json()["id"]
    assert client.get(f"/api/v1/classes/{cid}/students/{stu2}/points", headers=w["h_t"]).status_code == 403   # not a member
    assert client.get(url, headers=w["h_s"]).status_code == 403
    assert client.get("/api/v1/my/points", headers=w["h_t"]).status_code == 403
