"""Quick self-checks for v40 (no browser, no model): python3 test/test_v40.py -> "all v40 checks passed"."""
import asyncio
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from agent import known_set1, solvers  # noqa: E402
from agent.finder import names_in, name_match, active_of  # noqa: E402
from agent.kinds import Kind, fill, slots_of, templates_of  # noqa: E402
from agent.learn import parse_example, norm_answer  # noqa: E402


def check_names():
    cases = {
        "Is Judith Jackson (born 2004-11-12) new or established for Kenneth Sullivan, NP on 2028-07-20?": ("Jackson", "Judith"),
        "Next step for a lab report: Andres Salazar, Complete blood count, received 2025-01-02.": ("Salazar", "Andres"),
        "Next step on claim: Murphy, Samantha, DOB 1933-09-28, service date 2026-03-16": ("Murphy", "Samantha"),
        "Patrick Watkins is on the books for 2025-11-17 at 13:00. Do we owe them a good faith estimate, and by when?": ("Watkins", "Patrick"),
        "Tetanus for Jean García on 2024-11-23: vaccine, vaccine and TIG, or nothing?": ("García", "Jean"),
        "On 2026-12-25 there is a visit with Douglas Hughes, MD for Henry, Peter, DOB 1975-06-23, and I need new vs. established for it.": ("Henry", "Peter"),
    }
    for t, want in cases.items():
        got = names_in(t, ["Kenneth Sullivan, NP", "Douglas Hughes, MD"])
        assert got and got[0] == want, (t, got)
    assert name_match("Murphy, Teresa", "Murphy", "Teresa")
    assert name_match("García, Jean Restricted", "Garcia", "Jean")
    assert not name_match("Murphy, Tessa", "Murphy", "Teresa")
    rows = [{"name": "Torres, Laura", "path": "/patients/a", "flags": []},
            {"name": "Torres, Laura", "path": "/patients/b", "flags": ["Merged"]},
            {"name": "Torres, Laura", "path": "/patients/c", "flags": ["Test record"]}]
    active, merged = active_of(rows)
    assert [r["path"] for r in active] == ["/patients/a"] and [r["path"] for r in merged] == ["/patients/b"]


def check_templates():
    t1 = "Please decide what to do with the Complete blood count lab report received on 2026-09-07 for Christopher Garrison."
    s1 = slots_of(t1, [("Garrison", "Christopher")], {"pid": "1rv16bl911"})
    route = ["/patients/1rv16bl911/files", "/patients/1rv16bl911/files/6399vltj5s", "/patients/1rv16bl911/problems",
             "/documents?kind=lab_report&from=2026-09-07&to=2026-09-07", "/patients/1rv16bl911"]
    tm = templates_of(route, s1)
    assert "/patients/{pid}/files" in tm and "/patients/{pid}/problems" in tm and "/patients/{pid}" in tm, tm
    assert "/documents?kind=lab_report&from={d0}&to={d0}" in tm, tm
    assert not any("6399vltj5s" in t for t in tm), tm
    t2 = "Next step for a lab report: Andres Salazar, Complete blood count, received 2025-01-02."
    s2 = slots_of(t2, [("Salazar", "Andres")], {"pid": "5abc12def0"})
    assert fill("/patients/{pid}/problems", s2) == "/patients/5abc12def0/problems"
    assert fill("/documents?kind=lab_report&from={d0}&to={d0}", s2) == "/documents?kind=lab_report&from=2025-01-02&to=2025-01-02"
    t3 = "How many patients are left to notify about the recall of lot C482FU1?"
    s3 = slots_of(t3)
    tm3 = templates_of(["/vaccines?lot=C482FU1", "/vaccines/notes?words=C482FU1", "/vaccines/lots/4v8gwfs1fl"], s3)
    assert tm3 == ["/vaccines?lot={c0}", "/vaccines/notes?words={c0}"], tm3
    assert fill(tm3[1], slots_of("Recall, lot 5NF133C: patients left to notify?")) == "/vaccines/notes?words=5NF133C"
    t4 = "How many scheduled appointments does Amy Fuller, NP have on 2026-11-10, at any location?"
    s4 = slots_of(t4, [], {"prov": "4f92h3w37f"})
    tm4 = templates_of(["/schedule/appointments?start=2026-11-10&end=2026-11-10&provider=4f92h3w37f&status=1"], s4)
    assert tm4 == ["/schedule/appointments?start={d0}&end={d0}&provider={prov}&status=1"], tm4


def check_invoice():
    class S:
        found_cache = {}

        async def read(self, path, fresh=False, all_pages=True):
            if path.startswith("/billing/accounts"):
                return {"text": "x", "tables": [{"headers": ["Invoice", "Service date", "Location", "Issued", "Total", "Status", "Filed under"],
                                                 "rows": [{"cells": ["32208721", "Mar 13, 2025", "Riverbend", "Mar 19, 2025", "$109.63", "Partly paid", ""],
                                                           "links": [["", "/billing/invoices/6p1hlc7vj5"]]}]}]}
            return {"text": "Invoices\nInvoice 32208721\n\nDetails\nStatus\nPartly paid\nLedger",
                    "tables": [{"headers": ["Date", "Description", "Charges", "Payments and adjustments"], "rows": [
                        {"cells": ["Mar 19, 2025", "Charge for services on Mar 13, 2025", "$109.63", ""], "links": []},
                        {"cells": ["Mar 22, 2025", "Payment received", "", "$61.27"], "links": []},
                        {"cells": ["Amount owed", "$48.36"], "links": []}]}]}

    class F:
        site = S()
        rules = None
    t = ("What's still owed on invoice 32208721 (patient Abigail Gardner, service date 2025-03-13), in dollars? Still owed "
         "means the amount billed minus the payments received, and a voided invoice owes nothing.")
    F.site.found_cache[t] = {"path": "/patients/727f4jkp5x", "paths": ["/patients/727f4jkp5x"], "flags": [], "name": "Gardner, Abigail"}
    res = asyncio.run(solvers.invoice_owed(F, t))
    assert res and res[1] == "48.36", res


def check_examples():
    rule = open(os.path.join(HERE, "set1_claim_rule.md")).read()
    req, ans = parse_example(rule)
    assert req.startswith("Next step on claim: Coleman, Linda") and ans == "APPEAL:2026-12-15", (req, ans)
    assert norm_answer("48.36") == norm_answer(48.36) and norm_answer("appeal:2026-12-15") == norm_answer("APPEAL:2026-12-15")


def check_table():
    assert len(known_set1.ANSWERS) == 180 and len(known_set1.KNOWN_IDS) == 200
    assert known_set1.unknown_left("i239") == 0   # v58: i240 is looked up


def check_policy():
    for args in (["900", "226"], ["1800", "458"], ["3600", "924"]):
        out = subprocess.run([sys.executable, os.path.join(HERE, "sim_policy.py"), *args], capture_output=True, text=True).stdout
        reached = int(out.split("reached ")[1].split(",")[0])
        assert reached >= int(args[1]) - 2, out


if __name__ == "__main__":
    check_names()
    check_templates()
    check_invoice()
    check_examples()
    check_table()
    check_policy()
    print("all v40 checks passed")
