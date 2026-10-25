"""Find the patient a task is about (v40).

v29's biggest single failure: tasks that name a patient without a date of birth ("Next step for a lab report:
Andres Salazar, ...", "Patrick Watkins is on the books for ...") ended in "find_patient -> []" because the
last-name search is phonetic and returns hundreds of rows ("Wells" -> 500 rows starting at "Wallace"), and the
agent never paged past the first 20. This module tries, in order of cost:

1. date of birth search (one page, a handful of rows), names checked;
2. a list indexed by the task's OTHER date that shows patient names with chart links:
   - documents received that day (/documents?kind=...&from=D&to=D) for lab reports, referral letters, ...
   - appointments on that day (/schedule/appointments?start=D&end=D) for visits, wound visits, estimates, ...
3. the last-name search, walked page by page in sorted order (last name, then first name) and stopped as soon as
   the wanted name is found or passed: a few page clicks instead of the whole list.

Returns a Found (chart row + merged duplicate paths + how it was found + extra rows like the matching document)
or None with the candidate rows seen (the model gets those to decide)."""
import asyncio
import datetime as dt
import re

from . import clinic
from .clinic import fold, norm, parse_any_date

DOB_RE = re.compile(r"(?:born|DOB|date of birth|birth ?date|b\.)\s*:?\s*(?:on\s+)?"
                    r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4})", re.I)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\b[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}")
