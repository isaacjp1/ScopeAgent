"""A replica of the Set 1 clinic's pages (layouts copied from the v13 Set 1 output) to test agent/solvers.py
end to end without a submission. Run with the agent like test/mock_wrenfield.py (same ports):

    python test/mock_set1.py      # site :8811, queue :8812, model :8813
    QUEUE_URL=http://127.0.0.1:8812 SITE_URL=http://127.0.0.1:8811 LLM_BASE_URL=http://127.0.0.1:8813/v1 \
      LLM_API_KEY=x SHIFT_SECONDS=900 MODEL=fake python -m agent.main

Every expected answer below was worked out by hand from the clinic's rule text, not from the solver code.
Traps: a test record, a deleted record, a restricted chart, cancelled/no-show rows, another provider on the same
day, a provider working at another location, Thanksgiving, an end-of-month month limit, a payer with no terms
in effect, a payer that is only on the payers list (not in the coverage table)."""
import os
import sys
import time
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(__file__))
import mock_wrenfield as mw  # noqa: E402  (shell, iframe, login, queue and model servers)

PROVIDERS = [("4f92h3w37f", "Amy Fuller, NP", "Family Medicine"), ("6blkkfwwk1", "Carlos Chen, NP", "Pediatrics"),
             ("1pgb59q2cs", "Ethan Holmes, NP", "Internal Medicine"), ("3zmzhp10xn", "Vincent Perez, MD", "Cardiology")]
LOCS = [("34gtv07s8z", "Northgate"), ("4zg988xzkw", "Cedar Hollow"), ("2k2qpj5br2", "Riverbend")]
STATUS = {"1": "Scheduled", "2": "Completed", "3": "Cancelled", "4": "Late cancel", "5": "No-show"}

