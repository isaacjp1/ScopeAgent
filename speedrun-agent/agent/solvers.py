"""Code solvers for Set 1 task kinds whose pages load with plain URLs (seen working in the Set 1 log):
provider appointment counts, completed-visit counts, open slots and claim filing deadlines.

Every fact is checked before it is used: the page must show the date / provider / location that was asked for
(a clinic version that ignores a URL parameter would otherwise give a confident wrong count), lists must be
complete, and the rule text the clinic sent must contain what the code assumes. Anything unexpected -> no(...),
and the general model loop gets the task as before."""
import asyncio
import calendar
import datetime as dt
import re
from urllib.parse import urlencode

from .clinic import norm, parse_any_date, parse_dt
from .fast import dates_in, no, pick_patient

ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


# ------------------------------------------------------------------ page helpers
def form_dates(data, must_have):
    """Names of the date fields (in order) of the GET form that also has the field `must_have`."""
    for f in data.get("forms", []):
        spec = f.split(" :: ", 1)[-1]
        names = [(m.group(1), m.group(2)) for m in re.finditer(r"([\w\-]+)\((\w+)\)", spec)]
        if any(n == must_have for n, _ in names):
            return [n for n, t in names if t == "date"]
    return []


def option(data, select_name, label):
    """Value of the option whose text is `label` (ignoring case, accents, punctuation and '(inactive)')."""
    want = norm(label)
    for s in data.get("selects", []):
        if s.get("name") != select_name:
            continue
        hits = [o["value"] for o in s["options"] if norm(re.sub(r"\(inactive\)", "", o["text"])) == want]
        if len(hits) == 1 and hits[0]:
            return hits[0]
    return None


def table_rows(data, *headers):
    """Rows (as dicts header -> cell, plus '_links') of the tables whose headers include all of `headers`."""
    out = []
    for t in data.get("tables", []):
        h = [x.split(",")[0].strip() for x in t.get("headers", [])]
        if not all(any(x.lower().startswith(want.lower()) for x in h) for want in headers):
            continue
        for r in t["rows"]:
            row = {h[i]: c for i, c in enumerate(r["cells"]) if i < len(h)}
            row["_links"] = [x for _, x in r["links"]]
            out.append(row)
    return out


def incomplete(data):
    """True when a list shows only part of its rows ('Showing 20 of 31', 'Show more', a paging warning)."""
    t = data.get("text", "")
    m = re.search(r"Showing (?:\d+ to )?([\d,]+) of (?:about )?([\d,]+)", t)
    if m and int(m.group(1).replace(",", "")) < int(m.group(2).replace(",", "")):
        return True
    return bool(data.get("incomplete")) or "Show more" in t


def date_of(s):
    p = parse_dt(s or "")
    return p[0] if p else parse_any_date(s or "")


async def excluded_patient(site, row):
    """True if the appointment's patient is a test record or deleted, False if not, None if it can't be told."""
    cell = row.get("Patient", "")
    if re.search(r"\b(test|deleted)\b", cell, re.I):
        return True
    chart = next((h for h in row["_links"] if re.fullmatch(r"/patients/[^/?#]+", h)), None)
    if not chart:
        return None
    data = await site.read(chart, all_pages=False)
    text = data.get("text", "")
    if data.get("error"):
        return None
    if "This page is not available" in text[:200] or re.search(r"record was removed|has been deleted", text[:400], re.I):
        return True   # the chart a schedule row links to is gone: the record was deleted
    if re.search(r"chart is restricted", text[:400], re.I):
        return False   # a restricted chart is a real patient (its flag shows in the list cell, checked above)
    head = text.split("\nBilling", 1)[0][:300]   # name, MRN, date of birth, sex: the chart's header
    if re.search(r"\b(test record|test patient|deleted)\b", head, re.I):
        return True
    # The patient search has a Flags column (Restricted, Merged, ...): find this chart there by date of birth.
    dob = re.search(r"Date of birth\s*\n\s*(\d{2}/\d{2}/\d{4})", head)
    if not dob:
        return None
    found = await site.read("/patients?dob=" + parse_any_date(dob.group(1)).isoformat())
    hit = [r for r in table_rows(found, "Patient", "Flags") if chart in r["_links"]]
    if len(hit) != 1:
        return None   # not listed (perhaps deleted): can't tell, so the task is skipped
    return bool(re.search(r"\b(test|deleted)\b", hit[0].get("Flags", ""), re.I))