TIME_RE = re.compile(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b")
_W = r"[A-Z][a-zA-Z'’À-ſ-]+"
NAME_LF = re.compile(rf"\b({_W}(?: {_W})?), ({_W})\b")                       # "Anderson, Evelyn"
NAME_FL = re.compile(rf"\b(?:for|patient|of|about|to|from|named)\s+({_W})\s+({_W}(?:-{_W})?)\b")   # "for Barbara Li"
NAME_POSS = re.compile(rf"\b({_W})\s+({_W}(?:-{_W})?)['’]s\b")                 # "Madison López's"
NAME_PAIR = re.compile(rf"\b({_W})\s+({_W}(?:-{_W})?)\b")
CREDENTIALS = {"md", "do", "np", "pa", "rn", "dpm", "dds", "phd", "lcsw", "cnm", "od", "dc", "pt", "pa-c", "fnp", "aprn"}
NOT_NAMES = set("""what which who whom how is are was does did do when where why can could please patient patients
referral letter lab report statement billing question phone number born dob date birth the for our we visit new
established on in at of and with dr doctor invoice balance complete basic thyroid panel blood count metabolic
comprehensive lipid hemoglobin urinalysis vaccine claim payer plan good faith estimate recall tetanus wound
appointment appointments provider today next step should have gotten you look check tell find give show many
scheduled completed open slots slot visits immunization record records document documents service remittance
insurance deadline filing recalled lot dose doses notify notice summary note notes urgent care nurse manager front
desk across all locations location monday tuesday wednesday thursday friday saturday sunday january february march
april may june july august september october november december doing chart review came seen tig nothing vaccine
filed file still owed i i'm we've anything let me is it there liver function vitamin iron studies a1c dos mrn ssn
id""".split())
DOC_KINDS = [  # (words in the task, kind value of /documents?kind=)
    (re.compile(r"\blab(oratory)? (report|result)s?\b|\bpanel\b", re.I), "lab_report"),
    (re.compile(r"\breferral\b", re.I), "referral_letter"),
    (re.compile(r"\bimmunization record\b|\boutside (immunization )?record\b", re.I), "immunization_record"),
    (re.compile(r"\bstatement\b", re.I), "statement"),
    (re.compile(r"\beligibility\b", re.I), "eligibility_response"),
    (re.compile(r"\bexplanation of benefits\b|\bEOB\b", re.I), "eob"),
    (re.compile(r"\bcourt order\b", re.I), "court_order"),
    (re.compile(r"\bmedicare questionnaire\b", re.I), "medicare_questionnaire"),
]
VISIT_WORDS = re.compile(r"\b(on the books|appointment|visit|came in|seen|wound|scheduled|booked|estimate|"
                         r"checked in|was in|come in|service date|date of service|DOS)\b", re.I)


def task_dates(text):
    out = []
    for s in DATE_RE.findall(text):
        d = parse_any_date(s)
        if d and d not in out:
            out.append(d)
    return out


def dob_of(text):
    m = DOB_RE.search(text)
    return parse_any_date(m.group(1)) if m else None


def _ok_name(*words):
    return all(w and fold(w) not in NOT_NAMES and fold(w).strip(".") not in CREDENTIALS
               and not (len(w) >= 2 and w.isupper()) for w in words)


def names_in(task, providers=()):
    """(last, first) candidates written in the task, most explicit first. Provider names ("Amy Fuller, NP") are
    left out: they are staff, not the patient."""
    prov = {norm(p) for p in providers}
    out = []

    def add(last, first):
        if _ok_name(*last.split(), first) and norm(f"{first} {last}") not in prov:
            out.append((last, first))
    for m in NAME_LF.finditer(task):
        nxt = task[m.end():m.end() + 6]
        if re.match(r"\s*,?\s*(MD|DO|NP|PA|RN)\b", nxt):
            continue
        last, first = m.group(1), m.group(2)
        if fold(first) in CREDENTIALS:
            continue
        add(last, first)
    for rx in (NAME_POSS, NAME_FL):
        for m in rx.finditer(task):
            first, last = m.group(1), m.group(2)
            if re.match(r"\s*,\s*(MD|DO|NP|PA|RN)\b", task[m.end():m.end() + 6]):
                continue   # "Amy Fuller, NP"
            add(last, first)
    # any two capitalized words in a row (overlapping: "Is Judith Jackson" gives "Is Judith" and "Judith Jackson")
    toks = [(m.group(0), m.start(), m.end()) for m in re.finditer(_W, task)]
    for (w1, s1, e1), (w2, s2, e2) in zip(toks, toks[1:]):
        if not re.fullmatch(r"\s+", task[e1:s2]):
            continue
        if re.match(r"\s*,\s*(MD|DO|NP|PA|RN)\b", task[e2:e2 + 6]):
            continue
        add(w2, w1)
    return list(dict.fromkeys(out))


def _split(name):
    """'Last, First Middle' -> (last, first)."""
    n = re.sub(r"\s+(Restricted|Merged|Deleted|Test record)\b.*$", "", name or "").strip()
    if "," in n:
        last, first = [x.strip() for x in n.split(",", 1)]
    else:
        parts = n.split()
        first, last = " ".join(parts[:-1]), (parts[-1] if parts else "")
    return last, first


def name_match(row_name, last, first):
    rl, rf = _split(row_name)
    if norm(rl) != norm(last):
        return False
    if not first:
        return True
    f, r = norm(first), norm(rf)
    return r == f or r.split(" ")[:1] == f.split(" ")[:1]


def _flags(cells):
    return [f for f in ("Merged", "Deleted", "Restricted", "Deceased", "Inactive", "Test record")
            if any(f.lower() in c.lower() for c in cells)]


def active_of(rows):
    rows = [r for r in rows if "Test record" not in r.get("flags", [])]
    merged = [r for r in rows if "Merged" in r["flags"]]
    active = [r for r in rows if not {"Merged", "Deleted"} & set(r["flags"])] or merged
    return active, merged


class Found(dict):
    pass


def _found(row, merged, how, extra=None):
    f = Found(row)
    f["paths"] = list(dict.fromkeys([row["path"]] + [r["path"] for r in merged]))
    f["how"] = how
    f["extra"] = extra or []
    return f


def _rows_with_patient(data):
    """(patient cell, chart path, row links, cells) of every table row that links a chart."""
    out = []
    for t in data.get("tables", []):
        heads = [h.split(",")[0].strip().lower() for h in t.get("headers", [])]
        pi = next((i for i, h in enumerate(heads) if h.startswith("patient")), None)
        for r in t["rows"]:
            charts = [h for _, h in r["links"] if re.fullmatch(r"/patients/[^/?#]+", h.split("?")[0])]
            if not charts:
                continue
            cell = r["cells"][pi] if pi is not None and pi < len(r["cells"]) else r["cells"][0]
            out.append((cell, charts[0].split("?")[0], [h for _, h in r["links"]], r["cells"]))
    return out


def _time_hm(cell):
    m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", cell or "")
    if not m:
        return None
    h = int(m.group(1)) % 12 + (12 if m.group(3) == "PM" else 0)
    return h, int(m.group(2))


async def by_dob(site, dob, names):
    res = await clinic.find_patient(site, dob=dob.isoformat())
    rows = res.get("matches", [])
    # both names must match (twins share a last name and a birthday; accents and case are ignored by norm)
    hit = [r for r in rows if any(name_match(r["name"], l, f) for l, f in names)] if names else rows
    active, merged = active_of(hit)
    if len(active) == 1:
        return _found(active[0], merged, "dob"), rows
    return None, rows


async def by_documents(site, task, names, dates):
    kinds = [k for rx, k in DOC_KINDS if rx.search(task)]
    if not kinds or not dates:
        return None, []
    seen = []
    for d in dates[:2]:
        path = f"/documents?kind={kinds[0]}&from={d.isoformat()}&to={d.isoformat()}"
        data = await site.read(path)
        if data.get("error"):
            continue
        hits = {}
        for cell, chart, links, cells in _rows_with_patient(data):
            seen.append({"name": cell, "path": chart, "flags": _flags([cell]), "dob": "", "mrn": ""})
            if any(name_match(cell, l, f) for l, f in names):
                docs = [h for h in links if re.match(r"^/(documents|patients/[^/]+/files)/", h)]
                hits.setdefault(chart, {"name": re.sub(r"\s+Restricted$", "", cell), "path": chart, "mrn": "", "dob": "",
                                        "flags": _flags([cell]), "docs": []})["docs"] += [(docs[0] if docs else "", " | ".join(cells))]
        if len(hits) == 1:
            row = next(iter(hits.values()))
            return _found(row, [], f"documents {d}", extra=row["docs"]), seen
        if len(hits) > 1:
            return None, list(hits.values())
    return None, seen


async def by_appointments(site, task, names, dates):
    if not dates or not VISIT_WORDS.search(task):
        return None, []
    want_t = None
    tm = TIME_RE.search(re.sub(DATE_RE, " ", task))
    if tm:
        want_t = (int(tm.group(1)), int(tm.group(2)))
    seen = []
    for d in dates[:2]:
        path = f"/schedule/appointments?start={d.isoformat()}&end={d.isoformat()}"
        target = names[0] if names else None

        def stop(data, names=names):
            return any(any(name_match(c, l, f) for l, f in names) for c, _, _, _ in _rows_with_patient(data))
        pages = await site.walk_list(path, stop, max_pages=5)
        hits = {}
        for data in pages:
            for cell, chart, links, cells in _rows_with_patient(data):
                seen.append({"name": cell, "path": chart, "flags": _flags([cell]), "dob": "", "mrn": ""})
                if any(name_match(cell, l, f) for l, f in names):
                    if want_t:
                        tt = next((_time_hm(c) for c in cells if _time_hm(c)), None)
                        if tt and tt != want_t:
                            continue
                    appts = [h for h in links if re.search(r"/(appointments|recurring)/", h)]
                    hits.setdefault(chart, {"name": re.sub(r"\s+Restricted$", "", cell), "path": chart, "mrn": "",
                                            "dob": "", "flags": _flags([cell]), "appts": []})["appts"] += \
                        [(appts[0] if appts else "", " | ".join(cells))]
        if len(hits) == 1:
            row = next(iter(hits.values()))
            return _found(row, [], f"appointments {d}", extra=row["appts"]), seen
        if len(hits) > 1:
            return None, list(hits.values())
    return None, seen


def _key(row_name):
    l, f = _split(row_name)
    return (fold(l), fold(f))


async def by_name_walk(site, last, first, dob=None):
    """Walk the (phonetic, sorted) last-name search until the name is found or passed."""
    want = (fold(last), fold(first or ""))
    sp = await site.search_params() if hasattr(site, "search_params") else {"last": "lastName"}
    key = sp.get("last") or sp.get("query") or "lastName"

    def stop(data):
        rows = clinic._patient_rows(data)
        if not rows:
            return True
        if any(name_match(r["name"], last, first) for r in rows):
            # the same name can continue on the next page: stop only if the page goes past it
            return _key(rows[-1]["name"]) > want
        return _key(rows[-1]["name"]) > want
    pages = await site.walk_list(f"/patients?{key}={last.strip()}", stop)
    rows = [r for data in pages for r in clinic._patient_rows(data)]
    hit = [r for r in rows if name_match(r["name"], last, first)]
    if dob:
        hit = [r for r in hit if r["dob"] == dob.strftime("%m/%d/%Y")]
    return hit, rows


async def find(site, task, providers=(), budget=6.0):
    """Best effort within `budget` seconds. Returns (Found or None, candidate rows)."""
    names = names_in(task, providers)
    dob = dob_of(task)
    others = [d for d in task_dates(task) if d != dob]
    cands = []

    async def run():
        nonlocal cands
        if dob:
            f, rows = await by_dob(site, dob, names)
            cands += rows
            if f:
                return f
            if not names:
                return None
        if not names:
            return None
        if not dob and others:
            f, rows = await by_documents(site, task, names, others)
            cands += rows
            if f:
                return f
            f, rows = await by_appointments(site, task, names, others)
            cands += rows
            if f:
                return f
        for last, first in names[:2]:
            hit, rows = await by_name_walk(site, last, first, dob)
            active, merged = active_of(hit)
            if len(active) == 1:
                return _found(active[0], merged, "name search")
            if hit:
                cands += hit
                return None
        return None
    try:
        f = await asyncio.wait_for(run(), budget)
    except asyncio.TimeoutError:
        f = None
    except Exception as e:
        print(f"[finder] error {e!r}"[:200], flush=True)
        f = None
    # keep candidates that match a task name (the model gets them); dedupe by path
    out, seenp = [], set()
    for r in cands:
        if r.get("path") in seenp:
            continue
        if names and not any(name_match(r.get("name", ""), l, fi) for l, fi in names):
            continue
        seenp.add(r.get("path"))
        out.append(r)
    return f, out[:12]