# id: (last, first, dob, flags shown in the patient search, chart kind)
PATS = {
    "p1": ("Rivera", "Ana", "1980-01-01", "", "normal"),
    "p2": ("Bailey", "Daniel", "1975-05-05", "Restricted", "restricted"),
    "p3": ("Larkin", "Owen", "1990-02-02", "Test record", "normal"),     # test record: only the search flag shows it
    "p4": ("Moss", "Iris", "1960-03-03", "Deleted", "gone"),             # deleted: chart page not available
    "p5": ("Nguyen", "Lan", "1988-08-08", "", "normal"),
    "p6": ("Ortiz", "Paul", "1970-07-07", "", "normal"),
    "p7": ("Quinn", "Rose", "1999-09-09", "", "normal"),
    "pa": ("Anderson", "Alexander", "1971-07-30", "", "normal"),
    "pk": ("Khan", "Kevin", "2009-11-04", "", "normal"),
}
# appointments: (date, start, end, tz, patient, provider name, location, type, status, recurring)
APPTS = [
    ("2026-11-02", "9:00 AM", "9:20 AM", "CST", "p1", "Amy Fuller, NP", "Northgate", "Office visit", "Scheduled", False),
    ("2026-11-02", "9:20 AM", "9:40 AM", "CST", "p2", "Amy Fuller, NP", "Northgate", "Follow-up visit", "Scheduled", False),
    ("2026-11-02", "9:40 AM", "10:00 AM", "CST", "p3", "Amy Fuller, NP", "Northgate", "Sick visit", "Scheduled", False),
    ("2026-11-02", "10:00 AM", "10:20 AM", "CST", "p4", "Amy Fuller, NP", "Northgate", "Office visit", "Scheduled", False),
    ("2026-11-02", "10:20 AM", "10:50 AM", "CST", "p5", "Amy Fuller, NP", "Northgate", "Diabetes management", "Scheduled", True),
    ("2026-11-02", "11:00 AM", "11:20 AM", "CST", "p7", "Amy Fuller, NP", "Northgate", "Office visit", "Cancelled", False),
    ("2026-11-02", "9:00 AM", "9:20 AM", "CST", "p6", "Vincent Perez, MD", "Riverbend", "Office visit", "Scheduled", False),
    ("2026-04-15", "8:00 AM", "8:20 AM", "CDT", "p1", "Amy Fuller, NP", "Northgate", "Office visit", "Completed", False),
    ("2026-04-15", "8:40 AM", "9:00 AM", "CDT", "p5", "Amy Fuller, NP", "Riverbend", "Office visit", "Completed", False),
    ("2026-04-15", "9:00 AM", "9:20 AM", "CDT", "p3", "Amy Fuller, NP", "Northgate", "Office visit", "Completed", False),
    ("2026-04-15", "9:20 AM", "9:40 AM", "CDT", "p7", "Amy Fuller, NP", "Northgate", "Office visit", "No-show", False),
    ("2026-07-27", "7:00 AM", "7:40 AM", "MDT", "p1", "Carlos Chen, NP", "Cedar Hollow", "Annual physical", "Completed", False),
    ("2026-07-27", "1:40 PM", "2:00 PM", "MDT", "p5", "Ethan Holmes, NP", "Cedar Hollow", "Office visit", "Completed", False),
    ("2026-07-27", "2:00 PM", "2:20 PM", "MDT", "p6", "Carlos Chen, NP", "Cedar Hollow", "Office visit", "Completed", False),
    ("2026-07-27", "9:00 AM", "9:20 AM", "MDT", "p3", "Carlos Chen, NP", "Cedar Hollow", "Office visit", "Completed", False),
    ("2026-07-27", "10:00 AM", "10:20 AM", "MDT", "p7", "Carlos Chen, NP", "Cedar Hollow", "Office visit", "Cancelled", False),
]
# provider day pages: (provider id, date) -> (location, [rows]); a row is (time, patient id or None for an open slot, status)
DAYS = {
    ("4f92h3w37f", "2026-11-02"): ("Northgate", [("8:00 AM to 8:15 AM", None, ""), ("8:15 AM to 8:30 AM", None, ""),
                                                 ("9:00 AM to 9:20 AM", "p1", "Scheduled"), ("11:00 AM to 11:20 AM", "p7", "Cancelled"),
                                                 ("11:00 AM to 11:15 AM", None, ""), ("11:45 AM to 12:00 PM", None, "")]),
    ("6blkkfwwk1", "2026-11-03"): ("Riverbend", [("8:00 AM to 8:15 AM", None, "")]),
}
NOT_FILED = {  # patient -> rows (claim, date of service, visit, type, bill to, charge, primary rem, original rem)
    "pa": [("81461576", "Aug 31, 2026", "Post-operative check", "Original", "Senior Advantage of the Plains · Senior Complete", "$114.00", "None", "None"),
           ("94175100", "Jun 22, 2026", "Office visit", "Corrected", "Meridian Mutual Health · PPO Plus", "$201.00", "None", "Jul 25, 2026"),
           ("55500001", "Sep 15, 2026", "Office visit", "Secondary", "Meridian Mutual Health · PPO Plus", "$90.00", "None", "None"),
           ("55500002", "Dec 18, 2025", "Office visit", "Original", "State Family Assistance · Family Care", "$80.00", "None", "None")],
    "pk": [("36020593", "Jan 2, 2026", "Cast check", "Original", "Meridian Mutual Health · High Deductible 5000", "$395.00", "None", "None"),
           ("36020594", "Aug 28, 2026", "Office visit", "Original", "Meridian Mutual Health · High Deductible 5000", "$120.00", "None", "None")],
}
PAYERS = {"0qnvc9fghg": ("Senior Advantage of the Plains", [("Jan 1, 2026", "6 months from the date of service", "60 days from the primary payer's remittance date", "90 days from the remittance date of the original claim")]),
          "2dtkghkdqm": ("Meridian Mutual Health", [("Apr 1, 2026", "90 days from the date of service", "90 days from the primary payer's remittance date", "90 days from the remittance date of the original claim"),
                                                    ("Jan 1, 2023", "120 days from the date of service", "60 days from the primary payer's remittance date", "180 days from the remittance date of the original claim")]),
          "2nkr8glvbt": ("State Family Assistance", [("Jan 1, 2026", "9 months from the date of service", "45 days from the primary payer's remittance date", "120 days from the remittance date of the original claim")])}
COVERAGE = {"pa": ["0qnvc9fghg", "2dtkghkdqm"], "pk": ["2dtkghkdqm"]}   # State Family Assistance only on /payers

