"""Phase 10C — Class and exam statistics (REQ-OBS-007; docs/36 §4 10C).

Descriptive numbers only, computed from Submission / Run / CodingSession data. No labels,
rankings or judgments about students (NG1, NG6). Visibility follows docs/35 §3.

Definitions:
- judged submission: status COMPLETED (FAILED_INTERNAL is excluded from scores and ratios).
- class score of a student: mean over problems of the best judged percentage
  (score / judge_result.score_base * 100); null when the student has no judged submission.
- exam score of a student: ExamParticipation.total_score (D5, best per problem); distribution
  as a percentage of the exam maximum (sum of ExamProblem.max_score), participants only.
- distribution: 10 buckets of 10 points over 0-100 %; 100 % falls in the last bucket.
"""
import uuid
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models.run_submit import RunStatus, RunVerdict, Submission
from app.models.user import User
from app.repositories import statistics as repo
from app.services import observation_auth as auth


def _value(v) -> str:
    return v if isinstance(v, str) else v.value


def _mean(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


def _distribution(percentages: Iterable[float]) -> List[Dict[str, int]]:
    counts = [0] * 10
    for pct in percentages:
        counts[min(int(max(pct, 0) // 10), 9)] += 1
    return [{"range_start": i * 10, "range_end": (i + 1) * 10, "count": counts[i]} for i in range(10)]


def _judged(subs: Iterable[Submission]) -> List[Submission]:
    return [s for s in subs if _value(s.status) == RunStatus.COMPLETED.value and s.score is not None]


def _submission_summary(subs: List[Submission]) -> Dict[str, Any]:
    judged = _judged(subs)
    accepted = sum(1 for s in judged if s.verdict == RunVerdict.ACCEPTED.value)
    return {
        "total": len(subs), "judged": len(judged), "accepted": accepted, "not_accepted": len(judged) - accepted,
        "accepted_ratio": round(accepted / len(judged), 4) if judged else None,
    }


def _per_student_counts(sessions, subs, runs_by_session):
    sessions_by_student, runs_by_student, subs_by_student = defaultdict(int), defaultdict(int), defaultdict(list)
    for s in sessions:
        sessions_by_student[s.student_id] += 1
        runs_by_student[s.student_id] += runs_by_session.get(s.id, 0)
    for sub in subs:
        subs_by_student[sub.student_id].append(sub)
    return sessions_by_student, runs_by_student, subs_by_student


def _average_working_time(sessions) -> Optional[float]:
    return _mean([s.working_time_seconds for s in sessions if s.working_time_seconds is not None])


def _student_row(u: User, score, sessions_by_student, runs_by_student, subs_by_student) -> Dict[str, Any]:
    return {
        "student_id": u.id, "username": u.username, "full_name": u.full_name, "score": score,
        "run_count": runs_by_student.get(u.id, 0),
        "submission_count": len(subs_by_student.get(u.id, [])),
        "session_count": sessions_by_student.get(u.id, 0),
    }


def _class_score(subs: List[Submission]) -> Optional[float]:
    best: Dict[uuid.UUID, float] = {}
    for s in _judged(subs):
        base = (s.judge_result or {}).get("score_base") or 100
        pct = s.score * 100 / base
        best[s.problem_id] = max(best.get(s.problem_id, 0), pct)
    return _mean(list(best.values()))


def class_statistics(db: Session, teacher: User, class_id: uuid.UUID) -> Dict[str, Any]:
    auth.authorize_class(db, teacher, class_id)
    students = repo.class_students(db, class_id)
    sessions = repo.class_sessions(db, class_id, teacher.id, [u.id for u in students])
    session_ids = [s.id for s in sessions]
    subs = repo.submissions(db, session_ids)
    sessions_by, runs_by, subs_by = _per_student_counts(sessions, subs, repo.run_counts(db, session_ids))

    rows = [_student_row(u, _class_score(subs_by.get(u.id, [])), sessions_by, runs_by, subs_by) for u in students]
    scores = [r["score"] for r in rows if r["score"] is not None]
    return {
        "class_id": class_id,
        "student_count": len(students),
        "score": {"unit": "PERCENT", "max_possible": 100, "scored_student_count": len(scores),
                  "average": _mean(scores), "distribution": _distribution(scores)},
        "submissions": _submission_summary(subs),
        "average_working_time_seconds": _average_working_time(sessions),
        "students": rows,
    }


def exam_statistics(db: Session, teacher: User, exam_id: uuid.UUID) -> Dict[str, Any]:
    auth.authorize_exam(db, teacher, exam_id)
    students = repo.exam_students(db, exam_id, teacher.id)
    sessions = repo.exam_sessions(db, exam_id, [u.id for u in students])
    session_ids = [s.id for s in sessions]
    subs = repo.submissions(db, session_ids)
    sessions_by, runs_by, subs_by = _per_student_counts(sessions, subs, repo.run_counts(db, session_ids))
    participations = repo.exam_participations(db, exam_id)
    max_total = repo.exam_max_total(db, exam_id)

    rows = []
    for u in students:
        p = participations.get(u.id)
        rows.append(_student_row(u, p.total_score if p else None, sessions_by, runs_by, subs_by))
    scores = [r["score"] for r in rows if r["score"] is not None]
    percentages = [s * 100 / max_total for s in scores] if max_total else []
    return {
        "exam_id": exam_id,
        "student_count": len(students),
        "score": {"unit": "POINTS", "max_possible": max_total, "scored_student_count": len(scores),
                  "average": _mean(scores), "distribution": _distribution(percentages)},
        "submissions": _submission_summary(subs),
        "average_working_time_seconds": _average_working_time(sessions),
        "students": rows,
    }
