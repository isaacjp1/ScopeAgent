"""Kinds of task and what the agent has learned about each (v41).

A kind is, first, a CATEGORY from the playbook ("c:lab", "c:invoice_owed": the wordings Set 1 used for each kind of
request, agent/playbook.py); for a task no category fits, the rule message it belongs to ("rule3": rare-word overlap
with the long messages) or a cluster of tasks with the same wording ("w:phone number file ..."). v40 grouped by rule
words only, put invoice and count tasks under the lab and tetanus rules, wrote those kinds off and skipped them all
(Set 3). A category kind starts with Set 1's pages, procedure and worked examples. Per kind the agent keeps:

- its outcomes (tries, answers, time) -> the time policy (explore a new kind, replay a known one, write off one
  that never works);
- worked examples: the task, the answer, and the route of pages that answered it. The route is turned into
  TEMPLATES ("/patients/{pid}/insurance", "/schedule/appointments?start={d0}&end={d0}&provider={prov}") that are
  filled with the next task's own patient, dates and provider and opened BEFORE the first model call. With the
  pages that answered the last task already in front of it, the model usually answers in one turn: the agent gets
  faster at a kind as the shift goes on ("plan caching" / workflow memory).
"""
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

from . import playbook
from .clinic import norm, parse_any_date

STOP = set("""a an the of for to in on at by with and or is was are be do does did what which who whom how many much
when where our we you your patient patients please could would can i i'm it its this that these those there their
they them have has had get got as if so any all from than then into out up""".split())
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\b[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}")


def wording(text):
    """Content words of a task without names, numbers and dates: what kind of request it is."""
    t = DATE_RE.sub(" ", text)
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", t)
    out = set()
    for i, w in enumerate(words):
        if w[0].isupper() and i > 0:
            continue    # names, places, panel names: vary from task to task
        lw = w.lower()
        if lw in STOP or len(lw) < 3:
            continue
        out.add(lw)
    return out


def task_dates(text):
    out = []
    for s in DATE_RE.findall(text):
        d = parse_any_date(s)
        if d and d.isoformat() not in out:
            out.append(d.isoformat())
    return out


class Kind:
    def __init__(self, key, sig=None, play=None):
        self.key = key
        self.sig = sig or set()
        self.tried_pages = []    # v51: templates from unanswered tries of a kind no category fits
        self.play = play        # playbook.Play of a category kind (Set 1's pages, procedure, examples), else None
        self.tries = 0          # tasks that reached the model loop or a solver
        self.answers = 0
        self.explores = 0       # long tries spent on this kind
        self.seen = 0           # tasks of this kind seen (including instant skips)
        self.skipped_fast = 0
        self.secs = 0.0
        self.ans_secs = []      # seconds of the tries that answered
        self.examples = []      # dicts: task, answer, route, templates, validated
        self.last_try_seen = 0
        self.validated = False  # the rule's worked example was answered right in the background (agent/learn.py)

    @property
    def seeded(self):
        """Set 1 answered this kind live: it is worth a replay try from its first task."""
        return bool(self.play and self.play.proven)

    @property
    def proven(self):
        return self.answers > 0 or self.validated or self.seeded

    @property
    def avg_answer_secs(self):
        xs = self.ans_secs[-8:]
        return sum(xs) / len(xs) if xs else None

    @property
    def rate(self):
        return self.answers / self.tries if self.tries else 0.0

    def templates(self):
        """Pages to open before the first model call: the playbook's (Set 1), then those that answered this
        clinic's earlier tasks of the kind."""
        out = list(self.play.pages) if self.play else []
        for ex in reversed(self.examples[-4:]):
            for t in ex["templates"]:
                if t not in out:
                    out.append(t)
        for t in self.tried_pages:      # v51: pages opened by tries that did not answer (kinds with no category)
            if t not in out:
                out.append(t)
        return out[:6]


