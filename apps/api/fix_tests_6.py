import os

def fix_all():
    # 1. Fix materializer.py SignalStatus.NEW
    fname = "d:/SPNC/apps/api/app/services/judge/materializer.py"
    with open(fname, "r") as f:
        content = f.read()
    
    content = content.replace("SignalStatus.UNREAD", "SignalStatus.NEW")
    
    with open(fname, "w") as f:
        f.write(content)
        
    # 2. Fix len([]) assert in test_c_idle_01_active_threshold_crossed (why did it fail before? because materializer crashed on UNREAD)
    # So fixing UNREAD to NEW should make materializer succeed and return True!
    # And len(signals) == 1 will pass!

fix_all()
print("Fixed")
