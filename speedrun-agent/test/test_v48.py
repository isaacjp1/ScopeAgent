"""v48 checks: python3 test/test_v48.py -> "all v48 checks passed" (runs the v47..v40 checks too)."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ["SHIFT_SECONDS"] = "1800"
from agent import config, playbook  # noqa: E402
from agent.kinds import Kind  # noqa: E402
from agent.main import Policy  # noqa: E402

plays = {p.name: p for p in playbook.PLAYS}
# 1. the floor: on a hard set every kind has failed a lot; the best ones still get full tries (v47 went dark)
kinds = {}
for name, tries, answers in [("lab", 20, 3), ("invoice_owed", 15, 4), ("claim_next_step", 20, 1), ("tetanus", 9, 0)]:
    k = Kind("c:" + name, play=plays[name])
    k.seen, k.tries, k.answers, k.secs = tries + 10, tries, answers, tries * 12.0
    k.ans_secs = [11.0] * answers
    k.last_try_seen = k.seen    # tried just now: no periodic retry due
    kinds[name] = k
pol = Policy(kinds)
modes = {n: pol.decide(k, 900, 300, False, True)[0] for n, k in kinds.items()}
assert modes["invoice_owed"] == "normal" and modes["lab"] == "normal", modes      # top two by answers per second
assert modes["tetanus"] in ("skip", "fast-only"), modes                         # no answers, many tries: off
os.environ["FLOOR_KINDS"] = "0"
# 2. roomy time (Set 1 with the 180-answer table: ~15 s per remaining task) lets a try run past REPLAY_MAX
k = Kind("c:lab", play=plays["lab"]); k.seen = 1
mode, cap = Policy({"lab": k}).decide(k, 880, 59, False, True)
assert mode == "normal" and cap > config.REPLAY_MAX, (mode, cap)
# 3. tight sets drop off-track tries at once; volatile pages keep the short cache
assert config.EARLY_EXIT and config.TIGHT_FAIR == 6 and config.CACHE_SECONDS == 240
out = subprocess.run([sys.executable, os.path.join(HERE, "test_v47.py")], capture_output=True, text=True, timeout=900)
assert "all v47 checks passed" in out.stdout, out.stdout[-1500:] + out.stderr[-2500:]
print("all v48 checks passed")
