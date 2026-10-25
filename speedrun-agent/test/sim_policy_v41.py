"""Simulates the v41 time policy (no site, no model) on each set's size with Set 1's category mix.
Per category: (share of tasks, chance a try answers, seconds an answering try takes, deterministic path exists).
The chances are guesses from v40's Set 1/2 runs; the point is that every task is reached and that the seeded
kinds are not written off as a block.   python3 test/sim_policy_v41.py [seed]"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

MIX = {   # category: (share, p answer, secs, fast)
    "lab": (0.20, 0.45, 9, True), "claim_next_step": (0.17, 0.45, 8, True), "invoice_owed": (0.10, 0.6, 6, True),
    "phone": (0.09, 0.85, 4, True), "provider_appt_count": (0.07, 0.5, 7, True), "filing_deadline": (0.06, 0.6, 6, True),
    "recall_count": (0.06, 0.1, 15, False), "good_faith_estimate": (0.06, 0.3, 10, False), "tetanus": (0.05, 0.4, 10, False),
    "referral": (0.045, 0.9, 4, True), "open_slots": (0.04, 0.8, 4, True), "unique_patient_count": (0.035, 0.0, 0, False),
    "completed_visit_count": (0.015, 0.5, 7, True), "top_providers": (0.005, 0.0, 0, False),
}


def sim(shift, n, seed):
    os.environ["SHIFT_SECONDS"] = str(int(shift))
    import importlib
    from agent import config
    importlib.reload(config)
    from agent import main as M
    importlib.reload(M)
    from agent import playbook
    from agent.kinds import Kind
    plays = {p.name: p for p in playbook.PLAYS}
    rnd = random.Random(seed)
    names = list(MIX)
    order = rnd.choices(names, weights=[MIX[c][0] for c in names], k=n)
    kinds = {c: Kind("c:" + c, play=plays[c]) for c in names}
    pol = M.Policy(kinds)
    t, answered, reached, modes = 0.0, 0, 0, {}
    for j, c in enumerate(order):
        left = shift - config.SAFETY_SECONDS - t
        if left <= 0.5:
            break
        reached += 1
        k = kinds[c]
        k.seen += 1
        share, p, secs, fast = MIX[c]
        mode, cap = pol.decide(k, left, n - j, fast, True)
        cap = min(cap, config.TASK_HARD_MAX, left)
        modes[mode] = modes.get(mode, 0) + 1
        if mode == "skip" or cap < 1:
            t += 0.05
            continue
        jitter = secs * rnd.uniform(0.7, 1.4)
        ok = rnd.random() < p and jitter <= cap
        spent = jitter if ok else cap
        if mode == "fast-only":
            ok, spent = (fast and rnd.random() < p * 0.4), min(cap, 2.5)
        t += spent + 0.1
        if mode == "explore":
            pol.explore_spent += spent
        if mode in ("normal", "explore", "quick"):
            k.tries += 1
            k.secs += spent
            k.last_try_seen = k.seen
            if mode == "explore":
                k.explores += 1
        if ok:
            if mode == "fast-only":
                k.tries += 1
            k.answers += 1
            k.ans_secs.append(spent)
            answered += 1
    print(f"shift {shift:.0f}s, {n} tasks: reached {reached}, answered {answered}, time used {t:.0f}s, "
          f"explore {pol.explore_spent:.0f}s, modes {modes}")
    for c, k in kinds.items():
        print(f"   {c:22s} seen {k.seen:3d} tries {k.tries:3d} answered {k.answers:3d}")


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    for shift, n in ((900, 114), (900, 226), (1800, 458), (3600, 924)):
        sim(shift, n, seed)
