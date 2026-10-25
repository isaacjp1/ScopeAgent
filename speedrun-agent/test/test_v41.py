"""Self-checks for v41 (no browser, no model): python3 test/test_v41.py -> "all v41 checks passed".

v41 applies Set 1's patterns to every set: each task's kind is its playbook category (agent/playbook.py). These
checks hold the playbook to Set 1: every one of its 224 tasks must land in the right category, the instant lab
coverage path must give exactly Set 1's confirmed NOT_COVERED answers and nothing else, and the time policy must
reach every task of each set's size."""
import asyncio
import contextlib
import csv
import glob
import io
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from agent import known_set1, playbook, solvers  # noqa: E402
from agent.kinds import Kinds, fill, slots_of  # noqa: E402
from agent.rules import Rules  # noqa: E402

TASKS = list(csv.DictReader(open(os.path.join(HERE, "set1", "set1_tasks.csv"))))
RULE_TEXTS = [re.sub(r"<!--.*?-->\n", "", open(f).read())
              for f in sorted(glob.glob(os.path.join(HERE, "set1", "set1_rules", "*.md")))]
RULE_POS = [int(re.search(r"/i(\d+)_", f).group(1))
            for f in sorted(glob.glob(os.path.join(HERE, "set1", "set1_rules", "*.md")))]


def check_categories():
    alias = {"referral_reason": "referral", "referral_source": "referral"}
    bad = []
    for r in TASKS:
        p = playbook.category(r["task"])
        want = alias.get(r["kind"], r["kind"])
        if (p.name if p else None) != want:
            bad.append((r["id"], want, p and p.name, r["task"][:90]))
    assert not bad, bad[:5]
    # other sets word the same requests differently: the categories must still catch them
    para = {
        "What's the outstanding balance on invoice 55512345 for Jane Doe (service date 2026-01-02)?": "invoice_owed",
        "Is a GFE needed for Lee, Austin at 08:20 on 2026-10-27?": "good_faith_estimate",
        "How many patients are left to notify about the recall of lot M81X24L?": "recall_count",
        "Can you tell me what to do next with the denied claim for Mary Poe, DOS 2026-01-02?": "claim_next_step",
        "What is the timely filing deadline for Bob Ray's claim, date of service 2026-01-01?": "filing_deadline",
        "What should we do about the Lipid panel results received 2026-01-01 for Bob Ray?": "lab",
        "Which three providers had the most completed visits in March 2026?": "top_providers",
        "How many distinct patients had at least one completed visit at Eastside in May 2026?": "unique_patient_count",
        "Who referred Anna Bell (DOB 2000-01-01)?": "referral",
        "What's the telephone on file for Bob Ray?": "phone",
        "Is Bob Ray a new or established patient for Dr X on 2026-01-01?": "new_established",
        "How many available slots does Dr X have at Eastside on 2026-01-01?": "open_slots",
        "Was tetanus immune globulin due for Bob Ray, seen 2026-01-01?": "tetanus",
        "How many completed appointments did Juan Martin, NP have on 2024-12-20?": "completed_visit_count",
    }
    for t, want in para.items():
        p = playbook.category(t)
        assert p and p.name == want, (t, p and p.name)
    for p in playbook.PLAYS:   # every worked example is filed under its own category
        for t, a, _ in p.examples:
            assert playbook.category(t).name == p.name, (p.name, t)


