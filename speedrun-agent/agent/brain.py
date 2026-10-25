"""Solving one task (v41): deterministic paths first, then one short model loop that starts with the right pages
already open.

Order of work inside a task's (hard) deadline:
1. the patient finder (DOB search, the documents/appointments list of the task's date, a sorted name walk);
2. the deterministic solvers for kinds we know (counts, open slots, filing deadlines, claims, phone, referral);
3. the pages that answered earlier tasks of the same kind (route templates filled with this task's patient, dates,
   provider), plus the task's documents, all opened in parallel;
4. the model loop: lean prompt (site guide + only this kind's rule messages + the latest short messages), the
   pre-opened pages, and how the last tasks of this kind were answered. Most known kinds answer in one turn.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import time

from . import clinic, config, finder
from .fast import Fast
from .kinds import fill, slots_of
from .llm import BudgetExhausted
from .clinic import norm, parse_any_date

NOTES = open(os.path.join(os.path.dirname(__file__), "notes.md")).read()
EXTRA_NOTES = os.environ.get("AGENT_NOTES", "")

SYSTEM = """You answer back-office requests at a medical clinic using ONLY its records system, Wrenfield, which you \
read through the tools. You never change any data.

SCORING: a correct answer +1, a wrong answer -1, a skip 0. Answer when you are more likely right than wrong; skip \
(skip_task) when the data the answer depends on could not be read. Time is short (seconds): pages that are probably \
needed are ALREADY OPEN in the user message (opened by code for this task): use them, do not re-open them. When you \
need more, open several pages in ONE open_pages call. Do not double-check a clear answer: submit it.

TOOLS
- open_pages(paths, find): site paths (e.g. /patients/<id>/notes); find="a|b" shows only matching lines of long pages.
- find_patient(last_name, first_name, dob): chart lookup (dob = YYYY-MM-DD is fastest). A task's "Henry, Peter" is last name Henry.
- read_document(path): text of a document file (referral letters, typed reports). Scanned documents have no text: look_at_page.
- look_at_page(path): screenshot of a page's image (scanned document, paper remittance) for you to read.
- search_form(path, fields): fill a page's search form and submit it (fields by their form names, e.g. \
search_form("/billing", {"number": "32208721"}), search_form("/vaccines", {"lot": "M81X24L"}), \
search_form("/vaccines/notes", {"words": "M81X24L"})). Use it where a URL filter is ignored (the list comes back \
unfiltered).
- patient_contact(patient_path): phone/email/address as SHOWN on screen. Page-text phone digits are scrambled: \
for any phone question answer with this tool's "phone" (skip if safe_to_answer is false).
- appointment_history(patient_paths): every appointment incl. each date of recurring series with its status.
- new_or_established(...): applies a new-vs-established-patient rule exactly (fill the parameters from the rule).
- provider_info(name): specialty, id, active/inactive.
- python(code): run Python for date arithmetic / counting / sums. PAGES = {path: text} of pages opened so far.
- submit_answer(answer, confidence) / skip_task(reason).

HOW TO WORK
- Identify the right record: every detail must match (first and last name, date of birth, dates, provider). Several \
patients share names. Test records are not patients; deleted records do not count.
- Rule questions: the clinic's messages below define the rule and the EXACT answer form. Gather every input the rule \
needs, apply it step by step (use python for dates and sums), answer in that form. A later message overrides an \
earlier one on the same point.
- "Today" is the clinic date given below, not the real date.

ANSWER FORM (machine-compared)
- Rule answers: exactly the form the message gives, as ONE string (e.g. NURSE_REVIEW:2, WRITE_OFF:160.00).
- Otherwise just the value: whole numbers bare (12); amounts like 12.50; dates YYYY-MM-DD; names/addresses/IDs \
copied exactly as the product shows them, in the order the question asks; several items = a JSON list of strings.
- Never true/false, never an empty string.

{notes}
{extra}
<<DYNAMIC>>
CLINIC TODAY: {today}.

