"""Phase 10C — Statistics (REQ-OBS-007; docs/36 §4 10C, AC-10-11).

Numbers are checked against a hand-computed fixture. Reuses the Phase 10 fixtures
(guarded database spnc_phase10_submission_test).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.session import CodingSession
from app.models.user import User
from app.repositories.run import run_repository
from tests.api.test_exam_lifecycle import _class_with, _draft, _set
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    FakeAdapter, TestingSessionLocal, _add_case, _auth, _judge, _make_user, _snapshot, _submit, client,
    clean_db, db, enqueued, setup_database, world,
)


class SampleOnly(FakeAdapter):
    """Right on the sample (weight 10 of 100), wrong elsewhere."""
    def execute(self, source_code, input_data, memory_limit_mb=None):
        res = super().execute(source_code, input_data, memory_limit_mb)
        return res if input_data == "1 2\n" else {**res, "stdout": "nope\n"}


def _practice(h, pid):
    r = client.post("/api/v1/my/practice/sessions", json={"problem_id": pid, "language": "PYTHON3"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _attempt(h, pid, code, adapter=None):
    sid = _practice(h, pid)
    sub_id = _submit(h, sid, _snapshot(h, sid, code)).json()["id"]
    _judge(sub_id, adapter)
    return sid, sub_id


def _buckets(body):
    return {b["range_start"]: b["count"] for b in body["score"]["distribution"] if b["count"]}


@pytest.fixture
def people(db, world):
    w = world
    stu2 = db.scalar(select(User).where(User.username == "stu2"))
    stu3 = _make_user(db, "stu3", "STUDENT")
    outsider = _make_user(db, "outsider", "STUDENT")
    cid = _class_with(w, w["student_id"], stu2.id, stu3.id)
    _class_with(w, outsider.id)   # docs/41 R3: practising PUBLIC problems needs some class; not the one under test
    return {**w, "cid": cid, "stu2": stu2.id, "stu3": stu3.id, "h_out": _auth("outsider")}


def test_class_statistics_match_fixture(db, people):
    w = people
    p2 = client.post("/api/v1/problems", json={"title": "Two", "description": "d", "visibility": "PUBLIC",
                                               "supported_languages": ["PYTHON3"]}, headers=w["h_t"]).json()["id"]
    _add_case(w["h_t"], p2, "1 2\n", "3\n")

    # stu: 0 then 100 on P -> best 100; two runs
    s1, _ = _attempt(w["h_s"], w["pid"], "WRONG\n")
    _attempt(w["h_s"], w["pid"], "SUM\n")
    with TestingSessionLocal() as s:
        snap = s.scalar(select(CodingSession).where(CodingSession.id == uuid.UUID(s1))).final_code_snapshot_id
        run_repository.create(s, session_id=uuid.UUID(s1), snapshot_id=snap)
        run_repository.create(s, session_id=uuid.UUID(s1), snapshot_id=snap)
    # stu2: 10 on P, 100 on P2 -> mean 55; plus one internal failure (not judged)
    _attempt(w["h_s2"], w["pid"], "SUM\n", SampleOnly())
    _attempt(w["h_s2"], p2, "SUM\n")
    _attempt(w["h_s2"], w["pid"], "BOOM\n")
    # stu3: nothing. outsider: activity on the same problem, not a class member
    _attempt(w["h_out"], w["pid"], "SUM\n")

    r = client.get(f"/api/v1/classes/{w['cid']}/statistics", headers=w["h_t"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student_count"] == 3
    assert body["score"] == {**body["score"], "unit": "PERCENT", "max_possible": 100, "scored_student_count": 2, "average": 77.5}
    assert _buckets(body) == {50: 1, 90: 1}
    assert body["submissions"] == {"total": 5, "judged": 4, "accepted": 2, "not_accepted": 2, "accepted_ratio": 0.5}

    rows = {r["username"]: r for r in body["students"]}
    assert (rows["stu"]["score"], rows["stu"]["session_count"], rows["stu"]["submission_count"], rows["stu"]["run_count"]) == (100, 2, 2, 2)
    assert (rows["stu2"]["score"], rows["stu2"]["session_count"], rows["stu2"]["submission_count"], rows["stu2"]["run_count"]) == (55, 3, 3, 0)
    assert (rows["stu3"]["score"], rows["stu3"]["session_count"]) == (None, 0)
    assert "outsider" not in rows

    member_ids = [w["student_id"], w["stu2"]]
    times = db.scalars(select(CodingSession.working_time_seconds).where(CodingSession.student_id.in_(member_ids))).all()
    assert body["average_working_time_seconds"] == round(sum(times) / len(times), 2)

    # No labels or judgments in the payload (NG1/NG6)
    assert set(rows["stu"]) == {"student_id", "username", "full_name", "score", "run_count", "submission_count", "session_count"}


def test_class_statistics_follow_visibility_rule(db, people):
    """Another teacher's class with the same student does not see sessions on problems not published to it."""
    w = people
    _attempt(w["h_s"], w["pid"], "SUM\n")
    _make_user(db, "t2", "TEACHER")
    h2 = _auth("t2")
    c2 = client.post("/api/v1/classes", json={"name": "C2", "academic_year": "2026"}, headers=h2).json()["id"]
    client.post(f"/api/v1/classes/{c2}/members", json={"student_id": str(w["student_id"])}, headers=h2)
    body = client.get(f"/api/v1/classes/{c2}/statistics", headers=h2).json()
    assert body["student_count"] == 1
    assert body["students"][0]["session_count"] == 0 and body["submissions"]["total"] == 0
    assert body["average_working_time_seconds"] is None and body["score"]["average"] is None


