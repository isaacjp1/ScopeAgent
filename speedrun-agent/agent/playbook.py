"""What Set 1 taught about each kind of task, applied to every set (v41).

Sets 2, 3 and the final set are other clinics with other patients, so Set 1's answers never match there. But the
requests are written the same way ("Next step on claim: ...", "What's still owed on invoice ...", "... lab report
... received ...") and the product is the same, so what carries over is:
- how to RECOGNISE the kind from its wording (v40 grouped invoice and count tasks with the lab and tetanus rules by
  word overlap, then wrote those kinds off and skipped everything: Set 3 stalled);
- which PAGES answer it (opened before the first model call, filled with this task's patient, dates, provider);
- HOW it was worked, as a short procedure plus a worked example with its confirmed answer.
The clinic's own rule messages still decide the answer: a set may change a threshold or an answer form.

Every regex below was checked against all 224 Set 1 tasks (test/test_v41.py)."""
import collections
import re
from dataclasses import dataclass, field


@dataclass
class Play:
    name: str
    match: re.Pattern
    pages: list = field(default_factory=list)   # templates: {pid} {d0} {d1} {prov} {loc} {c0} {n0} {last}
    hint: str = ""
    examples: list = field(default_factory=list)   # (task, answer, how)
    proven: bool = True     # Set 1 answered this kind live: start replaying, no exploring needed
    skip_hard: bool = False  # Set 1 never answered it within the time: one exploring try, then deterministic only
    forms: list = field(default_factory=list)   # what Set 1's confirmed answers of this kind looked like
    searches: list = field(default_factory=list)   # (path, {form field: template}) submitted in the page before
    follow: str = ""        # a result row link to open too when the search finds exactly one (regex)
    set1_rate: float = None  # share of Set 1's tasks of this kind with a confirmed answer (shrunk), None if unseen
    set1_dist: str = ""     # Set 1's confirmed answers of this kind by form ("RELEASE 12, NURSE_REVIEW 9, ...")
    confirmed: int = 0      # Set 1 answers of this kind confirmed by the judge (agent/known_set1.py)
    patient: bool = True    # False: the task names no patient (counts, slots, recall): the finder is skipped


def R(p):
    return re.compile(p, re.I | re.S)


