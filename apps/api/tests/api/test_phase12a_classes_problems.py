"""Phase 12A — Class invite codes and problem bank gaps (docs/38; AC-12-01..05).

Reuses the Phase 10 fixtures (guarded database spnc_phase10_submission_test).
"""
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.models.class_org import ClassMembership
from app.models.user import User
from tests.api.test_submissions import (  # noqa: F401  (fixtures are used by name)
    TestingSessionLocal, _auth, _judge, _make_user, _practice_session, _snapshot, _submit, client,
    clean_db, db, enqueued, setup_database, world,
)

CODE_RE = re.compile(r"^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{8}$")


def _class(h, name="C"):
    r = client.post("/api/v1/classes", json={"name": name, "academic_year": "2026"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _join(h, code):
    return client.post("/api/v1/my/classes/join", json={"invite_code": code}, headers=h)


def _problem(h, **extra):
    body = {"title": "P", "description": "d", "visibility": "PUBLIC", "supported_languages": ["PYTHON3"], **extra}
    r = client.post("/api/v1/problems", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _exam_with(h, pid, status):
    now = datetime.now(timezone.utc)
    eid = client.post("/api/v1/exams", json={"title": "E", "start_time": (now + timedelta(hours=1)).isoformat(),
                                             "end_time": (now + timedelta(hours=2)).isoformat()}, headers=h).json()["id"]
    assert client.post(f"/api/v1/exams/{eid}/problems", json={"problem_id": pid, "order_index": 1}, headers=h).status_code == 201
    with TestingSessionLocal() as s:
        s.execute(text("UPDATE exams SET status = :st WHERE id = :id"), {"st": status, "id": eid})
        s.commit()
    return eid


# ---------------------------------------------------------------------------
# AC-12-01 / 02 — invite codes and join
# ---------------------------------------------------------------------------
def test_invite_code_generated_unique_and_owner_only(world):
    w = world
    a, b = _class(w["h_t"], "A"), _class(w["h_t"], "B")
    assert CODE_RE.match(a["invite_code"]) and CODE_RE.match(b["invite_code"]) and a["invite_code"] != b["invite_code"]
    assert client.get(f"/api/v1/classes/{a['id']}", headers=w["h_t"]).json()["invite_code"] == a["invite_code"]

    assert _join(w["h_s"], a["invite_code"]).status_code == 201
    mine = client.get("/api/v1/my/classes", headers=w["h_s"]).json()
    assert mine["total"] == 1 and "invite_code" not in mine["items"][0]
    assert a["invite_code"] not in str(mine)


def test_join_rules(db, world):
    w = world
    c = _class(w["h_t"])
    r = _join(w["h_s"], c["invite_code"].lower())          # case-insensitive entry
    assert r.status_code == 201, r.text
    membership_id = r.json()["id"]
    assert r.json()["is_active"] is True and r.json()["class_id"] == c["id"]

    again = _join(w["h_s"], c["invite_code"])
    assert again.status_code == 409 and again.json()["error_code"] == "ALREADY_ENROLLED"

    # D3: removed member re-joins on the same record
    stu_id = r.json()["student_id"]
    assert client.delete(f"/api/v1/classes/{c['id']}/members/{stu_id}", headers=w["h_t"]).status_code in (200, 204)
    rejoin = _join(w["h_s"], c["invite_code"])
    assert rejoin.status_code == 201 and rejoin.json()["id"] == membership_id
    assert len(db.scalars(select(ClassMembership).where(ClassMembership.class_id == uuid.UUID(c["id"]))).all()) == 1

    unknown = _join(w["h_s2"], "ZZZZZZZZ")
    assert unknown.status_code == 404 and unknown.json()["error_code"] == "INVITE_CODE_INVALID"
    assert _join(w["h_t"], c["invite_code"]).status_code == 403             # students only
    assert client.post("/api/v1/my/classes/join", json={"invite_code": "X", "extra": 1}, headers=w["h_s2"]).status_code == 422

    assert client.patch(f"/api/v1/classes/{c['id']}", json={"is_active": False}, headers=w["h_t"]).status_code == 200
    closed = _join(w["h_s2"], c["invite_code"])
    assert closed.status_code == 403 and closed.json()["error_code"] == "CLASS_NOT_ACTIVE"


def test_locked_student_cannot_join(db, world):
    w = world
    c = _class(w["h_t"])
    stu2 = db.scalar(select(User).where(User.username == "stu2"))
    stu2.status = "LOCKED"
    db.commit()
    assert _join(w["h_s2"], c["invite_code"]).status_code in (401, 403)   # REQ-AUTH-007 / UC-B03 A4


def test_rotate_invite_code(db, world):
    w = world
    c = _class(w["h_t"])
    r = client.post(f"/api/v1/classes/{c['id']}/invite-code/rotate", headers=w["h_t"])
    assert r.status_code == 200 and CODE_RE.match(r.json()["invite_code"]) and r.json()["invite_code"] != c["invite_code"]
    assert _join(w["h_s"], c["invite_code"]).status_code == 404                # old code is dead
    assert _join(w["h_s"], r.json()["invite_code"]).status_code == 201

    _make_user(db, "other_t", "TEACHER")
    assert client.post(f"/api/v1/classes/{c['id']}/invite-code/rotate", headers=_auth("other_t")).status_code == 403
    assert client.post(f"/api/v1/classes/{c['id']}/invite-code/rotate", headers=w["h_s"]).status_code == 403


# ---------------------------------------------------------------------------
# AC-12-03 — problem fields and filters
# ---------------------------------------------------------------------------
def test_problem_statement_fields(world):
    w = world
    p = _problem(w["h_t"], constraints="1 <= a, b <= 10^9", input_format="a b", output_format="a + b", difficulty="EASY")
    got = client.get(f"/api/v1/problems/{p['id']}", headers=w["h_t"]).json()
    assert (got["constraints"], got["input_format"], got["output_format"], got["difficulty"]) == ("1 <= a, b <= 10^9", "a b", "a + b", "EASY")
    upd = client.patch(f"/api/v1/problems/{p['id']}", json={"difficulty": "HARD", "constraints": "none"}, headers=w["h_t"]).json()
    assert upd["difficulty"] == "HARD" and upd["constraints"] == "none"
    assert client.post("/api/v1/problems", json={"title": "x", "description": "d", "difficulty": "EXTREME"}, headers=w["h_t"]).status_code == 422
    assert client.patch(f"/api/v1/problems/{p['id']}", json={"difficulty": "x"}, headers=w["h_t"]).status_code == 422


def test_problem_bank_filters(world):
    w = world
    _problem(w["h_t"], title="easy-py", difficulty="EASY", supported_languages=["PYTHON3"], visibility="PUBLIC")
    _problem(w["h_t"], title="hard-cpp", difficulty="HARD", supported_languages=["CPP17"], visibility="PRIVATE")
    _problem(w["h_t"], title="hard-both", difficulty="HARD", supported_languages=["CPP17", "PYTHON3"], visibility="CLASS")

    def titles(q):
        r = client.get(f"/api/v1/problems?{q}", headers=w["h_t"])
        assert r.status_code == 200, r.text
        return sorted(i["title"] for i in r.json()["items"])

    # world() already owns "Sum" (PUBLIC, PYTHON3, no difficulty)
    assert titles("difficulty=HARD") == ["hard-both", "hard-cpp"]
    assert titles("language=CPP17") == ["hard-both", "hard-cpp"]
    assert titles("language=PYTHON3&visibility=PUBLIC") == ["Sum", "easy-py"]
    assert titles("difficulty=HARD&language=PYTHON3") == ["hard-both"]
    for bad in ("difficulty=EXTREME", "language=JAVA", "visibility=SECRET"):
        assert client.get(f"/api/v1/problems?{bad}", headers=w["h_t"]).status_code == 422


# ---------------------------------------------------------------------------
# AC-12-04 / 05 — lock and soft delete
# ---------------------------------------------------------------------------
def test_problem_frozen_while_exam_scheduled_or_ongoing(world):
    w = world
    p = _problem(w["h_t"])
    eid = _exam_with(w["h_t"], p["id"], "SCHEDULED")
    for status in ("SCHEDULED", "ONGOING"):
        with TestingSessionLocal() as s:
            s.execute(text("UPDATE exams SET status = :st WHERE id = :id"), {"st": status, "id": eid})
            s.commit()
        r = client.patch(f"/api/v1/problems/{p['id']}", json={"title": "new"}, headers=w["h_t"])
        assert r.status_code == 409 and r.json()["error_code"] == "PROBLEM_IN_ACTIVE_EXAM"
        r = client.delete(f"/api/v1/problems/{p['id']}", headers=w["h_t"])
        assert r.status_code == 409 and r.json()["error_code"] == "PROBLEM_IN_ACTIVE_EXAM"
    for status in ("ENDED", "CANCELLED"):
        with TestingSessionLocal() as s:
            s.execute(text("UPDATE exams SET status = :st WHERE id = :id"), {"st": status, "id": eid})
            s.commit()
        assert client.patch(f"/api/v1/problems/{p['id']}", json={"title": status}, headers=w["h_t"]).status_code == 200


def test_soft_delete_hides_problem_but_keeps_history(db, world):
    w = world
    # History: a judged submission on the problem
    sid = _practice_session(w)
    sub_id = _submit(w["h_s"], sid, _snapshot(w["h_s"], sid, "SUM\n")).json()["id"]
    _judge(sub_id)

    pid = w["pid"]
    assert client.delete(f"/api/v1/problems/{pid}", headers=w["h_t"]).status_code == 204
    assert client.delete(f"/api/v1/problems/{pid}", headers=w["h_t"]).status_code == 404

    assert pid not in str(client.get("/api/v1/problems", headers=w["h_t"]).json())
    assert pid not in str(client.get("/api/v1/problems/public/bank", headers=w["h_s"]).json())
    assert client.get(f"/api/v1/problems/{pid}", headers=w["h_s"]).status_code == 404
    owner_view = client.get(f"/api/v1/problems/{pid}", headers=w["h_t"])
    assert owner_view.status_code == 200 and owner_view.json()["deleted_at"] is not None

    r = client.post("/api/v1/my/practice/sessions", json={"problem_id": pid, "language": "PYTHON3"}, headers=w["h_s"])
    assert r.status_code == 404
    assert client.patch(f"/api/v1/problems/{pid}", json={"title": "x"}, headers=w["h_t"]).status_code == 404
    assert client.post(f"/api/v1/problems/{pid}/test-cases", json={"expected_output": "1"}, headers=w["h_t"]).status_code == 404
    now = datetime.now(timezone.utc)
    eid = client.post("/api/v1/exams", json={"title": "E", "start_time": (now + timedelta(hours=1)).isoformat(),
                                             "end_time": (now + timedelta(hours=2)).isoformat()}, headers=w["h_t"]).json()["id"]
    assert client.post(f"/api/v1/exams/{eid}/problems", json={"problem_id": pid, "order_index": 1}, headers=w["h_t"]).status_code == 404

    # The student's history is untouched
    body = client.get(f"/api/v1/my/submissions/{sub_id}", headers=w["h_s"]).json()
    assert body["problem_id"] == pid and body["verdict"] == "ACCEPTED"
