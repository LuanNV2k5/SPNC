import os
import glob

def fix_all():
    # Fix TraceEvent canonical_fingerprint
    for fname in ["d:/SPNC/apps/api/tests/judge/test_scheduler_idle.py", "d:/SPNC/apps/api/tests/judge/test_scheduler_fast.py", "d:/SPNC/apps/api/tests/judge/test_scheduler_concurrency.py"]:
        with open(fname, "r") as f:
            content = f.read()
        content = content.replace("sequence_number=1,\n", "sequence_number=1,\n        canonical_fingerprint='fp1',\n")
        with open(fname, "w") as f:
            f.write(content)
            
    # Fix upload_code_snapshot
    fname = "d:/SPNC/apps/api/tests/judge/test_scheduler_rf.py"
    with open(fname, "r") as f:
        content = f.read()
    content = content.replace("storage_adapter.upload_code_snapshot(snap.object_key, b", "storage_adapter.upload_code_snapshot(str(session_id), 1, b")
    with open(fname, "w") as f:
        f.write(content)

    # Fix LOC tests
    fname = "d:/SPNC/apps/api/tests/judge/test_scheduler_loc.py"
    with open(fname, "r") as f:
        content = f.read()
    content = content.replace("UserRole", "RoleEnum")
    content = content.replace('db.add(cls)\n    db.add(ClassMembership', 'db.add(cls)\n    db.flush()\n    db.add(ClassMembership')
    content = content.replace("storage_adapter.upload_code_snapshot(snap.object_key, b", "storage_adapter.upload_code_snapshot(str(active_session.id), 1, b")
    content = content.replace("storage_adapter.upload_code_snapshot(snap1.object_key, b", "storage_adapter.upload_code_snapshot(str(active_session.id), 1, b")
    content = content.replace("storage_adapter.upload_code_snapshot(snap2.object_key, b", "storage_adapter.upload_code_snapshot(str(active_session.id), 2, b")
    # For cohort, we used sess.id:
    # "test/{uuid.uuid4()}" -> actually it's fine for object_key but storage adapter takes session_id
    content = content.replace("storage_adapter.upload_code_snapshot(snap.object_key, b", "storage_adapter.upload_code_snapshot(str(sess.id), 1, b")
    
    with open(fname, "w") as f:
        f.write(content)
        
    # Why is test_c_restart_safe and race failing?
    # Because active_session in fix_args.py is not committed properly? 
    # Or maybe evaluate_idle_detected is failing silently?
    # Let's fix test_c_restart_safe to use print to debug if it still fails.
    
fix_all()
print("Fixed")