async def count_rows(site, rows):
    flags = await asyncio.gather(*[excluded_patient(site, r) for r in rows])
    if any(f is None for f in flags):
        return None
    return sum(1 for f in flags if not f)


async def appointment_list(site, start, end, status, provider=None, location=None):
    """Rows of the schedule's appointment list for one date range, provider/location and status, read fresh.
    None if the form or the page does not show exactly what was asked."""
    base = await site.read("/schedule/appointments", all_pages=False)
    dates = form_dates(base, "status")
    if len(dates) < 2:
        return None, "appointment list form has no date range"
    params = {dates[0]: start.isoformat(), dates[1]: end.isoformat()}
    st = option(base, "status", status)
    if not st:
        return None, f"no status option {status!r}"
    if provider:
        pv = option(base, "provider", provider)
        if not pv:
            return None, f"provider {provider!r} not in the list form"
        params["provider"] = pv
    if location:
        lv = option(base, "location", location)
        if not lv:
            return None, f"location {location!r} not in the list form"
        params["location"] = lv
    params["status"] = st
    data = await site.read("/schedule/appointments?" + urlencode(params), fresh=True)   # live: being cancelled
    m = re.search(r"Appointments from ([A-Z][a-z]+ \d{1,2}, \d{4}) to ([A-Z][a-z]+ \d{1,2}, \d{4})", data.get("text", ""))
    if not m or date_of(m.group(1)) != start or date_of(m.group(2)) != end:
        return None, "the list does not show the requested dates"
    if incomplete(data):
        return None, "appointment list not complete on one page"
    rows = table_rows(data, "Patient", "Status")
    if not rows and not re.search(r"\b0 appointments|No appointments", data.get("text", "")):
        return None, "no appointment table and no 'no appointments' text"
    for r in rows:   # every row must match the filters, or the page ignored one
        if norm(r.get("Status", "")) != norm(status):
            return None, f"row with status {r.get('Status')!r}"
        if provider and norm(re.sub(r"\(inactive\)", "", r.get("Provider", ""))) != norm(provider):
            return None, f"row of provider {r.get('Provider')!r}"
        if location and "Location" in r and norm(r["Location"]) != norm(location):
            return None, f"row at {r.get('Location')!r}"
        if not start <= (date_of(r.get("Date", "")) or dt.date.min) <= end:
            return None, f"row dated {r.get('Date')!r}"
    return rows, "ok"


# ------------------------------------------------------------------ provider appointment / visit counts
COUNT_SCHED = re.compile(r"how many scheduled appointments does (.+?) have on (\d{4}-\d{2}-\d{2})", re.I)
COUNT_DONE = re.compile(r"how many completed visits did (.+?) have on (\d{4}-\d{2}-\d{2})", re.I)
COUNT_LOC_BEFORE = re.compile(r"how many completed visits at (.+?) on (\d{4}-\d{2}-\d{2}) started before (\d{1,2}):(\d{2})", re.I)
COUNT_ANY = re.compile(COUNT_SCHED.pattern + "|" + COUNT_DONE.pattern + "|" + COUNT_LOC_BEFORE.pattern, re.I)


async def provider_counts(fast, task):
    if not re.search(r"test record", task, re.I) or not re.search(r"deleted", task, re.I):
        return no("count task without the test/deleted instruction")
    m = COUNT_LOC_BEFORE.search(task)
    if m:
        day = dt.date.fromisoformat(m.group(2))
        rows, why = await appointment_list(fast.site, day, day, "Completed", location=m.group(1).strip())
        if rows is None:
            return no(why)
        limit = int(m.group(3)) * 60 + int(m.group(4))
        keep = []
        for r in rows:
            t = re.match(r"(\d{1,2}):(\d{2}) (AM|PM)", r.get("Time", ""))
            if not t:
                return no(f"unreadable time {r.get('Time')!r}")
            h = int(t.group(1)) % 12 + (12 if t.group(3) == "PM" else 0)
            if h * 60 + int(t.group(2)) < limit:   # times are local to the location (the list shows them so)
                keep.append(r)
        n = await count_rows(fast.site, keep)
    else:
        m = COUNT_SCHED.search(task) or COUNT_DONE.search(task)
        if not re.search(r"across all locations|at any location|any location", task, re.I):
            return no("count task limited to a location")
        status = "Scheduled" if COUNT_SCHED.search(task) else "Completed"
        day = dt.date.fromisoformat(m.group(2))
        rows, why = await appointment_list(fast.site, day, day, status, provider=m.group(1).strip())
        if rows is None:
            return no(why)
        n = await count_rows(fast.site, rows)
    if n is None:
        return no("could not tell whether a patient is a test or deleted record")
    return "answer", str(n), {"route": ["solver:count"], "conf": 1.0, "why": f"{len(rows)} rows, {n} counted"}


