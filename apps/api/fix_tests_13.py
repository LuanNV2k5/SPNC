import os

def fix_all():
    fname = "d:/SPNC/apps/api/tests/judge/test_scheduler_loc.py"
    with open(fname, "r") as f:
        lines = f.readlines()

    inside_01 = False
    inside_05 = False
    snap2_seen = False

    for i, line in enumerate(lines):
        if "def test_c_loc_01_02_qualifying_and_repeat" in line:
            inside_01 = True
            inside_05 = False
            
        if "def test_c_loc_03_small_cohort" in line:
            inside_01 = False
            
        if "def test_c_loc_05_06" in line:
            inside_05 = True
            inside_01 = False

        if inside_01 and "line_count=10" in line:
            lines[i] = line.replace("line_count=10", "line_count=30")
            
        if inside_05 and "line_count=10" in line:
            if not snap2_seen:
                lines[i] = line.replace("line_count=10", "line_count=30")
                snap2_seen = True
            else:
                lines[i] = line.replace("line_count=10", "line_count=35")

    with open(fname, "w") as f:
        f.writelines(lines)

fix_all()
print("Fixed")