class Kinds:
    def __init__(self, rules):
        self.rules = rules
        self.kinds = {}

    def of(self, text):
        p = playbook.category(text)
        if p:
            key = "c:" + p.name
            k = self.kinds.get(key)
            if not k:
                k = self.kinds[key] = Kind(key, play=p)
            return k
        key = self.rules.kind_of(text)
        if key:
            k = self.kinds.get(key)
            if not k:
                k = self.kinds[key] = Kind(key)
            return k
        sig = wording(text)
        best, score = None, 0.0
        for k in self.kinds.values():
            if not k.key.startswith("w:") or not k.sig:
                continue
            j = len(sig & k.sig) / (len(sig | k.sig) or 1)
            if j > score:
                best, score = k, j
        if best and score >= 0.5:
            return best
        key = "w:" + " ".join(sorted(sig))[:60]
        k = self.kinds.get(key) or Kind(key, sig)
        self.kinds[key] = k
        return k

    def get(self, key):
        k = self.kinds.get(key)
        if not k:
            k = self.kinds[key] = Kind(key)
        return k

    # ------------------------------------------------------------ learning from a solved task
    def learn(self, kind, task, answer, route, slots=None, validated=False):
        tmpl = templates_of(route, slots or {})
        kind.examples.append({"task": task, "answer": answer, "route": [r for r in route if r][:14],
                              "templates": tmpl, "validated": validated, "t": time.time()})
        kind.examples = kind.examples[-6:]
        if validated:
            kind.validated = True
        if tmpl:
            print(f"[kinds] {kind.key}: templates {tmpl}", flush=True)

    def learn_pages(self, kind, route, slots=None):
        """Templates from a try that did not answer: only pages opened at least twice across such tries are kept."""
        tmpl = templates_of(route, slots or {})
        kind.page_votes = getattr(kind, "page_votes", {})
        for t in tmpl:
            kind.page_votes[t] = kind.page_votes.get(t, 0) + 1
            if kind.page_votes[t] >= 2 and t not in kind.tried_pages:
                kind.tried_pages.append(t)
                print(f"[kinds] {kind.key}: start page {t} (opened by {kind.page_votes[t]} tries)", flush=True)
        kind.tried_pages = kind.tried_pages[-4:]

    def hint(self, kind, task):
        """Text for the first prompt: how this kind is worked (playbook, from Set 1) and how this clinic's earlier
        tasks of the kind were answered."""
        parts = []
        exs = [e for e in kind.examples if e["task"] != task][-2:]
        p = kind.play
        if p and p.hint:
            parts.append("HOW THIS KIND OF REQUEST IS WORKED (learned on the same product at another clinic; THIS "
                         "clinic's messages decide the rule, its numbers and the exact answer form):\n" + p.hint)
            if p.forms:
                parts.append("Answers of this kind there looked like: " + " | ".join(p.forms))
            if p.set1_dist:
                parts.append(f"Confirmed answers of this kind there, by form: {p.set1_dist} (a different clinic: "
                             f"decide from THIS task's records, never from these counts)")
            for t, a, how in p.examples[:1 if exs else 2]:
                parts.append(f"- Worked example (other clinic): {t}\n  How: {how or '-'}\n  Answer: {a}")
        if exs:
            parts.append("HOW EARLIER TASKS OF THIS KIND WERE ANSWERED HERE (same steps work for this task; use this "
                         "task's own patient, dates and names):")
            for e in exs:
                tag = " (checked: the rule's worked example)" if e.get("validated") else ""
                route = " -> ".join(e["route"][:10]) or "(no pages)"
                parts.append(f"- Task: {e['task'][:260]}\n  Pages: {route}\n  Answer sent{tag}: {e['answer']}")
        return "\n".join(parts)


ID_SEG = re.compile(r"^[A-Za-z0-9]{6,14}$")


def slots_of(task, names=(), ids=None):
    """The values of a task that a route can depend on, by type and order: d0.. dates (ISO), n0.. long numbers
    (invoice, claim numbers), c0.. codes with letters and digits (lot numbers), last/first (the patient's name),
    plus resolved ids (pid = patient chart, prov = provider, loc = location)."""
    s = {}
    for i, d in enumerate(task_dates(task)):
        s[f"d{i}"] = d
    plain = DATE_RE.sub(" ", task)
    for i, n in enumerate(dict.fromkeys(re.findall(r"\b\d{5,}\b", plain))):
        s[f"n{i}"] = n
    for i, c in enumerate(dict.fromkeys(t for t in re.findall(r"\b[A-Z0-9]{5,12}\b", plain)
                                        if re.search(r"\d", t) and re.search(r"[A-Z]", t))):
        s[f"c{i}"] = c
    if names:
        s["last"], s["first"] = names[0][0], names[0][1]
    for k, v in (ids or {}).items():
        if v:
            s[k] = v
    return s


def _sub(value, rev):
    if value in rev:
        return "{" + rev[value] + "}"
    return None


def templates_of(route, slots):
    """Route paths -> templates with {slot} placeholders. Paths that still hold an id the next task cannot know
    (a claim, a document opened from a list) are left out: the model follows those links itself."""
    out = []
    rev = {}
    for k, v in slots.items():
        rev.setdefault(str(v), k)
    for p in route:
        if not isinstance(p, str) or not p.startswith("/"):
            continue
        sp = urlsplit(p)
        segs = sp.path.split("/")
        ok = True
        for i, seg in enumerate(segs):
            r = _sub(seg, rev)
            if r:
                segs[i] = r
            elif ID_SEG.match(seg) and re.search(r"\d", seg):
                ok = False
        if not ok:
            continue
        q = []
        for k, v in parse_qsl(sp.query, keep_blank_values=True):
            r = _sub(v, rev)
            if r:
                v = r
            elif ID_SEG.match(v) and re.search(r"\d", v) and not re.fullmatch(r"\d{1,3}", v):
                ok = False
            q.append((k, v))
        if not ok:
            continue
        path = "/".join(segs) + ("?" + "&".join(f"{k}={v}" for k, v in q) if q else "")
        if path not in out and "{" in path:
            out.append(path)
    return out[:8]


def fill(template, slots):
    """A template filled with this task's values, or None if one is unknown."""
    out = template
    for k in re.findall(r"\{(\w+)\}", template):
        v = slots.get(k)
        if not v:
            return None
        out = out.replace("{" + k + "}", str(v))
    return out