def check_kinds():
    rules = Rules(None)
    for t in RULE_TEXTS:
        rules.items.append(t)
    kinds = Kinds(rules)
    k1 = kinds.of("As of now, how much is still owed on invoice 42750277 (patient Paul Gray, service date 2026-06-22)?")
    k2 = kinds.of("What's still owed on invoice 83999703 (patient Henry Wong, service date 2026-03-02), in dollars?")
    assert k1 is k2 and k1.key == "c:invoice_owed" and k1.proven and k1.seeded
    lab = kinds.of("Next step for a lab report: Billy Nguyen, Complete blood count, received 2025-07-05.")
    assert lab.key == "c:lab" and "/patients/{pid}/files" in lab.templates()
    hint = kinds.hint(lab, "x")
    assert "HOW THIS KIND" in hint and "NURSE_REVIEW:2" in hint, hint[:300]
    rec = kinds.of("Could you count how many of our patients still haven't been told about the recall of vaccine lot 36JR47H?")
    assert rec.key == "c:recall_count" and rec.proven and not rec.play.patient   # v45: 9 confirmed recall answers
    s = slots_of("Could you count how many of our patients still haven't been told about the recall of vaccine lot 36JR47H?")
    assert [fill(v, s) for _, f in rec.play.searches for v in f.values()] == ["36JR47H", "36JR47H"]
    s = slots_of("What's still owed on invoice 32208721 (patient Abigail Gardner, service date 2025-03-13), in dollars?")
    assert fill(k1.play.searches[0][1]["number"], s) == "32208721"
    cnt = kinds.of("How many open slots are there for Cheryl Taylor, MD at Eastside on 2026-12-29?")
    s = slots_of("How many open slots are there for Cheryl Taylor, MD at Eastside on 2026-12-29?", ids={"prov": "p7"})
    assert [fill(t, s) for t in cnt.templates()] == ["/schedule/providers/p7?date=2026-12-29"]


def check_lab_coverage():
    """The instant lab path answers exactly the six NOT_COVERED tasks of Set 1 (all confirmed) and nothing else,
    each with only the messages received before it."""
    got = {}
    for r in TASKS:
        if not solvers.LAB.search(r["task"]):
            continue
        n = int(r["id"][1:])

        class R:
            items = [t for t, pos in zip(RULE_TEXTS, RULE_POS) if pos < n]

        class F:
            rules = R
        with contextlib.redirect_stdout(io.StringIO()):
            res = asyncio.run(solvers.lab_not_covered(F, r["task"]))
        if res:
            got[r["id"]] = res[1]
    want = {r["id"]: "NOT_COVERED" for r in TASKS if known_set1.lookup(r["task"]) == "NOT_COVERED"}
    assert got == want, (got, want)
    # a different wording of the rule: no instant answer (the model loop decides)
    class R2:
        items = [RULE_TEXTS[0].replace("Panels this rule covers", "Covered panels")]

    class F2:
        rules = R2
    with contextlib.redirect_stdout(io.StringIO()):
        assert asyncio.run(solvers.lab_not_covered(F2, "What happens to the Lipid panel lab report for A B, received 2026-01-01?")) is None


def check_codes():
    from agent.brain import Brain
    rules = Rules(None)
    rules.items += RULE_TEXTS
    b = Brain.__new__(Brain)
    b.rules = rules
    kinds = Kinds(rules)
    lab = kinds.of("What happens to the Complete blood count lab report for A B (born 2000-01-01), received 2026-01-01?")
    assert b.known_code("NURSE_REVIEW:2", lab) and b.known_code("RELEASE", lab) and b.known_code("12.50", lab)
    assert not b.known_code("NEEDS_REVIEW:2", lab) and not b.known_code("ESCALATE_TO_MD", lab)


def check_policy():
    """Set 1's category mix with guessed answer rates and times: every task of each set is reached, and the
    seeded kinds keep getting tries (v40's Set 3 wrote them off and skipped everything)."""
    out = subprocess.run([sys.executable, os.path.join(HERE, "sim_policy_v41.py")], capture_output=True, text=True,
                         timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    for line in out.stdout.splitlines():
        if line.startswith("shift"):
            m = re.search(r"(\d+) tasks: reached (\d+), answered (\d+)", line)
            assert int(m.group(2)) >= int(m.group(1)) - 1, line   # the sim's 0.1 s overhead can cost the very last one
    print(out.stdout)


def check_table():
    assert len(known_set1.ANSWERS) == 180, len(known_set1.ANSWERS)


if __name__ == "__main__":
    check_categories()
    check_kinds()
    check_lab_coverage()
    check_codes()
    check_table()
    check_policy()
    out = subprocess.run([sys.executable, os.path.join(HERE, "test_v40.py")], capture_output=True, text=True, timeout=300)
    assert "all v40 checks passed" in out.stdout, out.stdout[-1500:] + out.stderr[-1500:]
    print("all v41 checks passed")