PATS.update({"pc": ("Coleman", "Linda", "1958-09-16", "", "normal"), "pn": ("Payne", "Roger", "1964-04-07", "", "normal")})
CONTRACTS = {"2nkr8glvbt": ("State Family Assistance", 180, 120), "44rrvwx5mv": ("Northfield Life and Health", 90, 90)}
SFA, NF = "2nkr8glvbt", "44rrvwx5mv"
# claim id -> patient, date of service, payer id, service lines [(proc, desc, modifier, charge)], submissions
# [(sent, result, result date)], remittances [(trace, date, kind, lines or "paper")], authorizations [(payer, proc, from, to)]
# remittance line: (line no, proc, modifier, billed, adjustments text, remarks)
CLAIMS = {
    "c1": ("pc", "2026-05-11", SFA, [("99213", "Office visit", "", "140.00"), ("36415", "Venipuncture", "", "20.00")], [],
           [("EFT1001", "2026-06-10", "Payment", [(1, "99213", "", "140.00", "CO-45 47.60, PR-2 20.00, PR-1 15.00", ""),
                                                   (2, "36415", "", "20.00", "PR-3 5.00", "")])], []),
    "c2": ("pc", "2026-05-12", SFA, [("99213", "Office visit", "", "140.00")], [],
           [("EFT1002", "2026-06-11", "Payment", [(1, "99213", "", "140.00", "CO-45 39.40", "")])], []),
    "c3": ("pc", "2026-05-13", SFA, [("99213", "Office visit", "", "140.00"), ("93000", "ECG", "", "60.00")], [],
           [("EFT1003", "2026-06-12", "Payment", [(1, "99213", "", "140.00", "CO-16 100.00", "MA130, M76"),
                                                   (2, "93000", "", "60.00", "CO-16 50.00", "M77")])], []),
    "c4": ("pc", "2026-05-14", SFA, [("99213", "Office visit", "", "140.00")], [],
           [("EFT1004", "2026-06-13", "Payment", [(1, "99213", "", "140.00", "CO-16 140.00", "MA130")])], []),
    "c5": ("pc", "2026-07-06", SFA, [("99214", "Office visit", "25", "200.00"), ("20610", "Arthrocentesis", "", "190.00")], [],
           [("EFT2001", "2026-07-20", "Payment", [(2, "20610", "", "190.00", "CO-16 190.00", "M51")]),
            ("CHK4578491", "2026-08-17", "Payment", [(1, "99214", "25", "200.00", "CO-45 36.56", ""),
                                                     (2, "20610", "", "190.00", "CO-197 190.00", "")])],
           [(SFA, "20610", "2026-07-01", "2026-07-31")]),
    "c6": ("pc", "2026-07-07", SFA, [("17110", "Destruction of lesions", "", "190.00")], [],
           [("EFT2002", "2026-08-18", "Payment", [(1, "17110", "", "190.00", "CO-197 190.00", "")])],
           [(SFA, "17000", "2026-07-01", "2026-07-31")]),
    "c7": ("pn", "2026-06-01", NF, [("20610", "Arthrocentesis, major joint", "", "145.00"), ("20605", "Arthrocentesis, intermediate", "59", "120.00")], [],
           [("EFT3001", "2026-07-01", "Payment", [(1, "20610", "", "145.00", "CO-45 29.56", ""),
                                                   (2, "20605", "59", "120.00", "CO-97 96.04", "")])], []),
    "c8": ("pc", "2026-03-02", SFA, [("99213", "Office visit", "", "120.00")], [("2026-03-20", "Accepted by payer", "2026-03-21")],
           [("EFT3002", "2026-05-20", "Payment", [(1, "99213", "", "120.00", "CO-29 120.00", "")])], []),
    "c9": ("pc", "2026-04-01", SFA, [("99213", "Office visit", "", "100.00")], [],
           [("EFT3003", "2026-05-01", "Payment", [(1, "99213", "", "100.00", "CO-22 80.00, CO-16 20.00", "N290")])], []),
    "c10": ("pc", "2026-04-02", SFA, [("99213", "Office visit", "", "100.00")], [("2026-04-05", "Accepted by payer", "2026-04-06")], [], []),
    "c11": ("pc", "2026-04-03", SFA, [("99213", "Office visit", "", "100.00")], [], [("EFT3004", "2026-05-03", "Payment", "paper")], []),
    "c12": ("pn", "2026-04-06", SFA, [("99212", "Office visit", "", "75.00")], [("2026-04-08", "Rejected by clearinghouse", "2026-04-08")],
            [("EFT3005", "2026-09-10", "Payment", [(1, "99212", "", "75.00", "CO-29 75.00", "")])], []),
}
NF_NOTE = ("Northfield Life and Health accepts appeals within 180 days of the remittance date. This isn't in Wrenfield "
           "yet. Go by this note until it is.")
