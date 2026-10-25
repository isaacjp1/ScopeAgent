"""Self-checks for v42 (no browser, no model): python3 test/test_v42.py -> "all v42 checks passed".
One check per bug found in v41's review, then the good-faith-estimate path, then every v41 and v40 check."""
import asyncio
import contextlib
import csv
import datetime as dt
import glob
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from agent import known_set1, playbook, solvers  # noqa: E402
from agent.brain import Brain, appt_when, text_matches_patient  # noqa: E402
from agent.kinds import Kinds  # noqa: E402
from agent.rules import Rules  # noqa: E402

TASKS = list(csv.DictReader(open(os.path.join(HERE, "set1", "set1_tasks.csv"))))
RULE_TEXTS = [re.sub(r"<!--.*?-->\n", "", open(f).read())
              for f in sorted(glob.glob(os.path.join(HERE, "set1", "set1_rules", "*.md")))]


class R:
    items = RULE_TEXTS


def quiet(coro):
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(coro)


def check_lab_person_not_panel():
    """v41 bug: 'the Billy Nguyen lab report' read 'Billy Nguyen' as a panel -> NOT_COVERED (a sure -1)."""
    class F:
        rules = R
    for t in ["What happens to the Billy Nguyen lab report received 2025-07-05?",
              "Next step for the Mary Ann Lopez lab report, received 2026-01-01.",
              "Next step for a lab report: Lipid panel, Billy Nguyen, received 2025-07-05.",
              "What happens to the Test Patient lab report received 2025-07-05?"]:
        assert quiet(solvers.lab_not_covered(F, t)) is None, t
    for t in ["What happens to the Hemoglobin A1c lab report for Bob Ray, received 2026-01-01?",
              "What happens to the Lipid panel lab report for Patricia Butler (born 1983-05-16), received 2025-09-21?",
              "Next step for a lab report: Billy Nguyen, Lipid panel, received 2025-07-05."]:
        res = quiet(solvers.lab_not_covered(F, t))
        assert res and res[1] == "NOT_COVERED", t


def check_image_only_when_needed():
    f = {"name": "Nguyen, Billy", "dob": "03/04/1990", "path": "/patients/x"}
    body = " Complete blood count Hemoglobin 13.1 g/dL Platelet count 250 " * 5
    assert text_matches_patient("Patient: NGUYEN, BILLY DOB: 03/04/1990" + body, f)
    assert text_matches_patient("Patient: Nguyen, Billy  Date of birth: Mar 4, 1990" + body, f)
    assert not text_matches_patient("Patient: Nguyen, Billy DOB 1991-03-04" + body, f)     # another DOB: a trap layer
    assert not text_matches_patient("Patient: Smith, Ann DOB 1990-03-04" + body, f)        # another name
    assert not text_matches_patient("Patient: Nguyen, Billy" + body, None)                 # nothing to check against
    assert text_matches_patient("Patient: Nguyen, Billy" + body, {**f, "dob": ""}, "Billy Nguyen, born 1990-03-04") is False
    assert text_matches_patient("Patient: Nguyen, Billy 1990-03-04" + body, {**f, "dob": ""}, "Billy Nguyen, born 1990-03-04")


def check_codes_scope():
    rules = Rules(None)
    rules.items += RULE_TEXTS
    b = Brain.__new__(Brain)
    b.rules = rules
    kinds = Kinds(rules)
    lab = kinds.of("What happens to the Complete blood count lab report for A B (born 2000-01-01), received 2026-01-01?")
    ref = kinds.of("Referral letter received on 2025-03-18 for patient Joseph Tucker (born 1985-10-13): which practice made the referral?")
    assert b.known_code("NURSE_REVIEW:2", lab) and not b.known_code("NEEDS_REVIEW:2", lab)
    assert not b.known_code("ESCALATE", lab)          # a rule kind: a bare code must be the rule's
    assert b.known_code("AETNA", ref) and b.known_code("ALDER CREEK", ref)   # names in caps are not codes
    blocked = [(t[:50], a) for t, a in known_set1.ANSWERS.items() if not b.known_code(str(a), kinds.of(t))]
    assert not blocked, blocked


