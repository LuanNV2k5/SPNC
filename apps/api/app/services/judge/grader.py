"""Phase 10A — Submission grading (docs/36 §3, D3/D4/D7/D12).

Pure logic over an adapter: no database access, so it is unit-testable with a fake adapter.
"""
from typing import Any, Dict, List, Optional, Protocol

from app.core.config import settings
from app.models.run_submit import RunVerdict


class _Adapter(Protocol):
    def execute(self, source_code: str, input_data: Optional[str], memory_limit_mb: Optional[int] = None) -> Dict[str, Any]: ...


def normalize_output(text: Optional[str]) -> str:
    """D3: CRLF/CR -> LF, strip trailing whitespace per line, drop trailing empty lines."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip() for line in lines]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def effective_limits(time_limit_ms: Optional[int], memory_limit_mb: Optional[int]) -> Dict[str, int]:
    """D12: per-problem limits capped by the global sandbox maxima."""
    global_time_ms = settings.JUDGE_WALL_TIME_LIMIT_SECONDS * 1000
    time_ms = min(time_limit_ms or global_time_ms, global_time_ms)
    memory_mb = min(memory_limit_mb or settings.JUDGE_MEMORY_LIMIT_MB, settings.JUDGE_MEMORY_LIMIT_MB)
    return {"time_limit_ms": time_ms, "memory_limit_mb": memory_mb}


def _case_verdict(raw: Dict[str, Any], expected_output: str, time_limit_ms: int) -> RunVerdict:
    verdict = RunVerdict(raw["verdict"])
    if verdict != RunVerdict.ACCEPTED:
        return verdict
    # Measured time includes interpreter start inside the container; JUDGE_STARTUP_ALLOWANCE_MS offsets it
    measured = max(0, int(raw.get("time_ms") or 0) - settings.JUDGE_STARTUP_ALLOWANCE_MS)
    if measured > time_limit_ms:
        return RunVerdict.TIME_LIMIT_EXCEEDED
    if normalize_output(raw.get("stdout")) != normalize_output(expected_output):
        return RunVerdict.WRONG_ANSWER
    return RunVerdict.ACCEPTED


def grade(adapter: _Adapter, source_code: str, test_cases: List[Any], score_base: int,
          time_limit_ms: Optional[int], memory_limit_mb: Optional[int]) -> Dict[str, Any]:
    """
    Runs every test case in order_index order and aggregates per D4.
    Returns {verdict, score, judge_result, internal_error}.
    """
    limits = effective_limits(time_limit_ms, memory_limit_mb)
    cases = sorted(test_cases, key=lambda tc: tc.order_index)
    results: List[Dict[str, Any]] = []
    first_failure: Optional[RunVerdict] = None
    internal_error = False
    compile_error_message = None
    passed_weight = total_weight = passed_count = 0

    for tc in cases:
        raw = adapter.execute(source_code, tc.input_data, memory_limit_mb=limits["memory_limit_mb"])
        if RunVerdict(raw["verdict"]) == RunVerdict.COMPILE_ERROR:
            # D4: compilation failure ends grading; no further cases run
            compile_error_message = raw.get("compile_error_message")
            first_failure = RunVerdict.COMPILE_ERROR
            results = []
            passed_weight = passed_count = 0
            total_weight = sum(c.score_weight for c in cases)
            break
        verdict = _case_verdict(raw, tc.expected_output, limits["time_limit_ms"])
        if verdict == RunVerdict.INTERNAL_ERROR:
            internal_error = True
        passed = verdict == RunVerdict.ACCEPTED
        is_sample = not tc.is_hidden
        entry = {
            "testcase_id": str(tc.id), "order_index": tc.order_index, "is_sample": is_sample,
            "verdict": verdict.value, "passed": passed,
            "execution_time_ms": int(raw.get("time_ms") or 0), "memory_used_kb": int(raw.get("memory_kb") or 0),
        }
        if is_sample:
            # D7: only sample I/O is ever stored; hidden input/expected/output never leave the judge
            entry.update({"input": tc.input_data, "expected_output": tc.expected_output,
                          "stdout": raw.get("stdout", ""), "stderr": raw.get("stderr", "")})
        results.append(entry)
        total_weight += tc.score_weight
        if passed:
            passed_weight += tc.score_weight
            passed_count += 1
        elif first_failure is None:
            first_failure = verdict

    if internal_error:
        overall = RunVerdict.INTERNAL_ERROR
        score = None
    else:
        overall = first_failure or RunVerdict.ACCEPTED
        if total_weight > 0:
            score = (score_base * passed_weight) // total_weight
        else:
            # All weights zero: fall back to the share of passed cases
            score = (score_base * passed_count) // len(cases) if cases else 0

    return {
        "verdict": overall,
        "score": score,
        "internal_error": internal_error,
        "judge_result": {
            "testcases": results,
            "passed_count": passed_count, "total_count": len(cases),
            "passed_weight": passed_weight, "total_weight": total_weight,
            "score_base": score_base,
            "time_limit_ms": limits["time_limit_ms"], "memory_limit_mb": limits["memory_limit_mb"],
            "compile_error_message": compile_error_message,
        },
    }
