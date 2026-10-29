"""Phase 18 — Restore drill data check (docs/44 §3.5, AC-18-05). Run by deploy/backup/drill.sh.

    SPNC_DRILL_PHASE=seed   before the backup: a teacher, a class, a student with a judged
                            submission; the ids and the code go to SPNC_DRILL_STATE (JSON)
    SPNC_DRILL_PHASE=check  after the restore: the same accounts log in, the teacher reads the
                            snapshot content back through the API (MinIO blob restored), the
                            submission keeps its verdict, and the worker judges a snapshot
                            taken before the backup

Skipped unless SPNC_E2E_BASE_URL and SPNC_DRILL_PHASE are set. Admin credentials as in
test_compose_stack.py.
"""
import json
import os
import uuid

import pytest
import requests

from tests.e2e.test_compose_stack import API, BASE, FINAL_PW, TEMP_PW, _h, _login, _poll, _ready_user, admin_token  # noqa: F401

PHASE = os.environ.get("SPNC_DRILL_PHASE", "")
STATE = os.environ.get("SPNC_DRILL_STATE", "drill-state.json")
pytestmark = pytest.mark.skipif(not (BASE and PHASE), reason="restore drill only (deploy/backup/drill.sh)")
CODE = "a, b = map(int, input().split())\nprint(a + b)  # drill\n"


def _submit(h, sid, snap):
    r = requests.post(f"{API}/my/coding-sessions/{sid}/submissions", json={"snapshot_id": snap}, headers=h, timeout=10)
    assert r.status_code == 201, r.text
    return _poll(f"{API}/my/submissions/{r.json()['id']}", h, lambda b: b["status"] in ("COMPLETED", "FAILED_INTERNAL"))


def _session_with_snapshot(h, pid):
    sid = requests.post(f"{API}/my/practice/sessions", json={"problem_id": pid, "language": "PYTHON3"}, headers=h, timeout=10).json()["id"]
    r = requests.post(f"{API}/my/coding-sessions/{sid}/snapshots", json={
        "reason": "SUBMIT", "language": "PYTHON3", "source_code": CODE, "line_count": 2}, headers=h, timeout=10)
    assert r.status_code == 200, r.text
    return sid, r.json()["id"]


@pytest.mark.skipif(PHASE != "seed", reason="seed phase")
def test_seed(admin_token):
    suffix = uuid.uuid4().hex[:8]
    ids = {}
    for role in ("TEACHER", "STUDENT"):
        username = f"drill_{role.lower()}_{suffix}"
        r = requests.post(f"{API}/admin/users", json={"username": username, "email": f"{username}@spnc.io", "password": TEMP_PW,
                                                     "full_name": username, "role": role}, headers=_h(admin_token), timeout=10)
        assert r.status_code in (200, 201), r.text
        ids[role] = {"username": username, "id": r.json()["id"], "token": _ready_user(username, TEMP_PW, FINAL_PW)}
    th, sh = _h(ids["TEACHER"]["token"]), _h(ids["STUDENT"]["token"])

    pid = requests.post(f"{API}/problems", json={"title": "Drill Sum", "description": "a+b", "visibility": "PUBLIC",
                                                 "supported_languages": ["PYTHON3"]}, headers=th, timeout=10).json()["id"]
    for inp, out, sample in (("1 2\n", "3\n", True), ("40 2\n", "42\n", False)):
        assert requests.post(f"{API}/problems/{pid}/test-cases", json={"input_data": inp, "expected_output": out, "is_sample": sample},
                             headers=th, timeout=10).status_code == 201
    klass = requests.post(f"{API}/classes", json={"name": "Drill", "academic_year": "2026"}, headers=th, timeout=10).json()
    assert requests.post(f"{API}/my/classes/join", json={"invite_code": klass["invite_code"]}, headers=sh, timeout=10).status_code == 201

    sid, snap = _session_with_snapshot(sh, pid)
    sub = _submit(sh, sid, snap)          # a submission ends the practice session
    assert (sub["status"], sub["verdict"], sub["score"]) == ("COMPLETED", "ACCEPTED", 100)
    open_sid, open_snap = _session_with_snapshot(sh, pid)   # stays ACTIVE: submitted after the restore

    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"teacher": ids["TEACHER"]["username"], "student": ids["STUDENT"]["username"], "student_id": ids["STUDENT"]["id"],
                   "class_id": klass["id"], "session_id": sid, "snapshot_id": snap, "submission_id": sub["id"],
                   "open_session_id": open_sid, "open_snapshot_id": open_snap}, f)


@pytest.mark.skipif(PHASE != "check", reason="check phase")
def test_restored_data_is_intact():
    with open(STATE, encoding="utf-8") as f:
        s = json.load(f)
    t, st = _login(s["teacher"], FINAL_PW), _login(s["student"], FINAL_PW)
    assert t.status_code == 200 and st.status_code == 200, (t.text, st.text)
    th, sh = _h(t.json()["access_token"]), _h(st.json()["access_token"])

    # Blob restored and still bound to its row (docs/44 invariant 1)
    r = requests.get(f"{API}/classes/{s['class_id']}/students/{s['student_id']}/sessions/{s['session_id']}/snapshots/{s['snapshot_id']}",
                     headers=th, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["content_available"] is True and r.json()["source_code"] == CODE

    sub = requests.get(f"{API}/my/submissions/{s['submission_id']}", headers=sh, timeout=10).json()
    assert (sub["status"], sub["verdict"], sub["score"]) == ("COMPLETED", "ACCEPTED", 100)

    # The worker reads a restored blob from MinIO and judges it
    again = _submit(sh, s["open_session_id"], s["open_snapshot_id"])
    assert (again["status"], again["verdict"], again["score"]) == ("COMPLETED", "ACCEPTED", 100)
