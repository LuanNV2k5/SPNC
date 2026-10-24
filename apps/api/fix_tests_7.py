import os

def fix_all():
    # Fix test_scheduler_loc.py ck_coding_sessions_context_exclusive
    fname = "d:/SPNC/apps/api/tests/judge/test_scheduler_loc.py"
    with open(fname, "r") as f:
        content = f.read()
    
    replace_from = """        sess = CodingSession(
            student_id=u.id,
            problem_id=active_session.problem_id,
            language="PYTHON3",
            status=SessionStatus.ACTIVE
        )"""
    replace_to = """        from app.models.session import PracticeAttempt
        attempt = PracticeAttempt(student_id=u.id, problem_id=active_session.problem_id)
        db.add(attempt)
        db.flush()
        sess = CodingSession(
            student_id=u.id,
            problem_id=active_session.problem_id,
            language="PYTHON3",
            status=SessionStatus.ACTIVE,
            practice_attempt_id=attempt.id
        )"""
    content = content.replace(replace_from, replace_to)
    
    # Fix print in test_c_idle_01
    fname = "d:/SPNC/apps/api/tests/judge/test_scheduler_idle.py"
    with open(fname, "r") as f:
        content2 = f.read()
    
    content2 = content2.replace("metrics = run_cycle(db, since_dt)", "metrics = run_cycle(db, since_dt)\n    print('IDLE METRICS:', metrics)")
    with open(fname, "w") as f:
        f.write(content2)

    with open("d:/SPNC/apps/api/tests/judge/test_scheduler_loc.py", "w") as f:
        f.write(content)

fix_all()
print("Fixed")
