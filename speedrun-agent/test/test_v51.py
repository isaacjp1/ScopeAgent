"""v51 checks: python3 test/test_v51.py -> "all v51 checks passed" (runs the v50..v40 checks too)."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ["SHIFT_SECONDS"] = "1800"
from agent import config, playbook  # noqa: E402
from agent.kinds import Kind, Kinds  # noqa: E402
from agent.main import Policy  # noqa: E402
from agent.rules import Rules  # noqa: E402

plays = {p.name: p for p in playbook.PLAYS}
def kinds_with(rate, tries=40):
    k = Kind("c:lab", play=plays["lab"]); k.tries, k.answers, k.seen = tries, int(rate * tries), tries
    return {"lab": k}
# 1. a set whose tries mostly fail (Set 3) keeps ~3 s per remaining task back; a set like Set 2 keeps 0.6 s
hard, easy = Policy(kinds_with(0.15)), Policy(kinds_with(0.45))
assert hard.hard_set() and not easy.hard_set()
assert abs(hard.reserve_for(1500, 400) - 399 * min(config.SPREAD_RESERVE, 1500 / 400 - config.SPREAD_SLACK)) < 1e-6
hard.spread_per = None
assert abs(easy.reserve_for(1500, 400) - 399 * config.SKIP_COST) < 1e-6
assert abs(Policy(kinds_with(0.15)).reserve_for(800, 40) - 39 * config.SKIP_COST) < 1e-6   # roomy: no spreading
# with the spread reserve fixed once, a try happens only when the slack above it covers the try
hard.spread_per = None
hard.reserve_for(1800, 458)                       # set once: ~3 s per remaining task
k = hard.kinds["lab"]; k.last_try_seen = k.seen
assert hard.decide(k, 1200, 400, False, True)[0] in ("skip", "fast-only")   # slack ~3 s: no model try
assert hard.decide(k, 1200, 400, True, True)[0] == "fast-only"              # a code path still runs
assert hard.decide(k, 1260, 400, False, True)[0] == "normal"                # slack ~63 s: a try
# 2. a kind no category fits keeps pages its unanswered tries opened twice
kinds = Kinds(Rules(None))
w = kinds.of("Please tally the widget forms for Bob Ray, DOB 1990-01-01")
assert w.play is None
for _ in range(2):
    kinds.learn_pages(w, ["/patients/p1/forms", "/patients/p1/notes"], {"pid": "p1"})
assert "/patients/{pid}/forms" in w.templates()
out = subprocess.run([sys.executable, os.path.join(HERE, "test_v50.py")], capture_output=True, text=True, timeout=900)
assert "all v50 checks passed" in out.stdout, out.stdout[-1500:] + out.stderr[-2500:]
print("all v51 checks passed")
