"""Simulates the v40 time policy on a set (no site, no model): kinds with a hidden success chance and time per try.
Checks that every task is reached and shows where the time goes.  python test/sim_policy.py 1800 458"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
shift, n = float(sys.argv[1]), int(sys.argv[2])
os.environ["SHIFT_SECONDS"] = str(int(shift))
from agent import config  # noqa: E402
from agent.kinds import Kind  # noqa: E402
from agent.main import Policy  # noqa: E402

random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
# (share of tasks, chance a try answers, seconds an answering try takes, has a deterministic path)
KINDS = [(0.12, 0.8, 4, True), (0.10, 0.7, 7, False), (0.10, 0.5, 9, False), (0.08, 0.0, 0, False),
         (0.08, 0.6, 6, False), (0.08, 0.0, 0, False), (0.07, 0.4, 10, False), (0.07, 0.9, 3, True),
         (0.06, 0.0, 0, True), (0.06, 0.3, 12, False), (0.05, 0.7, 5, False), (0.05, 0.0, 0, False),
         (0.04, 0.5, 8, False), (0.04, 0.0, 0, False)]
order = random.choices(range(len(KINDS)), weights=[k[0] for k in KINDS], k=n)
kinds = {i: Kind(f"k{i}") for i in range(len(KINDS))}
pol = Policy()
t, answered, reached, modes = 0.0, 0, 0, {}
for j, ki in enumerate(order):
    left = shift - config.SAFETY_SECONDS - t
    if left <= 0.5:
        break
    reached += 1
    k = kinds[ki]
    k.seen += 1
    share, p, secs, fast = KINDS[ki]
    mode, cap = pol.decide(k, left, n - j, fast, True)
    cap = min(cap, config.TASK_HARD_MAX, left)
    modes[mode] = modes.get(mode, 0) + 1
    if mode == "skip" or cap < 1:
        t += 0.05
        continue
    ok = random.random() < p and secs <= cap
    spent = secs if ok else cap
    if mode == "fast-only":
        ok, spent = (fast and random.random() < p), min(cap, 2.0)
    t += spent + 0.1
    if mode == "explore":
        pol.explore_spent += spent
    if mode in ("normal", "explore", "quick"):
        k.tries += 1
        k.last_try_seen = k.seen
        if mode == "explore":
            k.explores += 1
    if ok:
        k.answers += 1
        k.ans_secs.append(spent)
        answered += 1
print(f"shift {shift:.0f}s, {n} tasks: reached {reached}, answered {answered}, time used {t:.0f}s, "
      f"explore {pol.explore_spent:.0f}s, modes {modes}")
for i, k in kinds.items():
    print(f"  k{i} p={KINDS[i][1]} seen {k.seen} tries {k.tries} answered {k.answers} explores {k.explores}")
