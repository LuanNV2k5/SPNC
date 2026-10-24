import os
import re

def fix_all():
    fname = "d:/SPNC/apps/api/tests/judge/test_scheduler_loc.py"
    with open(fname, "r") as f:
        content = f.read()

    # Fix CodingSession in _setup_cohort
    content = re.sub(
        r's = CodingSession\(student_id=u\.id, problem_id=active_session\.problem_id, language="PYTHON3", status=SessionStatus\.ACTIVE\)',
        r"attempt = __import__('app.models.session', fromlist=['PracticeAttempt']).PracticeAttempt(student_id=u.id, problem_id=active_session.problem_id)\n        db.add(attempt)\n        db.flush()\n        s = CodingSession(student_id=u.id, problem_id=active_session.problem_id, language='PYTHON3', status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id)",
        content
    )

    # Fix CodeSnapshot everywhere
    content = content.replace("source_hash='hash',", "source_hash='hash', line_count=10,")

    with open(fname, "w") as f:
        f.write(content)

fix_all()
print("Fixed")
