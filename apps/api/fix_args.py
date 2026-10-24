import os

def fix_loc():
    fpath = "d:/SPNC/apps/api/tests/judge/test_scheduler_loc.py"
    with open(fpath, "r") as f:
        content = f.read()
    content = content.replace("CodeSnapshot(", "CodeSnapshot(reason='RUN', language='PYTHON3', source_hash='hash', ")
    with open(fpath, "w") as f:
        f.write(content)

def fix_concurrency():
    fpath = "d:/SPNC/apps/api/tests/judge/test_scheduler_concurrency.py"
    with open(fpath, "r") as f:
        content = f.read()
    
    replace_from = """        s = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE)"""
    
    replace_to = """        from app.models.session import PracticeAttempt
        attempt = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
        db.add(attempt)
        db.commit()
        s = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id)"""
    
    content = content.replace(replace_from, replace_to)
    
    # Also fix "assert 0 == 1" that I saw in the traceback for test_c_restart_safe, I don't remember putting that there. Ah wait, it was `assert len(signals) == 1` but `signals` was empty so 0 == 1.
    with open(fpath, "w") as f:
        f.write(content)

fix_loc()
fix_concurrency()
print("Fixed")