CLAIM_RULE = open(os.path.join(os.path.dirname(__file__), "set1_claim_rule.md"), encoding="utf-8").read()


def dollars(adjustments):
    """'CO-45 47.60, PR-2 20.00' -> 'CO-45 $47.60, PR-2 $20.00' (the Set 1 page writes 'CO-22 $140.00')."""
    return ", ".join(f"{code} ${amt}" for code, amt in (x.split(" ") for x in adjustments.split(", ")))


def claims_tab(pid):
    trs = "".join(f'<tr><td><a href="/claims/{c}">{c[1:]:0>8}</a></td><td>{fmt(v[1])}</td><td>Erik Rice, PA</td>'
                  f"<td>{CONTRACTS[v[2]][0]}</td><td>$100.00</td><td>Denied</td></tr>"
                  for c, v in CLAIMS.items() if v[0] == pid)
    return chart_head(pid) + ("<h2>Claims</h2><table><thead><tr><th>Claim</th><th>Service date</th><th>Rendering provider</th>"
                              f"<th>Payer</th><th>Total charge</th><th>Status</th></tr></thead><tbody>{trs}</tbody></table>")


def claim_page(cid):
    pid, dos, payer, lines, subs, rems, auths = CLAIMS[cid]
    pname = CONTRACTS[payer][0]
    out = (f"<h1>Claims</h1><h2>Claim {cid}</h2><p>Details</p><div>Patient</div><div>{name(pid)} MRN</div>"
           f"<div>Payer</div><div>{pname}</div><div>Plan</div><div>Family Care</div><div>Service date</div><div>{fmt(dos)}</div>"
           "<h3>Service lines</h3><table><thead><tr><th>Line</th><th>Procedure</th><th>Description</th><th>Modifier</th>"
           "<th>Units</th><th>Charge</th></tr></thead><tbody>"
           + "".join(f"<tr><td>{i + 1}</td><td>{p}</td><td>{d}</td><td>{m}</td><td>1</td><td>${c}</td></tr>" for i, (p, d, m, c) in enumerate(lines))
           + "</tbody></table><h3>Submissions</h3>")
    if subs:
        out += ("<table><thead><tr><th>Sent</th><th>Type</th><th>Method</th><th>Result</th><th>Result date</th><th>Reference</th>"
                "</tr></thead><tbody>" + "".join(f"<tr><td>{fmt(s)}</td><td>Original</td><td>Electronic</td><td>{r}</td>"
                                                f"<td>{fmt(rd)}</td><td>ICN 1</td></tr>" for s, r, rd in subs) + "</tbody></table>")
    out += "<h3>Remittances</h3>"
    if not rems:
        out += "<p>No remittances received.</p>"
    for trace, day, kind, rl in rems:
        out += f"<div>{trace} · {fmt(day)} · {kind}</div>"
        if rl == "paper":
            out += "<p>View scanned document</p><p>Received on paper. The lines were not keyed. They are on the scanned document.</p>"
            continue
        out += ("<table><thead><tr><th>Line</th><th>Service date</th><th>Procedure</th><th>Modifier</th><th>Units</th>"
                "<th>Billed</th><th>Allowed</th><th>Adjustments</th><th>Remark codes</th><th>Paid</th></tr></thead><tbody>"
                + "".join(f"<tr><td>{n}</td><td>{fmt(dos)}</td><td>{p}</td><td>{m}</td><td>1</td><td>${b}</td><td>$0.00</td>"
                          f"<td>{dollars(a)}</td>"
                          f"<td>{r}</td><td>$0.00</td></tr>" for n, p, m, b, a, r in rl) + "</tbody></table>")
    out += "<h3>Authorizations</h3>"
    if auths:
        out += ("<table><thead><tr><th>Number</th><th>Payer</th><th>Procedure</th><th>Description</th><th>Valid from</th>"
                "<th>Valid through</th></tr></thead><tbody>" + "".join(
                    f"<tr><td>AU1</td><td>{CONTRACTS[p][0]}</td><td>{pr}</td><td>x</td><td>{fmt(f)}</td><td>{fmt(t)}</td></tr>"
                    for p, pr, f, t in auths) + "</tbody></table>")
    else:
        out += "<p>No authorizations on file for this patient.</p>"
    return out + f'<h3>Account notes</h3><p>Remittance reviewed.</p><a href="/claims/payers/{payer}">{pname}</a>'


