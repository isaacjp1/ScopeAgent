"""v50 checks: python3 test/test_v50.py -> "all v50 checks passed" (runs the v48..v40 checks too)."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from agent import config, known_set1, playbook  # noqa: E402
from agent.kinds import Kind  # noqa: E402
from agent.main import Policy  # noqa: E402

assert len(known_set1.ANSWERS) == 180 and len(known_set1.KNOWN_IDS) == 200   # v58: +20 looked up only
plays = {p.name: p for p in playbook.PLAYS}
lab = Kind("c:lab", play=plays["lab"]); lab.seen, lab.tries, lab.answers = 20, 15, 0   # failing a lot
pol = Policy({"lab": lab})
# Set 1 mode: 44 unknown tasks left, 860 s: a real try with the fair share, never switched off
mode, cap = pol.decide_set1(lab, 860, 44, False, True)
assert mode == "normal" and 18 <= cap <= config.SET1_MAX, (mode, cap)
# leftovers roll forward: fewer tasks for the same time -> longer tries, capped
assert pol.decide_set1(lab, 860, 10, False, True)[1] == config.SET1_MAX
# near the end it still leaves the reserve for the tasks after it
mode, cap = pol.decide_set1(lab, 30, 40, False, True)
assert mode in ("fast-only", "skip") or cap <= 30 - 39 * config.SKIP_COST + 0.01, (mode, cap)
# a kind Set 1 never answered: one exploring try, then off
up = Kind("c:unique_patient_count", play=plays["unique_patient_count"]); up.seen = 1
assert pol.decide_set1(up, 860, 44, False, True)[0] == "explore"
up.explores = 1
assert pol.decide_set1(up, 860, 44, False, True)[0] in ("skip", "fast-only")
out = subprocess.run([sys.executable, os.path.join(HERE, "test_v48.py")], capture_output=True, text=True, timeout=900)
assert "all v48 checks passed" in out.stdout, out.stdout[-1500:] + out.stderr[-2500:]
print("all v50 checks passed")