def check_invoice_scope():
    cases = {
        "What's the outstanding balance on invoice 55512345 for Jane Doe?": "invoice_owed",
        "How much do we still need to collect on invoice 12345678?": "invoice_owed",
        "Next step on claim: Payne, Roger, DOB 1964-04-07, service date 2026-07-16 (invoice 12345678)": "claim_next_step",
        "Could you look at the claim for Ann Lee, invoice 12345678, DOS 2026-01-01, and tell me the next step?": "claim_next_step",
    }
    for t, want in cases.items():
        assert playbook.category(t).name == want, (t, playbook.category(t).name)
    for r in TASKS:
        m = solvers.INVOICE.search(r["task"])
        assert bool(m) == (r["kind"] == "invoice_owed"), r["task"]


class FakeSite:
    def __init__(self, pages, task):
        self.pages = pages
        self.found_cache = {task: {"path": "/patients/p1", "paths": ["/patients/p1"], "flags": [], "name": "Lee, Austin"}}

    async def read(self, path, all_pages=True, fresh=False):
        return self.pages.get(path, {"path": path, "error": "not found"})


def page(path, text):
    return {"path": path, "text": text, "tables": [], "links": []}


def check_gfe():
    task = "Good faith estimate question: Lee, Austin, born 2016-05-05, 08:20 on 2026-10-27. Is one required, and if so, when's it due?"
    assert solvers.gfe_rule(R) == "NOT_REQUIRED:INSURED"
    insured = page("/patients/p1/insurance", "Insurance\nPrimary insurance\nPayer Plains Mutual\nPlan PPO\nMember ID PM1234\nCoverage ...")
    clean = page("/patients/p1/notes", "Notes\n2026-09-01 Phone call: patient asked to move the appointment to the morning.")
    paynote = page("/patients/p1/notes", "Notes\n2026-10-01 Patient will self-pay for the 10/27 visit.")
    noins = page("/patients/p1/insurance", "Insurance\nNo insurance on file\nCoverage\nPayer Plan Member ID ...")

    def run(pages, rules=R):
        class F:
            pass
        F.site, F.rules = FakeSite({p["path"]: p for p in pages}, task), rules
        return quiet(solvers.gfe_insured(F, task))
    res = run([insured, clean])
    assert res and res[1] == "NOT_REQUIRED:INSURED", res
    assert run([insured, paynote]) is None             # a payment note: the model reads it
    assert run([noins, clean]) is None                 # uninsured: the deadline needs the model
    assert run([insured]) is None                      # notes not read

    class R2:
        items = RULE_TEXTS + ["Front desk: from today, high-deductible plans also need a good faith estimate."]
    assert run([insured, clean], R2) is None           # a later message changes the rule: not sure any more
    assert appt_when(task) == (dt.date(2026, 10, 27), "08:20")
    # the appointment row of that date and time -> its page and the location's clinic calendar
    b = Brain.__new__(Brain)
    b.directory = {"prov": {}, "loc": {"eastside": "L3"}}
    appts = {"path": "/patients/p1/appointments", "text": "", "tables": [{"headers": ["Date and time", "Location"], "rows": [
        {"cells": ["Oct 27, 2026, 8:20 AM CDT", "Eastside"], "links": [("Oct 27", "/patients/p1/appointments/a1")]},
        {"cells": ["Oct 27, 2026, 3:00 PM CDT", "Eastside"], "links": [("Oct 27", "/patients/p1/appointments/a2")]},
        {"cells": ["Nov 2, 2026, 8:20 AM CST", "Eastside"], "links": [("Nov 2", "/patients/p1/appointments/a3")]}]}]}
    assert b.gfe_pages(task, [appts]) == ["/patients/p1/appointments/a1", "/settings?year=2026&location=L3"]


if __name__ == "__main__":
    check_lab_person_not_panel()
    check_image_only_when_needed()
    check_codes_scope()
    check_invoice_scope()
    check_gfe()
    out = subprocess.run([sys.executable, os.path.join(HERE, "test_v41.py")], capture_output=True, text=True, timeout=600)
    assert "all v41 checks passed" in out.stdout, out.stdout[-1500:] + out.stderr[-2500:]
    print("all v42 checks passed")