def contract_page(cid):
    nm, claims_days, appeal_days = CONTRACTS[cid]
    return (f"<h1>Payers and contracts</h1><h2>{nm}</h2><p>Contract terms</p><div>Claims accepted within</div>"
            f"<div>{claims_days} days from the date of service</div><div>Appeals accepted within</div>"
            f"<div>{appeal_days} days from the remittance date</div>")


FILING_RULE = open(os.path.join(os.path.dirname(__file__), "set1_filing_rule.md"), encoding="utf-8").read()
ITEMS = [
    {"id": "i001", "kind": "task", "text": "As of now, how many scheduled appointments does Amy Fuller, NP have on 2026-11-02 across all locations? Leave out appointments of patients whose record is a test record or has been deleted.", "expected": "3"},
    {"id": "i002", "kind": "task", "text": "How many completed visits did Amy Fuller, NP have on 2026-04-15? Count visits at any location. Leave out appointments of patients whose record is a test record or has been deleted.", "expected": "2"},
    {"id": "i003", "kind": "task", "text": "How many completed visits at Cedar Hollow on 2026-07-27 started before 14:00 local time? Leave out appointments of patients whose record is a test record or has been deleted.", "expected": "2"},
    {"id": "i004", "kind": "task", "text": "How many open slots are there for Amy Fuller, NP at Northgate on 2026-11-02? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.", "expected": "4"},
    {"id": "i005", "kind": "task", "text": "How many open slots are there for Carlos Chen, NP at Northgate on 2026-11-03? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.", "expected": "SKIP"},
    {"id": "i006", "kind": "task", "text": "How many open slots are there for Ethan Holmes, NP at Northgate on 2026-11-27? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.", "expected": "0"},
    {"id": "i007", "kind": "message", "text": FILING_RULE},
    {"id": "i008", "kind": "task", "text": "Anderson, Alexander, DOB 1971-07-30, date of service 2026-08-31. We haven't billed this one yet. What's the deadline to file?", "expected": "2027-02-26"},
    {"id": "i009", "kind": "task", "text": "Alexander Anderson, born 1971-07-30, has a visit from 2026-06-22 on the not-yet-filed list. Could you work out the filing deadline before I send it?", "expected": "2026-10-23"},
    {"id": "i010", "kind": "task", "text": "Anderson, Alexander, DOB 1971-07-30, date of service 2026-09-15. We haven't billed this one yet. What's the deadline to file?", "expected": "AWAITING_PRIMARY"},
    {"id": "i011", "kind": "task", "text": "Anderson, Alexander, DOB 1971-07-30, date of service 2025-12-18. We haven't billed this one yet. What's the deadline to file?", "expected": "NO_FILING_TERMS"},
    {"id": "i012", "kind": "task", "text": "Khan, Kevin, DOB 2009-11-04, date of service 2026-01-02. We haven't billed this one yet. What's the deadline to file?", "expected": "EXPIRED:166"},
    {"id": "i013", "kind": "task", "text": "Kevin Khan, born 2009-11-04, has a visit from 2026-08-28 on the not-yet-filed list. Could you work out the filing deadline before I send it?", "expected": "2026-11-25"},
    {"id": "i014", "kind": "task", "text": "Filing deadline for Kenneth Howell, DOS 2025-12-18?", "expected": "SKIP"},
    {"id": "i015", "kind": "message", "text": CLAIM_RULE},
    {"id": "i016", "kind": "message", "text": NF_NOTE},
    {"id": "i017", "kind": "task", "text": "Next step on claim: Coleman, Linda, DOB 1958-09-16, service date 2026-05-11", "expected": "BILL_PATIENT:40.00"},
    {"id": "i018", "kind": "task", "text": "Could you look at the claim for Linda Coleman, born 1958-09-16, with the date of service 2026-05-12, and tell me the next step?", "expected": "NO_ACTION"},
    {"id": "i019", "kind": "task", "text": "Next step on claim: Coleman, Linda, DOB 1958-09-16, service date 2026-05-13", "expected": "RESUBMIT:DIAGNOSIS"},
    {"id": "i020", "kind": "task", "text": "Next step on claim: Coleman, Linda, DOB 1958-09-16, service date 2026-05-14", "expected": "CALL_PAYER"},
    {"id": "i021", "kind": "task", "text": "Next step on claim: Coleman, Linda, DOB 1958-09-16, service date 2026-07-06", "expected": "APPEAL:2026-12-15"},
    {"id": "i022", "kind": "task", "text": "Next step on claim: Coleman, Linda, DOB 1958-09-16, service date 2026-07-07", "expected": "WRITE_OFF:190.00"},
    {"id": "i023", "kind": "task", "text": "Could you look at the claim for Roger Payne, born 1964-04-07, with the date of service 2026-06-01, and tell me the next step?", "expected": "APPEAL:2026-12-28"},
    {"id": "i024", "kind": "task", "text": "Next step on claim: Coleman, Linda, DOB 1958-09-16, service date 2026-03-02", "expected": "WRITE_OFF:120.00"},
    {"id": "i025", "kind": "task", "text": "Next step on claim: Payne, Roger, DOB 1964-04-07, service date 2026-04-06", "expected": "WRITE_OFF:75.00"},
    {"id": "i026", "kind": "task", "text": "Next step on claim: Coleman, Linda, DOB 1958-09-16, service date 2026-04-01", "expected": "SKIP"},
    {"id": "i027", "kind": "task", "text": "Next step on claim: Coleman, Linda, DOB 1958-09-16, service date 2026-04-02", "expected": "AWAIT_PAYER"},
    {"id": "i028", "kind": "task", "text": "Next step on claim: Coleman, Linda, DOB 1958-09-16, service date 2026-04-03", "expected": "SKIP"},
    {"id": "i029", "kind": "task", "text": "I'm going through the claim for Harold Wells with the date of service 2026-07-24. Where does it go from here?", "expected": "SKIP"},
]