PLAYS = [
    Play("filing_deadline", R(r"deadline to file|filing deadline|can we still file|not-yet-filed|last day to file|timely filing|"
           r"\b(file|bill|submit)\b.{0,40}\bclaim\b.{0,40}\b(by when|deadline|in time|still)\b"),
         ["/patients/{pid}/insurance"],
         "Claims not yet filed (in the chart's Insurance tab) -> the row with the date of service: its type (Original/"
         "Secondary/Corrected), Bill to payer, remittance dates. Then the payer's page /payers/<id> (link from the "
         "coverage row or /payers): Claim filing table, the row in effect on the date of service. Count days/months, "
         "move back off weekends and the office holidays the rule lists. The Claims area is NOT this claim.",
         [("Anderson, Alexander, DOB 1971-07-30, date of service 2026-08-31. We haven't billed this one yet. "
           "What's the deadline to file?", "2027-02-26", "insurance tab -> payer page Claim filing table")]),
    Play("claim_next_step", R(r"next step on (the )?claim|\bthe claim for\b|\bclaim\b.{0,80}\b(next step|what('s| is) next|"
           r"what (should|do) we do|how (should|do) we (handle|work))|\b(next step|what('s| is) next)\b.{0,80}\bclaim\b|"
           r"\bremittance\b|\bdenied claim|\bclaim\b.{0,30}\bdenied\b"),
         ["/patients/{pid}/claims"],
         "Patient's Claims tab -> the claim with that service date -> /claims/<id>: Remittances (current = latest "
         "payment not reversed by a later 'Reversal of <trace>'), its lines' adjustments (CO-16/22/29/97/197 deny; "
         "PR-1/2/3 patient owes), Submissions, Authorizations, Account notes. A PAPER remittance ('Received on paper') "
         "is scanned into the patient's Documents (/patients/<id>/files): look_at_page on that file to read its "
         "lines. Appeal days: the payer contract page /claims/payers/<id> ('Appeals accepted within'), unless a "
         "clinic message overrides it. Reason 22: the most recent account note about other insurance decides.",
         [("Next step on claim: Payne, Roger, DOB 1964-04-07, service date 2026-07-16", "CONTACT_PATIENT",
           "claims tab -> claim page: reversal of the first payment, current remittance CO-22 -> latest note: plan is "
           "the spouse's -> CONTACT_PATIENT"),
          ("Could you look at the claim for Dorothy Williams, born 1978-02-11, with the date of service 2025-10-23, "
           "and tell me the next step?", "WRITE_OFF:190.00",
           "claim page: current remittance received on paper -> patient files -> the scanned remittance (look_at_page)"
           " -> denied amount 190.00, no grounds -> WRITE_OFF")]),
    Play("lab", R(r"\blab(oratory)? (report|result)s?\b|\b(complete blood count|metabolic panel|thyroid panel|lipid panel|"
           r"liver function panel)\b.{0,80}\b(report|result|received)"),
         ["/patients/{pid}/files", "/patients/{pid}/problems", "/patients/{pid}"],
         "Documents tab -> the report of that panel RECEIVED on the task's date (a report filed twice has two "
         "received dates). Its text layer is often garbled: read the scan IMAGE (attached, or look_at_page). Check "
         "the record number printed on the report matches the chart (else ignore that report). Previous report = "
         "same panel, latest COLLECTED date before this one, within 12 months, different report number. Sex and "
         "date of birth from the chart header/Demographics (age on the collected date); diabetes from Problems. "
         "Apply the clinic's latest lab rule messages (a later message can exclude a panel from a date on).",
         [("Next step for a lab report: Billy Nguyen, Complete blood count, received 2025-07-05.", "NURSE_REVIEW:2",
           "documents tab -> report of that date (image) + previous CBC -> problems"),
          ("What happens to the Complete blood count lab report for Bradley Owens (born 1955-07-17), received "
           "2025-10-09?", "RELEASE", "files -> report image -> nothing out of range or changing past the limit")]),
    Play("tetanus", R(r"\btetanus\b|\btdap\b|\btetanus immune globulin|\bwound (visit|care)\b|\bwith a wound\b"),
         ["/patients/{pid}/notes", "/patients/{pid}/immunizations", "/patients/{pid}/files"],
         "Notes: a note written ON the visit date whose text starts with 'Triage:' (none -> NO_WOUND_VISIT); its "
         "words decide clean/minor vs any other wound. Doses BEFORE the visit date from: Immunizations (not "
         "'Entered in error'), outside 'Immunization record:' documents in Documents (scans: look_at_page; mind the "
         "'Dates written' format and grid rows without years), and our notes of a tetanus vaccine given here with a "
         "lot. Same date = one dose. Answer ACTION:count:last-date as the rule says.",
         [("Doing chart review on wound visits. Sofía Hollis, DOB 1993-10-15, came in on 2025-10-14. What was due "
           "for tetanus?", "VACCINE_AND_TIG:2:2017-10-25", "notes (triage) + immunizations + outside record scan"),
          ("What should Douglas Walker have gotten for tetanus when they came in with a wound on 2025-09-23?",
           "VACCINE:3:2011-06-24", "notes + immunizations + files")]),
    Play("recall_count", R(r"\brecall(ed)?\b.{0,80}\blot\b|\blot\b.{0,80}\brecall|\blot (number )?[A-Z0-9]{5,}\b.{0,80}\bnotif"),
         [],
         "URL filters on /vaccines and /vaccines/notes are IGNORED: use search_form. 1) search_form('/vaccines', "
         "{'lot': '<LOT>'}) -> the lot's row -> its page /vaccines/lots/<id> (who got a dose). No lot with that "
         "number anywhere -> UNKNOWN_LOT. 2) search_form('/vaccines/notes', {'words': '<LOT>'}) -> notes that mention "
         "the lot: doses given here recorded only in a note, and notices mailed/sent/handed (or returned). Count "
         "record numbers once (merged duplicates once, test records never).",
         [("Could you count how many of our patients still haven't been told about the recall of vaccine lot "
           "36JR47H?", "UNKNOWN_LOT", "no lot with that number in any location's inventory"),
          ("How many patients are left to notify about the recall of lot 22UP75G?", "14",
           "lot search -> lot page (patients with a dose) + notes search for the lot (doses only in notes; notices "
           "mailed/sent/handed, letters returned) -> got a dose and not notified, each record number once")]),
    Play("invoice_owed", R(r"\binvoice\b.{0,100}\b(owe[ds]?|owing|balance|due|outstanding|unpaid|still|left|remaining)\b|"
           r"\b(owe[ds]?|owing|balance|outstanding|unpaid|remaining|still|collect)\b.{0,100}\binvoice\b"),
         ["/billing/accounts/{pid}"],
         "search_form('/billing', {'number': '<invoice>'}) finds the invoice directly (the URL filter is ignored); "
         "or the patient's account /billing/accounts/<patient id> -> the invoice row -> /billing/invoices/<id>. "
         "Owed = charges minus payments received (adjustments are not payments); a Void invoice owes 0. Balances "
         "change during the shift: read it now.",
         [("What's still owed on invoice 32208721 (patient Abigail Gardner, service date 2025-03-13), in dollars?",
           "48.36", "charge 109.63 - payment 61.27")]),
    Play("good_faith_estimate", R(r"good[- ]faith estimate|\bGFE\b"),
         ["/patients/{pid}/insurance", "/patients/{pid}/appointments", "/patients/{pid}/notes"],
         "Insurance tab: the chart's own primary insurance (payer/plan/member ID) or 'No insurance on file'; notes "
         "naming THIS appointment's date where the patient chose self-pay. The appointment's own page "
         "(/patients/<id>/appointments/<appt id>, from the Appointments tab row with that date and time) has the "
         "Booking date and History (latest 'start time moved'). Closures: the clinic calendar at "
         "/settings?year=YYYY&location=<location id> (Active entries for all locations or this one; code opens the "
         "appointment page and this calendar when it finds the row). Count business days after the scheduling date "
         "through the appointment date with python (Mon-Fri minus Active closures); a booking in another year needs "
         "that year's calendar too.",
         [("Good faith estimate question: Lee, Austin, born 2016-05-05, 08:20 on 2026-10-27. Is one required, and if "
           "so, when's it due?", "NOT_REQUIRED:INSURED", "insurance tab shows a primary plan, no self-pay note")],
         proven=False),
    Play("completed_visit_count", R(r"how many (completed|finished) (visits|appointments)\b"),
         ["/schedule/appointments?start={d0}&end={d0}&provider={prov}&status=2",
          "/schedule/appointments?start={d0}&end={d0}&location={loc}&status=2"],
         "The appointment list filtered to that day, provider or location, status Completed. Leave out patients "
         "flagged Test record or Deleted (their chart/search row shows it). Times are local to the location.",
         [("How many completed visits did Juan Martin, NP have on 2024-12-20? Count visits at any location. Leave "
           "out appointments of patients whose record is a test record or has been deleted.", "9",
           "list of that day, provider, Completed -> 9 rows, none test/deleted")]),
    Play("provider_appt_count", R(r"how many scheduled appointments\b|how many appointments\b.{0,60}\b(scheduled|booked)\b|"
           r"how many appointments (does|will|did) .{3,60}? have on"),
         ["/schedule/appointments?start={d0}&end={d0}&provider={prov}&status=1"],
         "The appointment list filtered to that day, provider, status Scheduled (every location). Leave out "
         "patients flagged Test record or Deleted.",
         [("How many scheduled appointments does Hannah West, MD have on 2026-11-10, at any location? Leave out "
           "appointments of patients whose record is a test record or has been deleted.", "8", "")]),
    Play("open_slots", R(r"how many (open|available|free|bookable) (appointment )?(slots|times|spots)"),
         ["/schedule/providers/{prov}?date={d0}"],
         "Provider day page: count the 'Open slot' rows in the section of the asked location.",
         [("How many open slots are there for Cheryl Taylor, MD at Eastside on 2026-12-29?", "18", "")]),
    Play("unique_patient_count", R(r"how many (distinct |unique |different |individual )?patients (had|have|were seen|came)"), [],
         "Needs every row of a month's list at a location (hundreds): only answer if the list is complete.",
         [], proven=False, skip_hard=True),
    Play("top_providers", R(r"which (\w+ )?providers? (had|saw|completed) the most|\btop \w+ providers\b"), [],
         "Needs a whole month of completed visits across all locations: only answer if the lists are complete.",
         [], proven=False, skip_hard=True),
    Play("referral", R(r"\breferr(al|ed|ing)\b"), ["/patients/{pid}/files"],
         "Documents tab: 'Referral letter from <practice>' received that day; the reason is in the letter text.",
         [("Referral letter received on 2025-03-18 for patient Joseph Tucker (born 1985-10-13): which practice made "
           "the referral?", "Tilden Grove Pediatrics", "document title")]),
    Play("phone", R(r"\b(tele)?phone\b"), [],
         "Use patient_contact (page-text digits are scrambled by a font).",
         [("What phone number do we have on file for patient Martha Nelson (born 2019-06-24)?", "(620) 314-7363", "")]),
    Play("new_established", R(r"\bnew\b.{0,40}\bestablished\b|\bestablished\b.{0,40}\bnew\b"), [],
         "Use new_or_established with the rule's parameters.", []),
]

