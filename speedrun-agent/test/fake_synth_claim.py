"""What the scripted model 'writes' when the synthesis asks for a claim solver (test/mock_set1.py). It stands in for
the strong model, to test agent/synth.py end to end: compile, the api, the check on the rule's worked example, the
repair round (BROKEN is sent first) and use on later tasks. It covers the paid and reason-197 branches only and
returns None for the rest, as a careful generated solver should."""

BROKEN = '''
async def solve(task, api):
    f = await api.fields(task, {"last_name": "patient's last name"})
    return f["no such key"]
'''

GOOD = '''
async def solve(task, api):
    f = await api.fields(task, {"last_name": "patient's last name", "first_name": "patient's first name",
                                "dob": "date of birth YYYY-MM-DD or null", "service_date": "date of service YYYY-MM-DD"})
    dos = api.parse_date(f.get("service_date"))
    if not f.get("dob") or not dos:
        return None
    pts = [p for p in await api.find_patient(dob=f["dob"])
           if p["name"].split(",")[0].strip().lower() == (f.get("last_name") or "").strip().lower()]
    if len(pts) != 1:
        return None
    tab = await api.data(pts[0]["path"] + "/claims")
    claims = [h for t in tab["tables"] for r in t["rows"] if len(r["cells"]) > 1 and api.parse_date(r["cells"][1]) == dos
              for _, h in r["links"] if h.startswith("/claims/")]
    if len(claims) != 1:
        return None
    page = await api.data(claims[0])
    heads = re.findall(r"(\\w+) · ([A-Z][a-z]{2} \\d{1,2}, \\d{4}) · (Payment|Reversal of \\w+)", page["text"])
    reversed_ = {k.split(" of ")[1] for _, _, k in heads if k.startswith("Reversal")}
    pays = [(api.parse_date(d), tr) for tr, d, k in heads if k == "Payment" and tr not in reversed_]
    if not pays:
        return "AWAIT_PAYER"
    pay_date, cur = max(pays)
    rem = [t for t in page["tables"] if "Adjustments" in t["headers"]]
    if len(rem) != len(heads):
        api.log("a remittance has no keyed lines (paper)")
        return None
    t = rem[[h[0] for h in heads].index(cur)]
    ai, pi = t["headers"].index("Adjustments"), t["headers"].index("Procedure")
    lines = [(r["cells"][pi], [(g, int(c), float(a.replace(",", ""))) for g, c, a in
                               re.findall(r"(CO|PR)-(\\d+) \\$([\\d.,]+)", r["cells"][ai])]) for r in t["rows"]]
    denied = [(p, g, c, a) for p, adj in lines for g, c, a in adj if g == "CO" and c in (16, 22, 29, 97, 197)]
    if not denied:
        owed = sum(a for _, adj in lines for g, c, a in adj if g == "PR" and c in (1, 2, 3))
        return f"BILL_PATIENT:{owed:.2f}" if owed > 0 else "NO_ACTION"
    reasons = {c for _, _, c, _ in denied}
    if reasons & {29, 22, 16} or reasons != {197}:
        return None
    payer = re.search(r"Payer\\n([^\\n]+)", page["text"])
    auth = [t for t in page["tables"] if "Valid from" in t["headers"]]
    covered = set()
    for at in auth:
        h = at["headers"]
        for r in at["rows"]:
            c = dict(zip(h, r["cells"]))
            lo, hi = api.parse_date(c.get("Valid from")), api.parse_date(c.get("Valid through"))
            if payer and c.get("Payer") == payer.group(1).strip() and lo and hi and lo <= dos <= hi:
                covered.add(c.get("Procedure"))
    amount = sum(a for _, _, _, a in denied)
    if not all(p in covered for p, _, _, _ in denied):
        return f"WRITE_OFF:{amount:.2f}"
    contract = next((h for _, h in page["links"] if h.startswith("/claims/payers/")), None)
    if not contract:
        return None
    m = re.search(r"Appeals accepted within\\s*(\\d+) days", await api.page(contract))
    if not m:
        return None
    last = pay_date + timedelta(days=int(m.group(1)))
    api.log("current", cur, pay_date, "last day", last)
    return f"APPEAL:{last.isoformat()}" if last >= api.today else f"WRITE_OFF:{amount:.2f}"
'''