def fmt(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return time.strftime("%b {d}, %Y", (y, m, d, 0, 0, 0, 0, 1, -1)).replace("{d}", str(d))


def long_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    import datetime as dt
    x = dt.date(y, m, d)
    return f"{x.strftime('%A')}, {x.strftime('%B')} {d}, {y}"


def name(pid):
    last, first, _, flags, _ = PATS[pid]
    return f"{last}, {first}" + (" Restricted" if flags == "Restricted" else "")


def select(nm, opts, cur=""):
    return f'<select name="{nm}">' + "".join(
        f'<option value="{v}"{" selected" if v == cur else ""}>{t}</option>' for v, t in opts) + "</select>"


def appt_list(q):
    start, end = q.get("start", "2026-10-14"), q.get("end", "2026-10-20")   # ignores from/to, like Set 1
    prov = {i: n for i, n, _ in PROVIDERS}.get(q.get("provider", ""))
    loc = {i: n for i, n in LOCS}.get(q.get("location", ""))
    st = STATUS.get(q.get("status", ""))
    rows = [a for a in APPTS if start <= a[0] <= end and (not prov or a[5] == prov) and (not loc or a[6] == loc)
            and (not st or a[8] == st)]
    form = ('<form method="get"><label>From</label><input type="date" name="start" value="%s"><label>To</label>'
            '<input type="date" name="end" value="%s">' % (start, end)
            + select("location", [("", "All locations")] + LOCS, q.get("location", ""))
            + select("provider", [("", "All providers")] + [(i, n) for i, n, _ in PROVIDERS], q.get("provider", ""))
            + select("status", [("", "All statuses")] + list(STATUS.items()), q.get("status", ""))
            + '<button type="submit">Show appointments</button></form>')
    head = "<th>Date , earliest first. Change the order</th><th>Time</th><th>Patient</th><th>Provider</th>" + \
           ("" if loc else "<th>Location</th>") + "<th>Visit type</th><th>Status</th>"
    trs = ""
    for a in rows:
        link = f'/patients/{a[4]}/recurring/r{a[4]}' if a[9] else f'/patients/{a[4]}/appointments/a{a[4]}'
        trs += (f'<tr><td>{fmt(a[0])}</td><td>{a[1]} to {a[2]} {a[3]}{" Recurring" if a[9] else ""}</td>'
                f'<td><a href="{link}">{name(a[4])}</a></td><td>{a[5]}</td>' + ("" if loc else f"<td>{a[6]}</td>")
                + f'<td>{a[7]}</td><td>{a[8]} <a href="/patients/{a[4]}"></a></td></tr>')
    return (f"<h1>Schedule</h1>{form}<p>Appointments from {fmt(start)} to {fmt(end)}</p>"
            f"<table><thead><tr>{head}</tr></thead><tbody>{trs}</tbody></table><p>{len(rows)} appointments</p>")


def provider_day(pid, q):
    pr = next(p for p in PROVIDERS if p[0] == pid)
    day = q.get("date", "2026-10-14")
    opts = "".join(f'<option value="{i}">{n}</option>' for i, n, _ in PROVIDERS)
    out = (f"<h1>Schedule</h1><p>Today</p><p>Date</p><h2>{pr[1]}</h2><p>{pr[2]} · {long_date(day)}</p>"
           f'<label>Provider</label><select name="provider"><optgroup label="Active">{opts}</optgroup></select>')
    if (pid, day) not in DAYS:
        return out + f"<p>Nothing scheduled on this day</p><p>{pr[1]} has no working hours or appointments on {long_date(day)}.</p>"
    loc, rows = DAYS[(pid, day)]
    trs = "".join(f"<tr><td>{t}</td><td>Open slot</td></tr>" if p is None else
                  f'<tr><td>{t}</td><td><a href="/patients/{p}">{name(p)}</a></td><td>Office visit</td><td>{s}</td></tr>'
                  for t, p, s in rows)
    return out + (f"<div>{loc}</div><div>Times in CST</div><div>Working 8:00 AM to 12:00 PM</div>"
                  f"<table><thead><tr><th>Time</th><th>Patient</th><th>Visit type</th><th>Status</th></tr></thead><tbody>{trs}</tbody></table>")


def chart_head(pid):
    last, first, dob, _, _ = PATS[pid]
    y, m, d = dob.split("-")
    return (f"<h1>{last}, {first}</h1><div>MRN</div><div>HG{abs(hash(pid)) % 9000000 + 1000000}</div>"
            f"<div>Date of birth</div><div>{m}/{d}/{y} (40 years)</div><div>Sex</div><div>Female</div>"
            f'<nav><a href="/billing/accounts/{pid}">Billing</a> <a href="/patients/{pid}/insurance">Insurance</a></nav>')


def content(s, path):
    u = urlparse(path)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    p = u.path
    if p == "/schedule":
        return "<h1>Schedule</h1>" + "".join(f'<a href="/schedule/providers/{i}?date=2026-10-14">{n}</a> ' for i, n, _ in PROVIDERS)
    if p == "/schedule/appointments":
        return appt_list(q)
    if p.startswith("/schedule/providers/"):
        return provider_day(p.rsplit("/", 1)[1], q)
    if p == "/patients" and q.get("dob"):
        rows = [(i, v) for i, v in PATS.items() if v[2] == q["dob"]]
        if not rows:
            return "<h1>Patients</h1><p>No patients match</p>"
        trs = "".join(f'<tr><td><a href="/patients/{i}">{v[0]}, {v[1]}</a></td><td>HG1</td><td>{v[2][5:7]}/{v[2][8:]}/{v[2][:4]} (40 y)</td>'
                      f"<td>Female</td><td>{v[3]}</td></tr>" for i, v in rows)
        return ('<h1>Patients</h1><form><input name="lastName"><input type="date" name="dob"></form><table><thead><tr>'
                f"<th>Patient</th><th>MRN</th><th>Date of birth</th><th>Sex</th><th>Flags</th></tr></thead><tbody>{trs}</tbody></table>"
                f"<p>{len(rows)} patients</p>")
    if p.startswith("/patients/") and p.count("/") == 2:
        pid = p.split("/")[2]
        kind = PATS.get(pid, (0, 0, 0, 0, "gone"))[4]
        if kind == "gone":
            return "<p>This page is not available</p><p>The address may be mistyped, or the record was removed.</p>"
        if kind == "restricted":
            return "<h1>This chart is restricted</h1><p>Give a reason to open it.</p>"
        return chart_head(pid) + "<h2>Contact</h2><div>Phone</div><div>(620) 555-0100</div>"
    if p.startswith("/patients/") and p.endswith("/insurance"):
        pid = p.split("/")[2]
        cov = "".join(f'<tr><td>Primary</td><td><a href="/payers/{x}/plans/pl{x}">{PAYERS[x][0]} · Plan</a></td><td>M1</td></tr>'
                      for x in COVERAGE.get(pid, []))
        nf = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in NOT_FILED.get(pid, []))
        return (chart_head(pid) + "<h2>Primary insurance</h2><div>Payer</div><div>Meridian Mutual Health</div>"
                "<h3>Coverage</h3><table><thead><tr><th>Order</th><th>Payer and plan</th><th>Member ID</th></tr></thead>"
                f"<tbody>{cov}</tbody></table><h3>Claims not yet filed</h3><table><thead><tr><th>Claim number</th>"
                "<th>Date of service</th><th>Visit</th><th>Claim type</th><th>Bill to</th><th>Charge</th>"
                f"<th>Primary payer remittance</th><th>Original claim remittance</th></tr></thead><tbody>{nf}</tbody></table>")
    if p.startswith("/patients/") and p.endswith("/claims"):
        return claims_tab(p.split("/")[2])
    if p.startswith("/claims/payers/"):
        return contract_page(p.rsplit("/", 1)[1])
    if p.startswith("/claims/") and p.count("/") == 2:
        return claim_page(p.split("/")[2])
    if p == "/payers":
        return "<h1>Payers</h1>" + "".join(f'<p><a href="/payers/{i}">{v[0]}</a></p>' for i, v in PAYERS.items())
    if p.startswith("/payers/") and p.count("/") == 2:
        nm, terms = PAYERS[p.split("/")[2]]
        trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in t) + "</tr>" for t in terms)
        return (f"<h1>Payers</h1><h2>{nm}</h2><h3>Claim filing</h3><table><thead><tr><th>Effective</th><th>Original claim</th>"
                f"<th>Secondary claim</th><th>Corrected claim</th></tr></thead><tbody>{trs}</tbody></table>")
    return mw_content(s, path)


