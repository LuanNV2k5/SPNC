"""Phase 11 — End-to-end against the running compose stack (docs/37 AC-11-03, AC-11-05).

Talks to the stack over HTTP/WebSocket only. Run and Submission are judged by the separate
`worker` container, which reads code from MinIO: this is the cross-process path that the
in-memory storage could not serve.

Skipped unless SPNC_E2E_BASE_URL is set, e.g.
    SPNC_E2E_BASE_URL=http://127.0.0.1:8000 \
    SPNC_E2E_ADMIN_USER=admin SPNC_E2E_ADMIN_PASSWORD=<bootstrap password> \
    SPNC_E2E_ADMIN_NEW_PASSWORD=<password the admin is moved to> \
    python -m pytest tests/e2e/test_compose_stack.py
Re-runnable: the admin keeps the new password; every other account is created fresh.
"""
import json
import os
import time
import uuid

import pytest
import requests

BASE = os.environ.get("SPNC_E2E_BASE_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE, reason="SPNC_E2E_BASE_URL not set (compose stack E2E)")

API = f"{BASE}/api/v1"
TEMP_PW = "Temp-Password-123!"
FINAL_PW = "Final-Password-456!"
SUM_PY = "a, b = map(int, input().split())\nprint(a + b)\n"


def _login(username, password):
    return requests.post(f"{API}/auth/login", data={"username": username, "password": password}, timeout=10)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _ready_user(username, temp_password, final_password):
    """Logs in and completes the forced password change; returns an access token."""
    r = _login(username, temp_password)
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    r = requests.post(f"{API}/auth/change-password", json={"current_password": temp_password, "new_password": final_password},
                      headers=_h(token), timeout=10)
    assert r.status_code == 200, r.text
    r = _login(username, final_password)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    user = os.environ.get("SPNC_E2E_ADMIN_USER", "admin")
    new_pw = os.environ["SPNC_E2E_ADMIN_NEW_PASSWORD"]
    r = _login(user, new_pw)
    if r.status_code == 200:
        return r.json()["access_token"]
    return _ready_user(user, os.environ["SPNC_E2E_ADMIN_PASSWORD"], new_pw)


@pytest.fixture(scope="module")
def people(admin_token):
    suffix = uuid.uuid4().hex[:8]
    tokens = {}
    for role in ("TEACHER", "STUDENT"):
        username = f"e2e_{role.lower()}_{suffix}"
        r = requests.post(f"{API}/admin/users", json={"username": username, "email": f"{username}@spnc.io", "password": TEMP_PW,
                                                     "full_name": username, "role": role}, headers=_h(admin_token), timeout=10)
        assert r.status_code in (200, 201), r.text
        tokens[role] = _ready_user(username, TEMP_PW, FINAL_PW)
    return tokens


def _poll(url, headers, done, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = requests.get(url, headers=headers, timeout=10).json()
        if done(body):
            return body
        time.sleep(1)
    pytest.fail(f"Timed out waiting on {url}: last body {body}")


@pytest.fixture(scope="module")
def problem(people):
    h = _h(people["TEACHER"])
    pid = requests.post(f"{API}/problems", json={"title": "E2E Sum", "description": "a+b", "visibility": "PUBLIC",
                                                 "supported_languages": ["PYTHON3"]}, headers=h, timeout=10).json()["id"]
    for inp, out, sample in (("1 2\n", "3\n", True), ("40 2\n", "42\n", False)):
        r = requests.post(f"{API}/problems/{pid}/test-cases", json={"input_data": inp, "expected_output": out, "is_sample": sample},
                          headers=h, timeout=10)
        assert r.status_code == 201, r.text
    return pid


def _session_with_snapshot(student_h, pid, code):
    sid = requests.post(f"{API}/my/practice/sessions", json={"problem_id": pid, "language": "PYTHON3"},
                        headers=student_h, timeout=10).json()["id"]
    r = requests.post(f"{API}/my/coding-sessions/{sid}/snapshots", json={
        "reason": "RUN", "language": "PYTHON3", "source_code": code, "line_count": code.count("\n")}, headers=student_h, timeout=10)
    assert r.status_code == 200, r.text
    return sid, r.json()["id"]


def test_run_is_executed_by_worker_container(people, problem):
    h = _h(people["STUDENT"])
    sid, snap = _session_with_snapshot(h, problem, SUM_PY)
    r = requests.post(f"{API}/my/coding-sessions/{sid}/runs", json={"snapshot_id": snap, "input": "20 22\n"}, headers=h, timeout=10)
    assert r.status_code == 200, r.text
    run = _poll(f"{API}/my/coding-sessions/{sid}/runs/{r.json()['id']}", h, lambda b: b["status"] in ("COMPLETED", "FAILED_INTERNAL"))
    assert run["status"] == "COMPLETED", run
    assert run["verdict"] == "ACCEPTED" and run["testcase_results"]["stdout"].strip() == "42"


def test_submission_is_judged_by_worker_container(people, problem):
    h = _h(people["STUDENT"])
    sid, snap = _session_with_snapshot(h, problem, SUM_PY)
    r = requests.post(f"{API}/my/coding-sessions/{sid}/submissions", json={"snapshot_id": snap}, headers=h, timeout=10)
    assert r.status_code == 201, r.text
    sub = _poll(f"{API}/my/submissions/{r.json()['id']}", h, lambda b: b["status"] in ("COMPLETED", "FAILED_INTERNAL"))
    assert sub["status"] == "COMPLETED", sub
    assert sub["verdict"] == "ACCEPTED" and sub["score"] == 100
    assert [c["passed"] for c in sub["judge_result"]["testcases"]] == [True, True]


def test_wrong_answer_is_judged_too(people, problem):
    h = _h(people["STUDENT"])
    sid, snap = _session_with_snapshot(h, problem, "print(3)\n")
    sub_id = requests.post(f"{API}/my/coding-sessions/{sid}/submissions", json={"snapshot_id": snap}, headers=h, timeout=10).json()["id"]
    sub = _poll(f"{API}/my/submissions/{sub_id}", h, lambda b: b["status"] in ("COMPLETED", "FAILED_INTERNAL"))
    # Right on the sample only: weights 10 + 10, so half the score
    assert (sub["status"], sub["verdict"], sub["score"]) == ("COMPLETED", "WRONG_ANSWER", 50)


def test_teacher_websocket_served_by_uvicorn(people):
    from websockets.sync.client import connect
    ws_url = BASE.replace("http://", "ws://").replace("https://", "wss://") + "/api/v1/ws/teacher"
    with connect(ws_url, open_timeout=10) as ws:
        ws.send(json.dumps({"type": "auth", "access_token": people["TEACHER"]}))
        assert json.loads(ws.recv(timeout=10)) == {"type": "authenticated"}
