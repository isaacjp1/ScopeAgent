"""v45 checks: python3 test/test_v45.py -> "all v45 checks passed" (runs the v42/v41/v40 checks too)."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ["SHIFT_SECONDS"] = "900"
from agent import config, known_set1, playbook  # noqa: E402

# 1. every confirmed Set 1 answer is in a category, and every answer code it uses is shown as a form there
for t, a in known_set1.ANSWERS.items():
    p = playbook.category(t)
    assert p, t
    if playbook._shape(a) not in ("number", "date", "text"):
        assert playbook._shape(a) in {playbook._shape(f) for f in p.forms}, (p.name, a)
plays = {p.name: p for p in playbook.PLAYS}
assert plays["recall_count"].proven and plays["recall_count"].confirmed == 13
assert all(len(p.examples) >= 1 for p in playbook.PLAYS if p.confirmed)
assert sum(p.confirmed for p in playbook.PLAYS) == len(known_set1.ANSWERS) == 180
# 2. the shift length follows the queue when SHIFT_SECONDS is missing/stale (v43 Set 3 planned for 225 tasks)
config.adopt_shift(1797)
assert config.SHIFT_SECONDS == 1800 and config.expected_tasks() == 458 and config.BUDGET == 15.0
config.adopt_shift(1790)
assert config.SHIFT_SECONDS == 1800
out = subprocess.run([sys.executable, os.path.join(HERE, "test_v42.py")], capture_output=True, text=True, timeout=900)
assert "all v42 checks passed" in out.stdout, out.stdout[-1500:] + out.stderr[-2500:]
print("all v45 checks passed")
