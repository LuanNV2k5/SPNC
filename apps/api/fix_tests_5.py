import os
import glob

def fix_all():
    # 1. Truncate users too
    files = glob.glob("d:/SPNC/apps/api/tests/judge/test_scheduler_*.py")
    for fname in files:
        with open(fname, "r") as f:
            content = f.read()
        content = content.replace("class_memberships, classes CASCADE", "class_memberships, classes, users CASCADE")
        with open(fname, "w") as f:
            f.write(content)
            
    # 2. Fix materializer.py
    fname = "d:/SPNC/apps/api/app/services/judge/materializer.py"
    with open(fname, "r") as f:
        content = f.read()
    
    replace_from = """    stmt = insert(AttentionSignal).values(
        id=signal.id or __import__("uuid").uuid4(),
        session_id=signal.session_id,
        student_id=signal.student_id,
        signal_type=signal.signal_type,
        status=signal.status,
        detected_at=signal.detected_at,
        rule_version=signal.rule_version,
        evidence=signal.evidence,
        dedup_key=signal.dedup_key,
    ).on_conflict_do_nothing(index_elements=["dedup_key"])
    
    result = db.execute(stmt)
    db.commit()
    return result.rowcount > 0"""

    replace_to = """    from app.models.observation import SignalStatus
    import datetime
    
    stmt = insert(AttentionSignal).values(
        id=signal.id or __import__("uuid").uuid4(),
        session_id=signal.session_id,
        student_id=signal.student_id,
        signal_type=signal.signal_type,
        status=signal.status or SignalStatus.UNREAD,
        detected_at=signal.detected_at or datetime.datetime.now(datetime.timezone.utc),
        rule_version=signal.rule_version,
        evidence=signal.evidence,
        dedup_key=signal.dedup_key,
    ).on_conflict_do_nothing(index_elements=["dedup_key"])
    
    try:
        result = db.execute(stmt)
        db.commit()
        return result.rowcount > 0
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to materialize signal {signal.dedup_key}: {e}")
        return False"""
    
    content = content.replace(replace_from, replace_to)
    
    with open(fname, "w") as f:
        f.write(content)

fix_all()
print("Fixed")