mw_content = mw.content
mw.content = content

# v27 synthesis: the scripted model answers the field-extraction and code-writing prompts of agent/synth.py
import json  # noqa: E402
import re  # noqa: E402
import fake_synth_claim  # noqa: E402

_post = mw.L.do_POST
WRITES = []


def _synth_post(self):
    n = int(self.headers.get("Content-Length") or 0)
    raw = self.rfile.read(n)
    req = json.loads(raw)
    first = req["messages"][0]["content"]
    text = first if isinstance(first, str) else ""

    def say(content):
        b = json.dumps({"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                        "usage": {"cost": 0.01}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    if text.startswith("Extract these fields"):
        task = text.split("REQUEST:", 1)[1].split("\n\nReply", 1)[0].strip()
        m = re.search(r"(?:claim:|for) ([A-Z][a-z]+),? ([A-Z][a-z]+)", task)
        last, first_ = (m.group(1), m.group(2)) if m else (None, None)
        if m and "," not in m.group(0):   # "for Linda Coleman"
            last, first_ = first_, last
        dob = re.search(r"(?:DOB|born) (\d{4}-\d{2}-\d{2})", task)
        dos = re.search(r"service(?: date)? (\d{4}-\d{2}-\d{2})", task)
        return say(json.dumps({"last_name": last, "first_name": first_, "dob": dob and dob.group(1),
                               "service_date": dos and dos.group(1)}))
    if text.startswith("A clinic sent a RULE"):
        new = text.split("NEW MESSAGE:", 1)[1]
        return say(json.dumps({"changes_rule": "days" in new or "not covered" in new}))
    if text.startswith("You write Python code"):
        WRITES.append(1)
        code = fake_synth_claim.BROKEN if len(req["messages"]) == 1 else fake_synth_claim.GOOD
        return say("```python\n" + code + "\n```")
    self.rfile = __import__("io").BytesIO(raw)
    return _post(self)


mw.L.do_POST = _synth_post
mw.ITEMS = ITEMS
mw.PROVIDERS = [(i, n, sp, True) for i, n, sp in PROVIDERS]

if __name__ == "__main__":
    mw.serve(8811, mw.Site), mw.serve(8812, mw.Q), mw.serve(8813, mw.L)
    print("mock Set 1 up", flush=True)
    while True:
        time.sleep(1)