def test_exam_statistics_match_fixture(db, people):
    w = people
    eid = _draft(w, cid=w["cid"], pid=w["pid"])   # max_score 40
    assert client.post(f"/api/v1/exams/{eid}/publish", headers=w["h_t"]).status_code == 200
    now = datetime.now(timezone.utc)
    _set(eid, start_time=now - timedelta(minutes=5), end_time=now + timedelta(minutes=60), status="ONGOING")
    # Practice activity must not leak into exam numbers
    _attempt(w["h_s"], w["pid"], "SUM\n")

    for h, code in ((w["h_s"], "SUM\n"), (w["h_s2"], "WRONG\n")):
        part = client.post(f"/api/v1/my/exams/{eid}/start", headers=h).json()["id"]
        r = client.post(f"/api/v1/my/exam-sessions?participation_id={part}", json={"problem_id": w["pid"], "language": "PYTHON3"},
                        headers=h)
        sid = r.json()["id"]
        _judge(_submit(h, sid, _snapshot(h, sid, code)).json()["id"])

    body = client.get(f"/api/v1/exams/{eid}/statistics", headers=w["h_t"]).json()
    assert body["student_count"] == 3
    assert body["score"]["unit"] == "POINTS" and body["score"]["max_possible"] == 40
    assert body["score"]["scored_student_count"] == 2 and body["score"]["average"] == 20
    assert _buckets(body) == {0: 1, 90: 1}
    assert body["submissions"] == {"total": 2, "judged": 2, "accepted": 1, "not_accepted": 1, "accepted_ratio": 0.5}
    rows = {r["username"]: r for r in body["students"]}
    assert (rows["stu"]["score"], rows["stu"]["session_count"]) == (40, 1)
    assert (rows["stu2"]["score"], rows["stu3"]["score"]) == (0, None)


def test_statistics_owner_only(db, people):
    w = people
    eid = _draft(w, cid=w["cid"], pid=w["pid"])
    _make_user(db, "t2", "TEACHER")
    h2 = _auth("t2")
    for url in (f"/api/v1/classes/{w['cid']}/statistics", f"/api/v1/exams/{eid}/statistics"):
        assert client.get(url, headers=w["h_t"]).status_code == 200
        r = client.get(url, headers=h2)
        assert r.status_code == 403 and r.json()["error_code"] == "FORBIDDEN_RESOURCE"
        assert client.get(url, headers=w["h_s"]).status_code == 403
        assert client.get(url).status_code == 401
    assert client.get(f"/api/v1/exams/{uuid.uuid4()}/statistics", headers=w["h_t"]).status_code == 404
