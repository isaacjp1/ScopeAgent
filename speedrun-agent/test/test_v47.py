"""v47 checks: python3 test/test_v47.py -> "all v47 checks passed" (runs the v45..v40 checks too)."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from agent import config, known_set1, playbook  # noqa: E402
assert len(known_set1.ANSWERS) == 180 and len(known_set1.KNOWN_IDS) == 200   # v58: +20 looked up only
assert not os.path.exists(os.path.join(HERE, "..", "agent", "lexicon.py"))   # the borrowed-dataset fallback is gone
plays = {p.name: p for p in playbook.PLAYS}
assert sum(p.confirmed for p in playbook.PLAYS) == 180
assert plays["invoice_owed"].set1_rate == 0.7 and plays["unique_patient_count"].set1_rate == 0.2
assert "RELEASE" in plays["lab"].set1_dist
assert config.REPLAY_MIN >= 12 and config.QUICK_MIN_FAIR > 50
out = subprocess.run([sys.executable, os.path.join(HERE, "test_v45.py")], capture_output=True, text=True, timeout=900)
assert "all v45 checks passed" in out.stdout, out.stdout[-1500:] + out.stderr[-2500:]
print("all v47 checks passed")
