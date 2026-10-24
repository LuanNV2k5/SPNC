import os
import re

def fix_all():
    fname = "d:/SPNC/apps/api/tests/judge/test_scheduler_cycle.py"
    with open(fname, "r") as f:
        content = f.read()

    # test_c_cycle_04_and_05_mixed_and_failure_isolation
    replace_04 = """    from app.models.session import CodingSession
    s1 = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE)
    s2 = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE)
    db.add_all([s1, s2])
    db.commit()"""
    replace_04_to = """    from app.models.session import CodingSession, PracticeAttempt
    attempt1 = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    attempt2 = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    db.add_all([attempt1, attempt2])
    db.flush()
    s1 = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=attempt1.id)
    s2 = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=attempt2.id)
    db.add_all([s1, s2])
    db.commit()"""
    content = content.replace(replace_04, replace_04_to)
    
    # test_batching_starvation
    replace_batch = """    sessions = []
    for _ in range(batch_size * 2 + 2): # 12 sessions
        sessions.append(CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE))
    
    db.add_all(sessions)
    db.commit()"""
    replace_batch_to = """    from app.models.session import PracticeAttempt
    sessions = []
    for _ in range(batch_size * 2 + 2): # 12 sessions
        attempt = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
        db.add(attempt)
        db.flush()
        sessions.append(CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id))
    
    db.add_all(sessions)
    db.commit()"""
    content = content.replace(replace_batch, replace_batch_to)

    with open(fname, "w") as f:
        f.write(content)

fix_all()
