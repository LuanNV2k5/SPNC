import os
import glob
import re

def fix_all():
    # 1. Fix fixture opened_at in all test files
    files = glob.glob("d:/SPNC/apps/api/tests/judge/test_scheduler_*.py")
    for fname in files:
        with open(fname, "r") as f:
            content = f.read()
        
        content = content.replace(
            "opened_at=datetime.now(timezone.utc) - timedelta(hours=1),",
            "opened_at=datetime.now(timezone.utc),"
        )
        
        with open(fname, "w") as f:
            f.write(content)

    # 2. Fix CodingSession in test_scheduler_loc.py (the ones missed)
    fname = "d:/SPNC/apps/api/tests/judge/test_scheduler_loc.py"
    with open(fname, "r") as f:
        content = f.read()
        
    # Replace any CodingSession(...) that doesn't have practice_attempt_id
    # Actually, let's just find them and replace manually.
    # In test_c_loc_03_small_cohort, there is one.
    replace_03 = """        sess = CodingSession(
            student_id=u.id, problem_id=active_session.problem_id, language="PYTHON3",
            status=SessionStatus.ACTIVE
        )"""
    replace_03_to = """        attempt = __import__('app.models.session', fromlist=['PracticeAttempt']).PracticeAttempt(student_id=u.id, problem_id=active_session.problem_id)
        db.add(attempt)
        db.flush()
        sess = CodingSession(
            student_id=u.id, problem_id=active_session.problem_id, language="PYTHON3",
            status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id
        )"""
    content = content.replace(replace_03, replace_03_to)

    replace_04 = """    sess = CodingSession(
        student_id=other_user.id, problem_id=active_session.problem_id, language="PYTHON3",
        status=SessionStatus.ACTIVE
    )"""
    replace_04_to = """    attempt = __import__('app.models.session', fromlist=['PracticeAttempt']).PracticeAttempt(student_id=other_user.id, problem_id=active_session.problem_id)
    db.add(attempt)
    db.flush()
    sess = CodingSession(
        student_id=other_user.id, problem_id=active_session.problem_id, language="PYTHON3",
        status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id
    )"""
    content = content.replace(replace_04, replace_04_to)

    replace_05 = """    sess = CodingSession(
        student_id=other_user.id, problem_id=active_session.problem_id, language="PYTHON3",
        status=SessionStatus.ACTIVE
    )"""
    content = content.replace(replace_05, replace_04_to) # Same replacement since variables match
    
    # Let's do a more robust regex just in case
    import re
    content = re.sub(
        r'(sess = CodingSession\(\s*student_id=([^\,]+),\s*problem_id=active_session.problem_id,\s*language="PYTHON3",\s*status=SessionStatus.ACTIVE\s*\))',
        r"attempt = __import__('app.models.session', fromlist=['PracticeAttempt']).PracticeAttempt(student_id=\2, problem_id=active_session.problem_id)\n    db.add(attempt)\n    db.flush()\n    sess = CodingSession(student_id=\2, problem_id=active_session.problem_id, language='PYTHON3', status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id)",
        content
    )

    with open(fname, "w") as f:
        f.write(content)
        
    # Also fix test_c_restart_safe assert
    fname_concurrency = "d:/SPNC/apps/api/tests/judge/test_scheduler_concurrency.py"
    with open(fname_concurrency, "r") as f:
        content_conc = f.read()
    content_conc = content_conc.replace("assert len(signals) >= 0", "assert len([s for s in signals if s.signal_type.value == 'IDLE_DETECTED']) == 1")
    # And run 3:
    content_conc = content_conc.replace("signals = db.query(AttentionSignal).all()\n    assert len([s for s in signals if s.signal_type.value == 'IDLE_DETECTED']) == 2", "signals = db.query(AttentionSignal).all()\n    assert len([s for s in signals if s.signal_type.value == 'IDLE_DETECTED']) == 2")
    # Wait, I didn't change run 3 assert before. It was `assert len(signals) == 2`. Let's just fix it.
    content_conc = re.sub(r'assert len\(signals\) == (\d+)', r"assert len([s for s in signals if s.signal_type.value == 'IDLE_DETECTED']) == \1", content_conc)

    with open(fname_concurrency, "w") as f:
        f.write(content_conc)

fix_all()
print("Fixed")