# ------------------------------------------------------------------ open slots
SLOTS = re.compile(r"how many open slots are there for (.+?) at (.+?) on (\d{4}-\d{2}-\d{2})", re.I)


async def open_slots(fast, task):
    m = SLOTS.search(task)
    name, place, day = m.group(1).strip(), m.group(2).strip(), dt.date.fromisoformat(m.group(3))
    provs = await fast.site.providers()
    hit = [p for p in provs if norm(p["name"]) == norm(name)]
    if len(hit) != 1 or not hit[0]["value"]:
        return no(f"provider {name!r} not found once")
    v = hit[0]["value"]
    data = await fast.site.read((v if v.startswith("/") else f"/schedule/providers/{v}") + f"?date={day.isoformat()}",
                                all_pages=False, fresh=True)
    text = data.get("text", "")
    shown = [date_of(x) for x in re.findall(r"[A-Z][a-z]+day, ([A-Z][a-z]+ \d{1,2}, \d{4})", text)]
    if day not in shown or norm(name) not in norm(text):
        return no("provider page does not show that provider and date")
    sections = re.findall(r"\n([^\n]+)\nTimes in [A-Z]{2,4}\n", "\n" + text)
    if not sections:
        if re.search(r"has no working hours", text):
            return "answer", "0", {"route": ["solver:slots"], "conf": 1.0, "why": "no working hours that day"}
        return no("no working-hours section on the provider page")
    if len(sections) != 1 or norm(sections[0]) != norm(place):
        return no(f"provider works at {sections} that day, asked about {place!r}")
    rows = [r for t in data.get("tables", []) for r in t["rows"]]
    if not rows:
        return no("no schedule table")
    n = sum(1 for r in rows if any(norm(c) == "open slot" for c in r["cells"]))
    return "answer", str(n), {"route": ["solver:slots"], "conf": 1.0, "why": f"{n} open slots at {place}"}


# ------------------------------------------------------------------ claim filing deadline
FILING = re.compile(r"deadline to file|filing deadline|can we still file|not-yet-filed list", re.I)


def filing_rule(rules):
    """Holidays, today and the answer forms from the clinic's filing message; None if it is not as expected."""
    text = next((t for t in reversed(rules.items) if re.search(r"last day to file a claim", t, re.I)), None)
    if not text:
        return None
    today = re.search(r"Today is (\d{4}-\d{2}-\d{2})", text)
    hol = re.search(r"these holidays:(.*?)Use this list", text, re.S)
    need = ["NO_FILING_TERMS", "AWAITING_PRIMARY", "EXPIRED:", "nearest earlier day", "latest effective date on or before"]
    if not today or not hol or not all(s in text for s in need):
        return None
    return {"today": dt.date.fromisoformat(today.group(1)),
            "holidays": {dt.date.fromisoformat(d) for d in ISO.findall(hol.group(1))}}


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


async def payer_path(site, ins, payer):
    for r in table_rows(ins, "Payer and plan"):
        if norm(r.get("Payer and plan", "").split("·")[0]) == norm(payer):
            for h in r["_links"]:
                m = re.match(r"(/payers/[^/?#]+)", h)
                if m:
                    return m.group(1)
    lst = await site.read("/payers", all_pages=False)
    hits = {h for t, h in lst.get("links", []) if norm(t) == norm(payer) and re.fullmatch(r"/payers/[^/?#]+", h)}
    return hits.pop() if len(hits) == 1 else None