# What Set 1's confirmed answers of each kind looked like (agent/known_set1.py): shown in the prompt so the answer
# form is familiar; the clinic's own message still gives the exact form.
FORMS = {
    "lab": ["RELEASE", "NURSE_REVIEW:1", "NURSE_REVIEW:2", "CALL_PROVIDER_NOW:Calcium,Creatinine,Potassium", "NOT_COVERED"],
    "tetanus": ["NO_WOUND_VISIT", "VACCINE:2:2023-05-02", "VACCINE:0:NONE", "VACCINE_AND_TIG:2:2017-10-25",
                "NONE:4:2023-06-01"],
    "claim_next_step": ["WRITE_OFF:190.00", "CONTACT_PATIENT", "APPEAL:2026-12-12", "RESUBMIT:PROCEDURE_CODE",
                        "RESUBMIT:RENDERING_PROVIDER_ID", "BILL_PATIENT:33.84", "BILL_OTHER:Gold 1000", "AWAIT_PAYER", "NO_ACTION"],
    "filing_deadline": ["2027-02-26", "EXPIRED:77", "AWAITING_PRIMARY", "NO_FILING_TERMS"],
    "invoice_owed": ["48.36", "0.00"],
    "good_faith_estimate": ["NOT_REQUIRED:INSURED"],
    "recall_count": ["4", "0", "UNKNOWN_LOT"],
    "referral": ["Tilden Grove Pediatrics", "Knee pain with suspected meniscal tear"],
    "phone": ["(620) 314-7363"],
    "open_slots": ["18"], "provider_appt_count": ["8"], "completed_visit_count": ["9"],
}
# First match wins: the specific kinds before the broad words ("claim", "phone", "referral").
ORDER = ["filing_deadline", "invoice_owed", "claim_next_step", "lab", "tetanus", "recall_count", "good_faith_estimate",
         "unique_patient_count", "top_providers", "completed_visit_count", "provider_appt_count", "open_slots",
         "new_established", "referral", "phone"]
