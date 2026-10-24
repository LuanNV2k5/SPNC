import os
import glob

def clean_tables():
    fixture = """
@pytest.fixture(scope="function", autouse=True)
def clean_db(db):
    from sqlalchemy import text
    db.execute(text("TRUNCATE TABLE attention_signals, coding_sessions, runs, code_snapshots, trace_events, practice_attempts, class_memberships, classes CASCADE;"))
    db.commit()
"""
    files = glob.glob("d:/SPNC/apps/api/tests/judge/test_scheduler_*.py")
    for f in files:
        with open(f, "r") as file:
            content = file.read()
        if "def clean_db(db):" not in content:
            content = content.replace('pytestmark = pytest.mark.asyncio(loop_scope="function")', 'pytestmark = pytest.mark.asyncio(loop_scope="function")\n' + fixture)
        
        # fix academic_year in Class
        content = content.replace('Class(name="CS101", owner_id=student_user.id)', 'Class(name="CS101", owner_id=student_user.id, academic_year="2026")')
        
        # fix line_count in CodeSnapshot
        content = content.replace("source_hash='hash', )", "source_hash='hash', line_count=10)")
        content = content.replace('source_hash="hash"\n    )', 'source_hash="hash",\n        line_count=10\n    )')

        with open(f, "w") as file:
            file.write(content)

clean_tables()
print("Fixed issues")