async def filing_deadline(fast, task):
    rule = filing_rule(fast.rules)
    if not rule:
        return no("filing rule message missing or not as expected")
    pat, dob = await pick_patient(fast.site, task)
    if not pat:
        return no(dob)
    dos = [d for d in dates_in(task) if d != dob]
    if len(dos) != 1:
        return no(f"{len(dos)} service dates in the task")
    dos = dos[0]
    ins = await fast.site.read(pat["path"] + "/insurance", all_pages=False)
    rows = [r for r in table_rows(ins, "Claim number", "Date of service", "Claim type", "Bill to")
            if date_of(r.get("Date of service", "")) == dos]
    if len(rows) != 1:
        return no(f"{len(rows)} not-yet-filed claims on {dos}")
    r = rows[0]
    kind = r["Claim type"].strip().lower()
    payer = r["Bill to"].split("·")[0].strip()
    path = await payer_path(fast.site, ins, payer)
    if not path:
        return no(f"payer page of {payer!r} not found")
    pdata = await fast.site.read(path, all_pages=False)
    if norm(payer) not in norm(pdata.get("text", "")[:300]):
        return no("payer page is not that payer's")
    terms = table_rows(pdata, "Effective", "Original claim", "Secondary claim", "Corrected claim")
    in_effect = [t for t in terms if (date_of(t["Effective"]) or dt.date.max) <= dos]
    if not terms:
        return no("no claim filing table on the payer page")
    if not in_effect:
        return "answer", "NO_FILING_TERMS", {"route": ["solver:filing"], "conf": 1.0, "why": f"{payer}: no terms on {dos}"}
    t = max(in_effect, key=lambda x: date_of(x["Effective"]))
    col = {"original": "Original claim", "secondary": "Secondary claim", "corrected": "Corrected claim"}.get(kind)
    if not col:
        return no(f"claim type {kind!r}")
    if kind == "original":
        start = dos
    else:
        cell = r.get("Primary payer remittance" if kind == "secondary" else "Original claim remittance", "")
        start = date_of(cell)
        if not start:
            if kind == "secondary" and re.fullmatch(r"\s*(none|not received.*|-|)\s*", cell, re.I):
                return "answer", "AWAITING_PRIMARY", {"route": ["solver:filing"], "conf": 1.0, "why": "no primary remittance"}
            return no(f"no {kind} start date in {cell!r}")
    lim = re.search(r"(\d+)\s+(day|month)s?", t[col], re.I)
    if not lim:
        return no(f"unreadable limit {t[col]!r}")
    n = int(lim.group(1))
    last = add_months(start, n) if lim.group(2).lower() == "month" else start + dt.timedelta(days=n)
    while last.weekday() >= 5 or last in rule["holidays"]:
        last -= dt.timedelta(days=1)
    today = rule["today"]
    ans = last.isoformat() if last >= today else f"EXPIRED:{(today - last).days}"
    return "answer", ans, {"route": ["solver:filing"], "conf": 1.0,
                           "why": f"{kind} {payer} {t[col]} from {start} -> {last}"}


# ------------------------------------------------------------------ claim next step after a remittance
CLAIM = re.compile(r"next step on claim|\bthe claim for\b", re.I)
ADJ = re.compile(r"\b(CO|PR|OA|PI)-(\d+)\s*\$?(-?[\d,]+\.\d{2})")


def claim_rule(rules):
    """Reason order, remark-code table, bundling table, today and appeal-day overrides, all read from the clinic's
    messages (a later message wins). None if the rule is not the one this solver implements."""
    text = next((t for t in reversed(rules.items) if re.search(r"working a claim after its remittance", t, re.I)), None)
    if not text:
        return None
    order = re.search(r"one reason only, the one that comes first in this order: ([\d, ]+)\.", text)
    today = re.search(r"Today is (\d{4}-\d{2}-\d{2})", text)
    patient = re.search(r"Add up the `PR` adjustments with reason ([\d, or]+) on", text)
    remarks = re.findall(r"\|\s*([A-Z]{1,2}\d{2,4})\s*\|[^|\n]*\|\s*`([A-Z_]+)`\s*\|", text)
    ncci = re.findall(r"\|\s*(\d{5})\s*\|\s*(\d{5})\s*\|\s*([01])\s*\|", text)
    need = ["AWAIT_PAYER", "NO_ACTION", "BILL_PATIENT:", "RESUBMIT:", "CALL_PAYER", "APPEAL:", "WRITE_OFF:",
            "never the current remittance", "modifier 59", "result date on or before", "first and last valid days"]
    if not (order and today and patient and remarks and ncci) or not all(s in text for s in need):
        return None
    overrides = {}
    for t in rules.items:   # in order, so the newest note about a payer wins
        for m in re.finditer(r"([A-Z][A-Za-z&' ]+?) accepts appeals within (\d+) days of the remittance date", t):
            overrides[norm(m.group(1))] = int(m.group(2))
    return {"order": [int(x) for x in re.findall(r"\d+", order.group(1))],
            "patient": {int(x) for x in re.findall(r"\d+", patient.group(1))},
            "remarks": remarks, "ncci": [(a, b, c == "1") for a, b, c in ncci],
            "today": dt.date.fromisoformat(today.group(1)), "overrides": overrides}


