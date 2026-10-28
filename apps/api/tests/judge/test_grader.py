"""Phase 10A — grader unit tests (docs/36 D3, D4, D7, D12). No database, no Docker."""
import os
import uuid
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost:5432/unused")

from app.core.config import settings
from app.models.run_submit import RunVerdict
from app.services.judge.grader import effective_limits, grade, normalize_output


def _case(order, expected, weight=10, hidden=True, input_data=""):
    return SimpleNamespace(id=uuid.uuid4(), order_index=order, input_data=input_data,
                           expected_output=expected, score_weight=weight, is_hidden=hidden)


class FakeAdapter:
    """Returns scripted results keyed by input_data; records calls."""
    def __init__(self, results):
        self.results = results
        self.calls = []

    def execute(self, source_code, input_data, memory_limit_mb=None):
        self.calls.append((input_data, memory_limit_mb))
        base = {"stdout": "", "stderr": "", "time_ms": 0, "memory_kb": 0,
                "compile_error_message": None, "runtime_error_message": None}
        base.update(self.results[input_data])
        return base


def _ok(stdout, time_ms=0):
    return {"verdict": RunVerdict.ACCEPTED, "stdout": stdout, "time_ms": time_ms}


# --- D3 output normalization ------------------------------------------------
def test_normalize_output_tolerates_invisible_differences():
    assert normalize_output("1 2\r\n3  \r\n\r\n\n") == "1 2\n3"
    assert normalize_output(None) == ""
    assert normalize_output("a\n b") == "a\n b"            # leading spaces are content


# --- D4 verdict aggregation and scoring --------------------------------------
def test_all_pass_full_score():
    cases = [_case(1, "3", input_data="a"), _case(2, "7", input_data="b")]
    out = grade(FakeAdapter({"a": _ok("3\n"), "b": _ok("7")}), "src", cases, 100, None, None)
    assert out["verdict"] == RunVerdict.ACCEPTED
    assert out["score"] == 100
    assert out["judge_result"]["passed_count"] == 2


def test_first_failing_case_decides_verdict_and_all_cases_still_run():
    cases = [_case(1, "1", weight=20, input_data="a"), _case(2, "2", weight=30, input_data="b"),
             _case(3, "3", weight=50, input_data="c")]
    adapter = FakeAdapter({
        "a": _ok("1"),
        "b": {"verdict": RunVerdict.RUNTIME_ERROR},
        "c": _ok("wrong"),
    })
    out = grade(adapter, "src", cases, 100, None, None)
    assert out["verdict"] == RunVerdict.RUNTIME_ERROR
    assert len(adapter.calls) == 3
    assert [t["verdict"] for t in out["judge_result"]["testcases"]] == ["ACCEPTED", "RUNTIME_ERROR", "WRONG_ANSWER"]
    assert out["score"] == 20                               # 100 * 20 / 100


def test_cases_run_in_order_index_order():
    cases = [_case(2, "x", input_data="second"), _case(1, "y", input_data="first")]
    adapter = FakeAdapter({"first": _ok("y"), "second": {"verdict": RunVerdict.RUNTIME_ERROR}})
    out = grade(adapter, "src", cases, 100, None, None)
    assert [c[0] for c in adapter.calls] == ["first", "second"]
    assert out["verdict"] == RunVerdict.RUNTIME_ERROR


def test_compile_error_stops_and_scores_zero():
    cases = [_case(1, "1", input_data="a"), _case(2, "2", input_data="b")]
    adapter = FakeAdapter({"a": {"verdict": RunVerdict.COMPILE_ERROR, "compile_error_message": "error: x"},
                           "b": _ok("2")})
    out = grade(adapter, "src", cases, 80, None, None)
    assert out["verdict"] == RunVerdict.COMPILE_ERROR
    assert out["score"] == 0
    assert len(adapter.calls) == 1
    assert out["judge_result"]["compile_error_message"] == "error: x"
    assert out["judge_result"]["testcases"] == []


def test_score_rounds_down_on_exam_base():
    cases = [_case(1, "1", weight=1, input_data="a"), _case(2, "2", weight=2, input_data="b")]
    out = grade(FakeAdapter({"a": _ok("1"), "b": _ok("no")}), "src", cases, 10, None, None)
    assert out["score"] == 3                                # floor(10 * 1 / 3)


def test_zero_weights_fall_back_to_case_share():
    cases = [_case(1, "1", weight=0, input_data="a"), _case(2, "2", weight=0, input_data="b")]
    out = grade(FakeAdapter({"a": _ok("1"), "b": _ok("no")}), "src", cases, 100, None, None)
    assert out["score"] == 50


def test_internal_error_marks_submission_failed_without_score():
    cases = [_case(1, "1", input_data="a")]
    out = grade(FakeAdapter({"a": {"verdict": RunVerdict.INTERNAL_ERROR}}), "src", cases, 100, None, None)
    assert out["internal_error"] is True
    assert out["verdict"] == RunVerdict.INTERNAL_ERROR
    assert out["score"] is None


# --- D12 limits ---------------------------------------------------------------
def test_time_limit_applies_after_startup_allowance():
    limit = 1000
    slow = limit + settings.JUDGE_STARTUP_ALLOWANCE_MS + 1
    fast = limit + settings.JUDGE_STARTUP_ALLOWANCE_MS
    cases = [_case(1, "ok", input_data="slow"), _case(2, "ok", input_data="fast")]
    out = grade(FakeAdapter({"slow": _ok("ok", slow), "fast": _ok("ok", fast)}), "src", cases, 100, limit, None)
    assert [t["verdict"] for t in out["judge_result"]["testcases"]] == ["TIME_LIMIT_EXCEEDED", "ACCEPTED"]


def test_problem_limits_are_capped_by_global_maxima():
    big = effective_limits(10 ** 9, 10 ** 6)
    assert big["time_limit_ms"] == settings.JUDGE_WALL_TIME_LIMIT_SECONDS * 1000
    assert big["memory_limit_mb"] == settings.JUDGE_MEMORY_LIMIT_MB
    small = effective_limits(200, 64)
    assert small == {"time_limit_ms": 200, "memory_limit_mb": 64}


def test_memory_limit_is_passed_to_adapter():
    adapter = FakeAdapter({"a": _ok("1")})
    grade(adapter, "src", [_case(1, "1", input_data="a")], 100, None, 64)
    assert adapter.calls == [("a", 64)]


# --- D7 hidden data never stored ---------------------------------------------
def test_hidden_case_io_not_in_judge_result():
    cases = [_case(1, "SAMPLE_OUT", hidden=False, input_data="SAMPLE_IN"),
             _case(2, "SECRET_OUT", hidden=True, input_data="SECRET_IN")]
    out = grade(FakeAdapter({"SAMPLE_IN": _ok("SAMPLE_OUT"), "SECRET_IN": _ok("SECRET_STDOUT")}), "src", cases, 100, None, None)
    sample, hidden = out["judge_result"]["testcases"]
    assert sample["input"] == "SAMPLE_IN" and sample["expected_output"] == "SAMPLE_OUT"
    assert set(hidden) == {"testcase_id", "order_index", "is_sample", "verdict", "passed", "execution_time_ms", "memory_used_kb"}
    assert "SECRET" not in str(out["judge_result"])
