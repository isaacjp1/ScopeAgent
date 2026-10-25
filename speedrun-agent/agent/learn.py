"""Learning a kind before its tasks arrive (v40).

Rule messages come with a worked example ("If someone asks: ... The answer is `X`"). In the background, the agent
works that example like a task. When it gets the rule's own answer, the route of pages it used becomes a checked
example of the kind: the queue's tasks of that kind then start with those pages open and that worked example in the
prompt. This costs a few cents and a few page loads per rule, off the queue's clock (v29 synthesized code from the
same exploration instead, which cost $3+ per set and produced no working solver on Set 1)."""
import asyncio
import re
import time

from . import config
from .llm import BACKGROUND

EXAMPLE_RE = re.compile(
    r"(?:If someone asks|Request|Question|For example, if asked|Example request)\s*:?\s*[\"“](.+?)[\"”]\s*\n.*?"
    r"(?:The answer is|Answer|The correct answer is)\s*:?\s*`([^`]+)`", re.S | re.I)


def parse_example(text):
    i = text.find("## Example")
    m = EXAMPLE_RE.search(text[i:] if i >= 0 else text)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def norm_answer(a):
    if a is None:
        return ""
    if isinstance(a, (list, tuple)):
        a = ",".join(str(x) for x in a)
    s = re.sub(r"\s+", "", str(a)).upper().rstrip(".")
    try:
        return repr(round(float(s.replace("$", "").replace(",", "")), 6))
    except ValueError:
        return s


class Learner:
    def __init__(self, brain, kinds, llm):
        self.brain, self.kinds, self.llm = brain, kinds, llm
        self.lock = asyncio.Lock()
        self.jobs = []
        self.results = {}
        self.spent = 0.0   # model dollars spent on examples (approximate: other calls run at the same time)

    def on_message(self, idx, text):
        if not config.LEARN_EXAMPLES or config.BUDGET < config.LEARN_MIN_BUDGET or len(text) < 600:
            return
        ex = parse_example(text)
        if not ex:
            return
        self.jobs.append(asyncio.create_task(self._job(idx, ex[0], ex[1])))

    async def _job(self, idx, request, expected):
        BACKGROUND.set(True)
        async with self.lock:   # one at a time: the queue's tasks come first
            if self.spent >= config.BUDGET * config.LEARN_BUDGET_SHARE or self.llm.budget_gone \
                    or self.llm.spent >= config.BUDGET * 0.8:
                print(f"[learn] rule{idx}: skipped (budget)", flush=True)
                return
            await self.brain.site.ready.wait()
            kind = self.kinds.of(request)
            t0 = time.time()
            spent0 = self.llm.spent
            try:
                res = await asyncio.wait_for(self.brain.solve(request, kind, time.time() + config.LEARN_SECONDS),
                                             config.LEARN_SECONDS + 10)
            except Exception as e:
                print(f"[learn] rule{idx}: failed {e!r}"[:200], flush=True)
                return
            self.spent += max(0.0, self.llm.spent - spent0)
            verdict, value, info = res
            ok = verdict == "answer" and norm_answer(value) == norm_answer(expected)
            self.results[kind.key] = ok
            print(f"[learn] rule{idx} kind={kind.key}: example answered {value!r} (expected {expected!r}) "
                  f"{'OK' if ok else 'MISS'} in {time.time() - t0:.0f}s src={info.get('src')} route={info.get('route', [])[:8]}",
                  flush=True)
            if ok:
                self.kinds.learn(kind, request, expected, info.get("route", []), info.get("slots"), validated=True)