MESSAGES FROM THE CLINIC that may apply (in the order received; some may be chatter):
{messages}"""

TOOLS = [
    {"type": "function", "function": {
        "name": "open_pages",
        "description": "Open one or more Wrenfield pages (in parallel) and return their text, tables with row links, and forms.",
        "parameters": {"type": "object", "properties": {
            "paths": {"type": "array", "items": {"type": "string"}},
            "find": {"type": "string", "description": "Optional: only lines containing any of these |-separated words"},
        }, "required": ["paths"]}}},
    {"type": "function", "function": {
        "name": "find_patient",
        "description": "Find charts by last/first name and/or date of birth (YYYY-MM-DD).",
        "parameters": {"type": "object", "properties": {
            "last_name": {"type": "string"}, "first_name": {"type": "string"}, "dob": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "read_document",
        "description": "Text of a document's file, from its page (/patients/<id>/files/<doc> or /documents/<doc>).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "look_at_page",
        "description": "Screenshot of a page's visual content (scanned document, image) for you to read.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "search_form",
        "description": "Fill a page's search form (field name -> value) inside the page and submit it; returns the result page.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "fields": {"type": "object", "description": "form field name -> value, e.g. {\"lot\": \"M81X24L\"}"}},
            "required": ["path", "fields"]}}},
    {"type": "function", "function": {
        "name": "patient_contact",
        "description": "Phone, email and address of a chart as displayed on screen.",
        "parameters": {"type": "object", "properties": {"patient_path": {"type": "string"}}, "required": ["patient_path"]}}},
    {"type": "function", "function": {
        "name": "appointment_history",
        "description": "All appointments of a patient (chart list + every date of recurring series, with status).",
        "parameters": {"type": "object", "properties": {
            "patient_paths": {"type": "array", "items": {"type": "string"}}}, "required": ["patient_paths"]}}},
    {"type": "function", "function": {
        "name": "new_or_established",
        "description": "Apply a new-vs-established patient rule exactly and return the result with the evidence.",
        "parameters": {"type": "object", "properties": {
            "patient_paths": {"type": "array", "items": {"type": "string"}},
            "provider": {"type": "string"}, "visit_date": {"type": "string"},
            "excluded_services": {"type": "array", "items": {"type": "string"}},
            "years": {"type": "integer"},
            "counting_statuses": {"type": "array", "items": {"type": "string"}}},
            "required": ["patient_paths", "provider", "visit_date", "excluded_services", "years"]}}},
    {"type": "function", "function": {
        "name": "provider_info",
        "description": "A provider's specialty, id and status (Active/Inactive).",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "python",
        "description": "Run Python 3 and return what it prints. PAGES = {path: text}. datetime, re, math imported.",
        "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
    {"type": "function", "function": {
        "name": "submit_answer",
        "description": "Submit the final answer.",
        "parameters": {"type": "object", "properties": {
            "answer": {"description": "A string, a number, or a list of strings"},
            "confidence": {"type": "number", "description": "Probability 0..1 that it is exactly right"},
        }, "required": ["answer", "confidence"]}}},
    {"type": "function", "function": {
        "name": "skip_task",
        "description": "Skip (scores 0) when the answer cannot be determined.",
        "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}},
]

FINAL_PROMPT = """Time for this task is up: no more tools. From what you have already seen, give your best final \
answer in the exact answer form and the probability (0 to 1) that it is exactly right. A wrong answer costs a point: \
if you have not seen the data the answer depends on, give a low probability.
Reply with JSON only: {"answer": <answer or null>, "confidence": <0 to 1>}"""

DOC_WORDS = re.compile(r"\b(reports?|letters?|records?|documents?|statements?|scans?|eobs?|explanation of benefits|"
                       r"results?|panel|questionnaire|court order|eligibility)\b", re.I)


def run_python(code, pages, timeout=5):
    pages_file = os.path.join(config.WORK_DIR, f"pages-{os.getpid()}-{time.time_ns()}.json")
    with open(pages_file, "w") as f:
        json.dump(pages, f)
    prelude = ("import json, re, math, datetime\nfrom datetime import date, timedelta, datetime as dt\n"
               f"PAGES = json.load(open({pages_file!r}))\n")
    try:
        r = subprocess.run([sys.executable, "-c", prelude + code], capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + ("\nSTDERR: " + r.stderr[-1200:] if r.returncode else ""))
    except subprocess.TimeoutExpired:
        out = "timeout"
    finally:
        try:
            os.remove(pages_file)
        except OSError:
            pass
    return out[:4000] or "(no output)"


# kinds whose answers are a rule message's codes (RELEASE, WRITE_OFF:..., NOT_REQUIRED:INSURED, UNKNOWN_LOT, ...)
RULE_KINDS = {"lab", "tetanus", "claim_next_step", "filing_deadline", "good_faith_estimate", "recall_count",
              "new_established"}
DATE_ANY = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4}|\b[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}")
TASK_DOB = re.compile(r"(?:born|DOB|date of birth|birth ?date)\s*:?\s*(?:on\s+)?(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})", re.I)


def appt_when(task):
    """(appointment date, 'HH:MM') of a task: its date that is not the date of birth, and its 24-hour time."""
    m = TASK_DOB.search(task)
    dob = parse_any_date(m.group(1)) if m else None
    dates = [d for d in (parse_any_date(x) for x in DATE_ANY.findall(task)) if d and d != dob]
    t = re.search(r"\b(\d{1,2}):(\d{2})\b", task)
    return (dates[0] if dates else None), (f"{int(t.group(1)):02d}:{t.group(2)}" if t else None)


def text_matches_patient(txt, found, task=""):
    """True if a document's text layer shows the found patient's last name and (when known) date of birth: then it
    can be trusted without its image. False when it cannot be checked."""
    if not found or len(txt) < 150:
        return False
    last = norm(re.sub(r"\s+(Restricted|Merged|Test record|Deleted)\b.*$", "", found.get("name") or "").split(",")[0])
    if not last or f" {last} " not in f" {norm(txt)} ":
        return False
    dob = parse_any_date(found.get("dob") or "")
    if not dob:
        m = TASK_DOB.search(task or "")
        dob = parse_any_date(m.group(1)) if m else None
    if not dob:
        return True
    return dob in {parse_any_date(x) for x in DATE_ANY.findall(txt)}


def clean_answer(a):
    if isinstance(a, str):
        a = a.strip()
        if len(a) >= 2 and a[0] == a[-1] and a[0] in "\"'`":
            a = a[1:-1].strip()
        if a.startswith("[") and a.endswith("]"):
            try:
                v = json.loads(a)
                if isinstance(v, list):
                    return v
            except Exception:
                pass
        return a
    if isinstance(a, bool):
        return None
    if isinstance(a, (int, float)):
        return a
    if isinstance(a, list):
        return [str(x).strip() if not isinstance(x, (int, float)) else x for x in a if str(x).strip()]
    return None


def plausible(task, answer):
    t = task.lower()
    vals = answer if isinstance(answer, list) else [answer]
    s = " ".join(str(v) for v in vals).strip()
    if not s or re.fullmatch(r"(?i)(true|false|none|null|n/?a|unknown|not found|skip)", s):
        return False
    if re.search(r"\bhow many\b", t) and not isinstance(answer, list):
        return bool(re.fullmatch(r"\$?-?[\d,]+(\.\d+)?%?|[A-Z_]+(:[^\s]*)?", s))
    if re.search(r"\bwhat\b[^?]{0,30}\bphone\b", t) and not isinstance(answer, list):
        return len(re.sub(r"\D", "", s)) in (10, 11)
    return True


def parse_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None


class Brain:
    def __init__(self, site, llm, rules, kinds):
        self.site, self.llm, self.rules, self.kinds = site, llm, rules, kinds
        self.fast = Fast(site, llm, rules)
        self.turn_secs = 2.0
        self.directory = {"prov": {}, "loc": {}}   # name -> id, from the appointment list form

    # ------------------------------------------------------------------ helpers
    async def load_directory(self):
        try:
            base = await self.site.read("/schedule/appointments", all_pages=False)
            for s in base.get("selects", []):
                name = (s.get("name") or "").lower()
                if name in ("provider", "location"):
                    key = "prov" if name == "provider" else "loc"
                    for o in s["options"]:
                        if o["value"]:
                            self.directory[key][norm(re.sub(r"\(inactive\)", "", o["text"]))] = o["value"]
            print(f"[brain] directory: {len(self.directory['prov'])} providers, {len(self.directory['loc'])} locations",
                  flush=True)
        except Exception as e:
            print(f"[brain] directory failed: {e!r}"[:200], flush=True)

    def ids_for(self, task):
        """Provider and location ids of the names written in the task (longest name first)."""
        low = " " + norm(task) + " "
        out = {}
        for key in ("prov", "loc"):
            hits = [(len(n), v) for n, v in self.directory[key].items()
                    if n and (f" {n} " in low or f" {norm(n.split(',')[0])} " in low)]
            if hits:
                out[key] = max(hits)[1]
        return out

    def providers(self):
        return [p["name"] for p in (getattr(self.site, "_providers", None) or [])]

    def system_prompt(self, task):
        msgs = self.rules.for_task(task)
        return (SYSTEM.replace("{notes}", NOTES).replace("{extra}", EXTRA_NOTES)
                .replace("{today}", getattr(self.site, "today", "") or "see the dashboard at /")
                .replace("{messages}", msgs))

    # ------------------------------------------------------------------ context
    async def find(self, task, deadline):
        """The task's patient (agent/finder.py), within ~45% of the time left. Returns (found, candidates, slots)."""
        t0 = time.time()
        budget = max(2.5, min(7.0, 0.5 * (deadline - t0)))
        found, cands = await finder.find(self.site, task, self.providers(), budget=budget)
        if found:
            self.site.found_cache[task] = found
        names = finder.names_in(task, self.providers())
        ids = self.ids_for(task)
        if found:
            ids["pid"] = found["path"].rstrip("/").split("/")[-1]
        print(f"[finder] {time.time() - t0:.1f}s patient={'yes:' + found['how'] + ' ' + found['path'] if found else 'no'} "
              f"cands={len(cands)} names={names[:2]}", flush=True)
        return found, cands, slots_of(task, names, ids)

    async def prefetch(self, task, kind, deadline, found, cands, slots):
        """Text for the first prompt: the patient, then the pages that answered earlier tasks of this kind (filled
        with this task's values) and the task's documents, opened in parallel. Returns (text, opened texts)."""
        t0 = time.time()
        parts, opened = [], {}
        if found:
            flags = " ".join(found.get("flags", [])) or "-"
            parts.append(f"THE PATIENT (found by code via {found['how']}): {found['name']} | DOB {found.get('dob') or '?'} "
                         f"| {flags} -> {found['path']}"
                         + (f" (merged duplicates: {', '.join(found['paths'][1:])})" if len(found["paths"]) > 1 else ""))
            for link, line in found.get("extra", [])[:4]:
                parts.append(f"  matching row: {line} -> {link}")
            if "Restricted" in found.get("flags", []):
                parts.append("NOTE: this chart is RESTRICTED (do not open it).")
        elif cands:
            parts.append("Patient candidates (no unique match; check name/DOB):\n" +
                         "\n".join(f"- {r.get('name')} | DOB {r.get('dob') or '?'} | {' '.join(r.get('flags', [])) or '-'} "
                                   f"-> {r.get('path')}" for r in cands[:10]))
        paths = []
        for t in kind.templates():
            p = fill(t, slots)
            if p and p not in paths:
                paths.append(p)
        restricted = bool(found and "Restricted" in found.get("flags", []))
        if found and not restricted and DOC_WORDS.search(task) and not any(p.endswith(("/files", "/documents")) for p in paths):
            paths.append(found["path"] + "/files")
        if restricted:
            paths = [p for p in paths if not p.startswith(found["path"])]
        paths = paths[:5]
        searches = []
        for path, fields in (kind.play.searches if kind.play else []):
            f = {k: fill(v, slots) for k, v in fields.items()}
            if all(f.values()):
                searches.append((path, f))
        pages = []
        left = deadline - time.time()
        if (paths or searches) and left > 2.5:
            async def run_searches():
                out = []
                for path, f in searches:     # one at a time: each takes a tab for a few seconds
                    d = await self.site.submit_form(path, f, timeout=min(6.0, max(2.0, deadline - time.time() - 3)))
                    out.append(d)
                    links = {h for t in d.get("tables", []) for r in t["rows"] for _, h in r["links"]
                             if kind.play.follow and re.fullmatch(kind.play.follow, h)} if not d.get("error") else set()
                    if len(links) == 1 and deadline - time.time() > 3:
                        out += await self.site.read_many([links.pop()])
                return out
            try:
                got = await asyncio.wait_for(asyncio.gather(self.site.read_many(paths) if paths else asyncio.sleep(0, []),
                                                            run_searches()),
                                             max(1.0, min(7.0, 0.55 * left)))
                pages = list(got[0] or []) + list(got[1] or [])
            except Exception:
                pages = []
        if kind.play and kind.play.name == "good_faith_estimate" and found and deadline - time.time() > 3.5:
            extra = self.gfe_pages(task, pages)
            if extra:   # the appointment's own page (Booking date, History) and the clinic calendar of its location
                try:
                    pages = list(pages) + list(await asyncio.wait_for(
                        self.site.read_many(extra), max(1.0, min(4.0, 0.5 * (deadline - time.time())))))
                except Exception:
                    pass
        doc_reads = []
        for p in pages:
            if p.get("error"):
                continue
            opened[p["path"]] = p.get("text", "")
            parts.append("PRE-OPENED PAGE:\n" + self.site.render(p, max_chars=3500))
            if p["path"].endswith(("/files", "/documents")) and DOC_WORDS.search(task):
                doc_reads += pick_documents(p, task)
        for link, line in (found or {}).get("extra", [])[:2]:
            if link and re.search(r"/(documents|files)/", link) and link not in [h for h, _ in doc_reads]:
                doc_reads.insert(0, (link, line))
        doc_reads = list(dict.fromkeys(doc_reads))[:3]
        docs = []
        if doc_reads and deadline - time.time() > 3.5:
            for h, line in doc_reads:   # one at a time: the clinic serves the file of the open document
                if time.time() > deadline - 3.0:
                    break
                try:
                    d = await asyncio.wait_for(self.site.read_document(h), max(1.0, min(4.0, deadline - time.time() - 2.5)))
                except Exception:
                    d = {}
                docs.append((h, line, d))
        images = []
        # Lab reports and outside immunization records: some text layers are deliberately wrong (another patient's
        # name or date of birth, v29 SITE_MAP). Their image goes in only then: when the text does not show this
        # patient's last name and date of birth (an image costs ~2-4 s; v41 attached one for every such task).
        see_too = bool(kind.play and kind.play.name in ("lab", "tetanus"))
        for h, line, d in docs:
            txt = (d.get("text") or "").strip()
            if txt:
                opened["doc:" + h] = txt
                parts.append(f"DOCUMENT {h} ({line}):\n{txt[:3000]}")
                if see_too and not images and not text_matches_patient(txt, found, task) \
                        and deadline - time.time() > 4.5:
                    try:
                        shots = await asyncio.wait_for(self.site.look(h, max_images=1),
                                                       max(1.0, min(3.5, deadline - time.time() - 3.5)))
                    except Exception:
                        shots = []
                    if shots:
                        images += shots[:1]
                        opened["look:" + h] = ""
                        parts.append(f"(the image of {h} is attached below as image {len(images)}: if its text above "
                                     f"looks garbled, read the values from the image)")
                continue
            # a scan: its image goes into the first prompt (saves the model a look_at_page turn)
            shots = []
            if len(images) < 3 and deadline - time.time() > 4.5:
                try:
                    shots = await asyncio.wait_for(self.site.look(h, max_images=2), max(1.0, min(4.0, deadline - time.time() - 3.5)))
                except Exception:
                    shots = []
            if shots:
                images += shots[:2]
                opened["look:" + h] = ""
                parts.append(f"DOCUMENT {h} ({line}): a scan, its image is attached below (image {len(images) - len(shots[:2]) + 1}"
                             f"{'-' + str(len(images)) if len(shots[:2]) > 1 else ''})")
            else:
                parts.append(f"DOCUMENT {h} ({line}): no text layer (a scan): use look_at_page on {h} to read it")
        print(f"[context] {time.time() - t0:.1f}s pages={len(pages)}/{len(paths)} docs={len(docs)} images={len(images)}",
              flush=True)
        return "\n\n".join(parts), opened, images

    def gfe_pages(self, task, pages):
        """For a good faith estimate: the appointment row of the task's date and time on the chart's Appointments
        tab -> its page, and the clinic calendar (/settings?year=&location=) of that row's location."""
        day, hhmm = appt_when(task)
        if not day:
            return []
        rows = []
        for p in pages:
            if p.get("error") or not p.get("path", "").endswith("/appointments"):
                continue
            for t in p.get("tables", []):
                for r in t["rows"]:
                    links = [h for _, h in r["links"] if re.fullmatch(r"/patients/[^/]+/appointments/[^/?#]+", h)]
                    when = [x for x in (clinic.parse_dt(c) for c in r["cells"]) if x]
                    if links and any(w[0] == day for w in when):
                        rows.append((r, links[0], any(w[1] == hhmm for w in when) if hhmm else False))
        if len(rows) > 1:
            rows = [x for x in rows if x[2]]
        if len(rows) != 1:
            return []
        r, link, _ = rows[0]
        out = [link]
        locs = self.directory.get("loc", {})
        for c in r["cells"]:
            lid = locs.get(norm(c))
            if lid:
                out.append(f"/settings?year={day.year}&location={lid}")
                break
        return out

    # ------------------------------------------------------------------ solve
    async def solve(self, task, kind, deadline, mode="normal", tight=False):
        """('answer'|'skip', value, info). Never runs past the deadline by more than ~1 s."""
        t0 = time.time()
        found, cands, slots = None, [], {}
        from . import solvers
        fast_tried = False

        async def try_fast():
            left = deadline - time.time()
            if left < 1.2:
                return None
            try:
                share = 0.8 if kind.play and not kind.play.patient else 0.6   # counts: no finder runs after
                return await asyncio.wait_for(self.fast.solve(task), max(1.0, min(share * left, 10)))
            except BudgetExhausted:
                raise
            except Exception as e:
                print(f"[fast] {e!r}"[:200], flush=True)
                return None
        if any(r.search(task) for r in (solvers.SLOTS, solvers.COUNT_ANY, solvers.LAB, solvers.INVOICE)):
            fast_tried = True   # counts, lab coverage and invoices (billing search) need no patient: solver first
            res = await try_fast()
            if res:
                res[2].update(src="fast", slots=slots_of(task, [], self.ids_for(task)))
                return res
        try:
            if kind.play and not kind.play.patient:
                pass    # a count, slots or recall task names no patient: no chart search (v40 spent seconds on it)
            else:
                found, cands, slots = await asyncio.wait_for(self.find(task, deadline),
                                                             max(2.5, min(7.0, 0.5 * (deadline - t0))) + 0.5)
        except asyncio.TimeoutError:
            print("[finder] timed out", flush=True)
        except BudgetExhausted:
            raise
        except Exception as e:
            print(f"[finder] failed: {e!r}"[:200], flush=True)
        if not slots:
            slots = slots_of(task, finder.names_in(task, self.providers()), self.ids_for(task))
        if not fast_tried and self.fast.matches(task):
            res = await try_fast()
            if res:
                res[2].update(src="fast", slots=slots)
                return res
        info = {"route": [], "src": "-", "slots": slots}
        if tight and config.EARLY_EXIT and kind.play is not None and kind.play.patient and not found and not cands:
            # v48: off track. With ~4 s per task (Sets 2/3) a try whose patient was not found almost never answers but
            # used to run to its full cap; dropping it now keeps those seconds for tasks that are on track.
            return "skip", None, {**info, "why": "early exit: patient not found"}
        if mode == "fast-only":
            return "skip", None, {**info, "why": "no deterministic answer; model loop not allowed"}
        if self.llm.budget_gone or self.llm.spent >= config.BUDGET * config.LOOP_BUDGET_SHARE:
            return "skip", None, {**info, "why": "model budget"}
        ctx_text, opened, images = "", {}, []
        try:
            ctx_text, opened, images = await asyncio.wait_for(self.prefetch(task, kind, deadline, found, cands, slots),
                                                      max(1.0, 0.5 * (deadline - time.time())))
        except asyncio.TimeoutError:
            print("[context] timed out", flush=True)
        except BudgetExhausted:
            raise
        except Exception as e:
            print(f"[context] failed: {e!r}"[:200], flush=True)
        if tight and config.EARLY_EXIT and not opened and not found and kind.play is not None:
            return "skip", None, {**info, "why": "early exit: no page could be opened for this task"}
        hint = self.kinds.hint(kind, task)
        kind_, value, info2 = await self.loop(task, deadline, ctx_text, hint, opened, images)
        info2["slots"] = slots
        info2["pid"] = found["path"] if found else None
        if kind_ == "answer" and not plausible(task, value):
            kind_, info2 = "skip", {**info2, "why": f"implausible answer {value!r}"[:150]}
        if kind_ == "answer" and not self.known_code(value, kind):
            kind_, info2 = "skip", {**info2, "why": f"answer code in no clinic message {value!r}"[:150]}
        return kind_, value, info2

    def known_code(self, value, kind):
        """A rule answer's CODE (NURSE_REVIEW in NURSE_REVIEW:2) must be one a clinic message or Set 1 used: a made-up
        code is always wrong."""
        if not isinstance(value, str):
            return True
        m = re.match(r"([A-Z][A-Z_]{3,})(?::|$)", value.strip())
        if not m:
            return True
        code = m.group(1)
        rule_kind = bool(kind.play and kind.play.name in RULE_KINDS)
        if "_" not in code and ":" not in value and not rule_kind:
            return True     # a plain all-caps word outside the rule kinds (a name, a payer) is not a code
        if any(code in t for t in self.rules.items):
            return True
        return bool(kind.play and any(f.split(":")[0] == code for f in kind.play.forms))

    async def loop(self, task, deadline, ctx_text, hint, opened, images=()):
        t0 = time.time()
        user = f"TASK:\n{task}"
        if ctx_text:
            user += "\n\n" + ctx_text
        if hint:
            user += "\n\n" + hint
        first = user if not images else [{"type": "text", "text": user}] + \
            [{"type": "image_url", "image_url": {"url": u}} for u in images]
        convo = [{"role": "system", "content": self.system_prompt(task)}, {"role": "user", "content": first}]
        route = [p if not p.startswith("look:") else p[5:] for p in opened if not p.startswith("doc:")]
        opened_text = dict(opened)
        for turn in range(config.MAX_TURNS):
            left = deadline - time.time() - (config.FINAL_RESERVE if turn else 0)
            if left < min(self.turn_secs, 2.5):
                return await self.final(convo, task, deadline, route, t0, "time")
            self._compact(convo)
            try:
                msg, usage, dt_ = await asyncio.wait_for(self.llm.chat(convo, TOOLS, timeout=max(4, left)), left)
            except BudgetExhausted:
                raise
            except Exception as e:
                return await self.final(convo, task, deadline, route, t0, f"llm {e!r}"[:60])
            self.turn_secs = 0.8 * self.turn_secs + 0.2 * dt_
            calls = msg.get("tool_calls") or []
            convo.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls} if calls
                         else {"role": "assistant", "content": msg.get("content") or ""})
            note = (msg.get("content") or "").strip().replace("\n", " ")[:200]
            print(f"[turn] {turn + 1} {dt_:.1f}s tok={usage.get('prompt_tokens')}/{usage.get('completion_tokens')} "
                  + " ; ".join(f"{c['function']['name']}({c['function'].get('arguments', '')[:180]})" for c in calls)
                  + (f" | says: {note}" if note else ""), flush=True)
            if not calls:
                ans = parse_json(msg.get("content"))
                if isinstance(ans, dict) and "answer" in ans:
                    calls = [{"id": "x", "function": {"name": "submit_answer", "arguments": json.dumps(ans)}}]
                else:
                    convo.append({"role": "user", "content": "Use a tool, or finish with submit_answer or skip_task."})
                    continue
            images = []
            for c in calls:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except Exception:
                    args = {}
                if name == "submit_answer":
                    ans = clean_answer(args.get("answer"))
                    try:
                        conf = float(args.get("confidence") or 0)
                    except (TypeError, ValueError):
                        conf = 0.0
                    info = {"route": route, "conf": conf, "turns": turn + 1, "src": "loop"}
                    if ans in (None, "", []):
                        return "skip", None, {**info, "why": "empty"}
                    if conf < config.MIN_CONFIDENCE:
                        return "skip", ans, {**info, "why": f"low confidence {conf}"}
                    return "answer", ans, info
                if name == "skip_task":
                    return "skip", None, {"why": "model: " + str(args.get("reason"))[:150], "route": route,
                                          "turns": turn + 1, "src": "loop"}
                result = await self._tool(name, args, deadline, route, opened_text, images)
                convo.append({"role": "tool", "tool_call_id": c.get("id", name), "content": result})
            if images:
                convo.append({"role": "user", "content": [{"type": "text", "text": "Screenshots you asked for:"}] +
                              [{"type": "image_url", "image_url": {"url": u}} for u in images]})
        return await self.final(convo, task, deadline, route, t0, "max turns")

    async def _tool(self, name, args, deadline, route, opened_text, images):
        site = self.site
        left = max(1.5, deadline - time.time())
        try:
            if name == "open_pages":
                paths = [p for p in (args.get("paths") or []) if isinstance(p, str)][:6]
                try:
                    pages = await asyncio.wait_for(site.read_many(paths), left)
                except asyncio.TimeoutError:
                    pages = [{"path": p, "error": "timed out"} for p in paths]
                site.learn_nav(pages)
                for p in pages:
                    if not p.get("error"):
                        opened_text[p["path"]] = p.get("text", "")
                        route.append(p["path"])
                return "\n\n".join(site.render(p, find=args.get("find")) for p in pages) or "no paths given"
            if name == "look_at_page":
                shots = await asyncio.wait_for(site.look(str(args.get("path", "/"))), left)
                route.append(site._normalize(str(args.get("path", "/"))))
                images.extend(shots)
                return f"{len(shots)} screenshot(s) attached in the next message." if shots else "no visual content found"
            if name == "python":
                return await asyncio.to_thread(run_python, args.get("code", ""), opened_text, max(1, min(5, left)))
            if name == "search_form":
                fields = {str(k): str(v) for k, v in (args.get("fields") or {}).items()} if isinstance(args.get("fields"), dict) else {}
                if not fields:
                    return json.dumps({"error": "fields must be an object of form field name -> value"})
                data = await asyncio.wait_for(site.submit_form(str(args.get("path") or "/"), fields, timeout=min(8.0, left)), left)
                if not data.get("error"):
                    opened_text[data["path"]] = data.get("text", "")
                    route.append(data["path"])
                return site.render(data, find=args.get("find"))
            res = await asyncio.wait_for(self._fast_tool(name, args), left)
            if name == "read_document":
                route.append(site._normalize(str(args.get("path", ""))))
                if isinstance(res, dict) and res.get("text"):
                    opened_text["doc:" + str(args.get("path"))] = res["text"]
            elif name == "patient_contact":
                route.append(site._normalize(str(args.get("patient_path", ""))))
            out = json.dumps(res, ensure_ascii=False, default=str)[:config.PAGE_CHARS]
            print(f"[tool] {name} -> {out[:300]}", flush=True)
            return out
        except asyncio.TimeoutError:
            return json.dumps({"error": "timed out"})
        except BudgetExhausted:
            raise
        except Exception as e:
            return json.dumps({"error": f"{e!r}"[:300]})

    async def _fast_tool(self, name, a):
        site = self.site
        if name == "find_patient":
            return await clinic.find_patient(site, a.get("last_name"), a.get("first_name"), a.get("dob"))
        if name == "appointment_history":
            res = await clinic.appointment_history(site, a.get("patient_paths") or [])
            res["appointments"] = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()
                                    if k in ("date", "time", "type", "provider", "location", "status", "source")}
                                   for r in res["appointments"][:120]]
            return res
        if name == "new_or_established":
            ne = self.rules.ne
            return await clinic.new_or_established(
                site, a.get("patient_paths") or [], a.get("provider", ""), a.get("visit_date", ""),
                ne["excluded"] if ne else a.get("excluded_services") or [], ne["years"] if ne else a.get("years") or 3,
                ne["statuses"] if ne else a.get("counting_statuses") or ["Completed"])
        if name == "patient_contact":
            return await clinic.patient_contact(site, self.llm, str(a.get("patient_path", "")))
        if name == "read_document":
            res = await site.read_document(str(a.get("path", "")))
            if res.get("text"):
                res["text"] = res["text"][:6000]
            return res
        if name == "provider_info":
            provs = await site.providers()
            spec = await site.provider_specialty(a.get("name", ""))
            from .site import norm_name
            key = norm_name(a.get("name", ""))
            m = [p for p in provs if norm_name(p["name"]) == key or norm_name(p["name"].split(",")[0]) == norm_name(key.split(",")[0])]
            return {"name": a.get("name"), "specialty": spec,
                    "matches": [{"name": p["name"], "status": p["group"] or "?", "id": p["value"].rsplit("/", 1)[-1]} for p in m]}
        return {"error": "unknown tool"}

    async def final(self, convo, task, deadline, route, t0, why):
        info = {"route": route, "src": "final"}
        left = deadline - time.time() + 1.0
        read = sum(len(m["content"]) for m in convo if m["role"] == "tool" and isinstance(m.get("content"), str))
        c1 = convo[1].get("content", "")
        read += (len(c1) if isinstance(c1, str) else sum(len(p.get("text", "")) + (2000 if p.get("type") == "image_url" else 0)
                                                          for p in c1)) - len(task) - 10
        if left < 1.5 or read < config.FINAL_MIN_READ:
            return "skip", None, {**info, "why": why + (" (nothing read)" if read < config.FINAL_MIN_READ else "")}
        msgs = convo + [{"role": "user", "content": FINAL_PROMPT}]
        try:
            msg, usage, dt_ = await asyncio.wait_for(
                self.llm.chat(msgs, TOOLS, max_tokens=300, timeout=max(2, left), reasoning="none", tool_choice="none"), left)
        except BudgetExhausted:
            raise
        except Exception as e:
            return "skip", None, {**info, "why": f"{why}; final {e!r}"[:120]}
        out = parse_json(msg.get("content")) or {}
        ans = clean_answer(out.get("answer"))
        try:
            conf = float(out.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        info["conf"] = conf
        print(f"[final] {why}: {ans!r} conf={conf} in {dt_:.1f}s", flush=True)
        if ans in (None, "", []) or conf < config.FINAL_MIN_CONFIDENCE:
            return "skip", None, {**info, "why": f"{why}; final guess too unsure ({conf})"}
        return "answer", ans, {**info, "why": f"{why}; final best answer"}

    @staticmethod
    def _compact(convo, keep_last=3, limit=2500):
        tool_idx = [i for i, m in enumerate(convo) if m["role"] == "tool"]
        for i in tool_idx[:-keep_last] if len(tool_idx) > keep_last else []:
            c = convo[i]["content"]
            if len(c) > limit:
                convo[i]["content"] = c[:limit] + "\n...[older output shortened]"


STOPW = set("""the a an of for to in on at by with and or is was are be do does did what which who how many much when
where our we this that these those it its from report received please patient need needs call nurse review release
provider decide lab""".split())


def pick_documents(data, task, limit=3):
    """Document rows worth reading for this task: the task's date and title words, then same-title siblings
    (rules often compare with a previous report)."""
    dates = [d for d in (parse_any_date(s) for s in finder.DATE_RE.findall(task)) if d]
    words = {w for w in re.findall(r"[a-z]{4,}", task.lower()) if w not in STOPW}
    scored = []
    for t in data.get("tables", []):
        for r in t["rows"]:
            hrefs = [h for _, h in r["links"] if re.search(r"/(files|documents)/[^/?]+", h)]
            if not hrefs:
                continue
            line = " | ".join(r["cells"])
            date_hit = any(parse_any_date(c) in dates for c in r["cells"] if parse_any_date(c))
            title = r["cells"][0] if r["cells"] else line
            overlap = len(words & set(re.findall(r"[a-z]{4,}", title.lower())))
            score = (3 if date_hit else 0) + overlap
            if score > 0:
                scored.append((score, date_hit, title, hrefs[0], line))
    scored.sort(key=lambda x: (-x[0], not x[1]))
    if not scored:
        return []
    best_title = norm(scored[0][2])
    out = [s for s in scored if s[0] == scored[0][0]][:2]
    out += [s for s in scored if norm(s[2]) == best_title and s not in out]
    return [(s[3], s[4]) for s in out[:limit]]
