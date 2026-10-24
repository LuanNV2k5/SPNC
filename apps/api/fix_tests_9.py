import os

def fix_all():
    fname = "d:/SPNC/apps/api/tests/judge/test_scheduler_loc.py"
    with open(fname, "r") as f:
        content = f.read()
        
    # Replace CodingSession in _setup_cohort
    replace_cohort = """        sess = CodingSession(
            student_id=u.id, problem_id=active_session.problem_id, language="PYTHON3",
            status=SessionStatus.ACTIVE
        )"""
    replace_cohort_to = """        attempt = __import__('app.models.session', fromlist=['PracticeAttempt']).PracticeAttempt(student_id=u.id, problem_id=active_session.problem_id)
        db.add(attempt)
        db.flush()
        sess = CodingSession(
            student_id=u.id, problem_id=active_session.problem_id, language="PYTHON3",
            status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id
        )"""
    content = content.replace(replace_cohort, replace_cohort_to)

    # For 04 and 05_06, let's just do a blanket regex that catches all CodingSession(...) missing practice_attempt_id
    import re
    content = re.sub(
        r'sess = CodingSession\(\s*student_id=([a-zA-Z0-9_\.]+),\s*problem_id=active_session\.problem_id,\s*language="PYTHON3",\s*status=SessionStatus\.ACTIVE\s*\)',
        r"attempt = __import__('app.models.session', fromlist=['PracticeAttempt']).PracticeAttempt(student_id=\1, problem_id=active_session.problem_id)\n    db.add(attempt)\n    db.flush()\n    sess = CodingSession(student_id=\1, problem_id=active_session.problem_id, language='PYTHON3', status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id)",
        content
    )

    # Replace CodeSnapshot missing line_count
    # In test_c_loc_03_small_cohort, there is CodeSnapshot(session_id=sess.id, object_key=..., created_at=..., reason="RUN", language="PYTHON3", source_hash="hash")
    # Let's replace "hash") with "hash", line_count=10)
    content = content.replace('source_hash="hash"\n    )', 'source_hash="hash", line_count=10\n    )')
    content = content.replace("source_hash='hash', )", "source_hash='hash', line_count=10)")
    content = content.replace('source_hash="hash")', 'source_hash="hash", line_count=10)')

    with open(fname, "w") as f:
        f.write(content)

    # Fix assert in test_scheduler_concurrency.py
    fname_conc = "d:/SPNC/apps/api/tests/judge/test_scheduler_concurrency.py"
    with open(fname_conc, "r") as f:
        content = f.read()
    
    content = content.replace(".value == 'IDLE_DETECTED'", " == 'IDLE_DETECTED' or s.signal_type == __import__('app.models.observation', fromlist=['SignalType']).SignalType.IDLE_DETECTED")
    
    with open(fname_conc, "w") as f:
        f.write(content)

fix_all()
print("Fixed")