# Searches whose URL filters the site ignores (the form lives in the nested frame): submitted in the page by code.
SEARCHES = {
    "invoice_owed": ([("/billing", {"number": "{n0}"})], r"/billing/invoices/[^/?#]+"),
    "recall_count": ([("/vaccines", {"lot": "{c0}"}), ("/vaccines/notes", {"words": "{c0}"})], r"/vaccines/lots/[^/?#]+"),
}
PLAYS.sort(key=lambda p: ORDER.index(p.name))
NO_PATIENT = {"recall_count", "unique_patient_count", "top_providers", "completed_visit_count", "provider_appt_count",
              "open_slots"}
for _p in PLAYS:
    _p.forms = FORMS.get(_p.name, [])
    _p.patient = _p.name not in NO_PATIENT
    _p.searches, _p.follow = SEARCHES.get(_p.name, ([], ""))


# v45: everything above was written from Set 1's first 110-126 confirmed answers. The table keeps growing (156 in
# v44), so the answer forms and the worked examples are also DERIVED from it: every confirmed answer adds its form
# (code, or the shape of a number/date) to its category, and a category with few hand-written examples gets
# confirmed ones (task + answer). A category with confirmed answers counts as answered (proven).
def _shape(a):
    a = str(a)
    m = re.match(r"([A-Z][A-Z_]+)(:.*)?$", a)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a):
        return "date"
    if re.fullmatch(r"-?\d+(\.\d+)?", a):
        return "number"
    return "text"