def table_block(block):
    """Rows of the first '[table] ## h1 | h2 ... [/table]' block in a piece of page text, as dicts."""
    m = re.search(r"\[table\]\n## ([^\n]*)\n(.*?)\n\[/table\]", block, re.S)
    if not m:
        return None
    heads = [h.strip() for h in m.group(1).split(" | ")]
    rows = []
    for ln in m.group(2).split("\n"):
        cells = [c.strip() for c in re.sub(r"\s+->\s+/.*$", "", ln).split(" | ")]
        if len(cells) == len(heads) - 1 and ln.rstrip().endswith("|"):
            cells[-1] = cells[-1].rstrip("|").strip()
            cells.append("")   # an empty last cell lost its separator to trimming
        if len(cells) == len(heads):
            rows.append(dict(zip(heads, cells)))
        elif ln.strip():
            return None   # a row that does not fit the header: don't guess
    return rows


async def claim_next_step(fast, task):
    rule = claim_rule(fast.rules)
    if not rule:
        return no("claim rule message missing or not as expected")
    pat, dob = await pick_patient(fast.site, task)
    if not pat:
        return no(dob)
    dos = [d for d in dates_in(task) if d != dob]
    if len(dos) != 1:
        return no(f"{len(dos)} service dates in the task")
    dos = dos[0]
    links = set()
    for p in pat["paths"]:   # a duplicate merged into the chart files its claims there too
        data = await fast.site.read(p + "/claims")
        for r in table_rows(data, "Claim", "Service date", "Payer", "Status"):
            if date_of(r["Service date"]) == dos:
                links |= {h for h in r["_links"] if re.fullmatch(r"/claims/[^/?#]+", h)}
    if len(links) != 1:
        return no(f"{len(links)} claims on {dos}")
    cdata = await fast.site.read(links.pop(), all_pages=False)
    text = cdata.get("text", "")
    shown = re.search(r"\nService date\s*\n\s*([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    payer = re.search(r"\nPayer\s*\n\s*([^\n]+)", text)
    if not shown or date_of(shown.group(1)) != dos or not payer:
        return no("claim page does not show that service date / a payer")
    payer = payer.group(1).strip()
    lines_billed = {r.get("Line"): r for r in table_rows(cdata, "Line", "Procedure", "Description", "Modifier")}
    if "\nRemittances" not in text or "\nAuthorizations" not in text:
        return no("claim page has no Remittances / Authorizations panel")
    sec = text.split("\nRemittances", 1)[1].split("\nAuthorizations", 1)[0]
    heads = list(re.finditer(r"([A-Z0-9]+) · ([A-Z][a-z]{2} \d{1,2}, \d{4}) · ([A-Za-z ]+)", sec))
    if not heads:
        if re.search(r"No remittance", sec, re.I):
            return "answer", "AWAIT_PAYER", {"route": ["solver:claim"], "conf": 1.0, "why": "no remittance"}
        return no("unreadable Remittances panel")
    rems = []
    for i, h in enumerate(heads):
        block = sec[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(sec)]
        rems.append({"trace": h.group(1), "date": date_of(h.group(2)), "type": h.group(3).strip(), "block": block})
    if any(r["type"].lower() != "payment" or re.search(r"revers", r["block"], re.I) for r in rems):
        return no("remittance with a reversal: its layout has not been seen")
    latest = max(r["date"] for r in rems)
    current = [r for r in rems if r["date"] == latest]
    if len(current) != 1:
        return no("two current remittances on one date")
    current = current[0]
    rows = table_block(current["block"])
    if rows is None:
        return no("current remittance not keyed (paper) or unreadable")
    rows = [r for r in rows if date_of(r.get("Service date", "")) == dos]
    if not rows:
        return no("no remittance lines for this claim")
    for r in rows:
        r["adj"] = [(g, int(c), float(a.replace(",", ""))) for g, c, a in ADJ.findall(r.get("Adjustments", ""))]
        r["remarks"] = set(re.findall(r"\b[A-Z]{1,2}\d{2,4}\b", r.get("Remark codes", "")))
    denial = set(rule["order"])
    present = {c for r in rows for g, c, _ in r["adj"] if g == "CO" and c in denial}
    if not present:
        total = sum(a for r in rows for g, c, a in r["adj"] if g == "PR" and c in rule["patient"])
        ans = f"BILL_PATIENT:{total:.2f}" if total > 0.004 else "NO_ACTION"
        return "answer", ans, {"route": ["solver:claim"], "conf": 1.0, "why": f"paid, patient owes {total:.2f}"}
    reason = next(c for c in rule["order"] if c in present)
    denied = [r for r in rows if any(g == "CO" and c == reason for g, c, _ in r["adj"])]
    amount = sum(a for r in denied for g, c, a in r["adj"] if g == "CO" and c == reason)
    write_off = ("answer", f"WRITE_OFF:{amount:.2f}", {"route": ["solver:claim"], "conf": 1.0, "why": f"reason {reason}, no grounds"})
    if reason == 16:
        for code, field in rule["remarks"]:
            if any(code in r["remarks"] for r in denied):
                return "answer", f"RESUBMIT:{field}", {"route": ["solver:claim"], "conf": 1.0, "why": f"16 with {code}"}
        return "answer", "CALL_PAYER", {"route": ["solver:claim"], "conf": 1.0, "why": "16 without a listed remark"}
    if reason == 22:
        return no("reason 22 needs the account notes about other insurance")
    contract_link = next((h for _, h in cdata.get("links", []) if re.fullmatch(r"/claims/payers/[^/?#]+", h)), None)
    if not contract_link:
        return no("no payer contract link on the claim page")
    contract = (await fast.site.read(contract_link, all_pages=False)).get("text", "")
    if norm(payer) not in norm(contract[:300]):
        return no("contract page is not the claim payer's")
    if reason == 29:
        m = re.search(r"Claims accepted within\s*\n\s*(\d+) days from the date of service", contract)
        if not m:
            return no("contract has no claim filing days")
        last_file = dos + dt.timedelta(days=int(m.group(1)))
        subs = table_rows(cdata, "Sent", "Type", "Method", "Result", "Result date")
        grounds = any(re.search(r"accepted by payer", s.get("Result", ""), re.I)
                      and (date_of(s.get("Result date", "")) or dt.date.max) <= last_file for s in subs)
    elif reason == 197:
        if not re.search(r"No authorizations on file", text):
            auths = table_rows(cdata, "Number", "Payer", "Procedure", "Valid from", "Valid through")
            if not auths:
                return no("authorizations panel unreadable")
        else:
            auths = []
        grounds = all(any(norm(a["Payer"]) == norm(payer) and a["Procedure"].strip() == r.get("Procedure", "").strip()
                          and (date_of(a["Valid from"]) or dt.date.max) <= dos <= (date_of(a["Valid through"]) or dt.date.min)
                          for a in auths) for r in denied)
    elif reason == 97:
        billed = list(lines_billed.values())
        if not billed:
            return no("no service lines table")

        def has_grounds(r):
            own = lines_billed.get(r.get("Line"))
            if not own or own.get("Procedure", "").strip() != r.get("Procedure", "").strip():
                return False
            for c1, c2, ind in rule["ncci"]:
                if ind and c2 == own["Procedure"].strip() and "59" in own.get("Modifier", "") and \
                        any(b is not own and b.get("Procedure", "").strip() == c1 for b in billed):
                    return True
            return False
        grounds = all(has_grounds(r) for r in denied)
    else:
        return no(f"reason {reason} not handled")
    if not grounds:
        return write_off
    days = rule["overrides"].get(norm(payer))
    if days is None:
        m = re.search(r"Appeals accepted within\s*\n\s*(\d+) days from the remittance date", contract)
        if not m:
            return no("contract has no appeal days")
        days = int(m.group(1))
    last = current["date"] + dt.timedelta(days=days)
    if last >= rule["today"]:
        return "answer", f"APPEAL:{last.isoformat()}", {"route": ["solver:claim"], "conf": 1.0,
                                                        "why": f"reason {reason}, {days} days from {current['date']}"}
    return write_off


KINDS = [(COUNT_ANY, provider_counts), (SLOTS, open_slots), (FILING, filing_deadline), (CLAIM, claim_next_step)]
