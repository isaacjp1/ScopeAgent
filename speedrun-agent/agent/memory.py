"""Workflow memory: how earlier tasks of the same kind were solved.

Each solved task stores the sequence of pages that led to the answer. A new task that looks like an
earlier one gets that route as a hint, so the model can jump straight to the right pages instead of
exploring again. This is what makes the agent get faster during the shift.
"""
import re

STOP = set("""a an the of for to in on at by with and or is was are be do does did what which who whom
how many much when where our we patient patients please""".split())


def signature(text):
    """Words that describe the kind of task, without names, numbers and dates."""
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*|\S", text)
    sig = set()
    for i, w in enumerate(words):
        if not w[0].isalpha():
            continue
        if w[0].isupper() and i > 0 and words[i - 1] not in (".", "?", ":", "!"):
            continue  # likely a name
        lw = w.lower()
        if lw in STOP or len(lw) < 3:
            continue
        sig.add(lw)
    return sig


class Memory:
    def __init__(self):
        self.items = []     # dicts: text, sig, route, answer
        self.outcomes = []  # (signature, answered) of model-loop tasks
        self.hopeless_seen = []  # signatures of tasks of hopeless kinds, to space out exploration tries

    def add(self, text, route, answer):
        self.items.append({"text": text, "sig": signature(text), "route": route[:12], "answer": answer})

    def similar(self, text, k=2, threshold=0.4):
        s = signature(text)
        if not s:
            return []
        scored = []
        for it in self.items:
            inter = len(s & it["sig"])
            union = len(s | it["sig"]) or 1
            j = inter / union
            if j >= threshold:
                scored.append((j, it))
        scored.sort(key=lambda x: -x[0])
        out, seen = [], set()
        for j, it in scored:
            key = tuple(it["route"])
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
            if len(out) >= k:
                break
        return out

    def hint(self, text):
        sims = self.similar(text)
        if not sims:
            return ""
        parts = ["Earlier tasks of the same kind and the pages that answered them (copy the route, with this task's names and dates):"]
        for it in sims:
            route = " -> ".join(it["route"]) or "(no pages)"
            parts.append(f"- Task: {it['text'][:300]}\n  Route: {route}\n  Answer sent: {it['answer']}")
        return "\n".join(parts)

    # ---- outcomes of model-loop tasks, to stop paying for kinds of task the agent never answers ----
    def outcome(self, text, answered):
        self.outcomes.append((signature(text), answered))

    def answered_like(self, text, threshold=0.6):
        """How many earlier model-loop tasks like this one were answered."""
        s = signature(text)
        return sum(1 for sig, a in self.outcomes if a and s and len(s & sig) / (len(s | sig) or 1) >= threshold)

    def hopeless(self, text, n, threshold=0.6):
        """True if at least n earlier loop tasks like this one were all skipped."""
        s = signature(text)
        like = [a for sig, a in self.outcomes if s and len(s & sig) / (len(s | sig) or 1) >= threshold]
        return len(like) >= n and not any(like)

    def explore_turn(self, text, every, threshold=0.6):
        """Called for each task of a hopeless kind: True on every `every`-th one, which gets a longer try."""
        s = signature(text)
        n = sum(1 for sig in self.hopeless_seen if s and len(s & sig) / (len(s | sig) or 1) >= threshold)
        self.hopeless_seen.append(s)
        return every > 0 and n % every == every - 1