# Set 1 tasks per category (test/set1/set1_tasks.csv): with the confirmed answers below this gives how often each kind
# is answerable at all (the time policy's starting answer rate, main.Policy.yield_of).
SET1_TOTALS = {'lab': 45, 'phone': 20, 'invoice_owed': 22, 'provider_appt_count': 16, 'referral': 10, 'tetanus': 12, 'open_slots': 9, 'recall_count': 13, 'completed_visit_count': 3, 'top_providers': 1, 'unique_patient_count': 8, 'claim_next_step': 38, 'filing_deadline': 14, 'good_faith_estimate': 13}


def _derive():
    try:
        from . import known_set1
    except Exception:
        return
    by = {}
    for t, a in known_set1.ANSWERS.items():
        p = next((p for p in PLAYS if p.match.search(t)), None)
        if p:
            by.setdefault(p.name, []).append((t, a))
    for p in PLAYS:
        rows = by.get(p.name, [])
        if not rows:
            continue
        p.proven = p.proven or not p.skip_hard
        shapes = {_shape(f) for f in p.forms}
        for t, a in rows:      # one example of every answer form Set 1 confirmed
            if _shape(a) not in shapes and len(p.forms) < 12:
                p.forms.append(str(a))
                shapes.add(_shape(a))
        seen = {e[0] for e in p.examples}
        for t, a in rows:      # up to 3 worked examples per category, preferring answer forms not shown yet
            if len(p.examples) >= 3:
                break
            if t not in seen and (len(p.examples) < 2 or _shape(a) not in {_shape(e[1]) for e in p.examples}):
                p.examples.append((t, str(a), "confirmed answer (Set 1)"))
                seen.add(t)
        p.confirmed = len(rows)
    for p in PLAYS:
        n = SET1_TOTALS.get(p.name, 0)
        # share of Set 1's tasks of this kind that have a confirmed answer (many runs; shrunk towards 0.4)
        p.set1_rate = round(0.5 * (p.confirmed / n) + 0.2, 3) if n else None
        dist = collections.Counter(_shape(a) for t, a in by.get(p.name, []))
        p.set1_dist = ", ".join(f"{k} {v}" for k, v in dist.most_common(6))


_derive()


def category(text):
    for p in PLAYS:
        if p.match.search(text or ""):
            return p
    return None
