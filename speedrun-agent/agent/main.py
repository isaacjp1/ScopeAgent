"""ScopeAgent v41: works the queue until the shift ends.

v41: a task's kind is first its playbook CATEGORY (agent/playbook.py: Set 1's wordings, pages, procedures and worked
examples, applied to every set); the kinds Set 1 answered live start in replay mode, with their pages pre-opened.


What is different from v29 (the main loop and the time policy were rewritten):
- every task has ONE wall-clock cap, enforced around the whole solve (asyncio.wait_for). Nothing can hold the queue
  longer (v29 Set 3: tasks waited out account suspensions for minutes, synthesized solvers got >= 15 s each, and
  239 of 458 tasks were never reached);
- the time policy is per kind of task: explore a new kind (bounded share of the shift), replay a kind that has been
  answered (its pages pre-opened, short cap), write off a kind that never works (instant skip, with a retry now
  and then), and keep a reserve so every remaining task is reached;
- patients are found without a date of birth (agent/finder.py), and each answered task teaches its kind which pages
  to open (agent/kinds.py); rule messages' worked examples are learned in the background (agent/learn.py).
"""
import asyncio
import os
import time

from . import config, known_set1
from .brain import Brain
from .kinds import Kinds
from .learn import Learner
from .llm import LLM, BudgetExhausted, BACKGROUND
from .queue import Queue
from .rules import Rules
from .site import Site


def log(*a):
    print("[agent]", *a, flush=True)


class Policy:
    """How long a task may take, and whether the model loop may run."""

    def __init__(self, kinds=None):
        self.explore_spent = 0.0
        self.kinds = kinds      # key -> Kind (agent/kinds.py), for the answers-per-second gate
        self.last_why = ""
        self.spread_per = None  # v51: seconds kept back per remaining task once the set looks hard

    def hard_set(self):
        """The tries of this set mostly fail (Set 3: ~15% answered, Set 2: ~40%)."""
        ks = list((self.kinds or {}).values())
        tries = sum(k.tries for k in ks)
        return tries >= config.SPREAD_MIN_TRIES and sum(k.answers for k in ks) / tries < config.SPREAD_HARD_RATE

    def reserve_for(self, secs_left, tasks_left):
        """Seconds kept back for the tasks after this one. v51: on a tight set (Sets 2/3, ~4 s per task) 0.6 s each let
        the first ~170 of Set 3's 458 tasks take full 12-16 s tries and left the rest ~1.5 s (instant skips). Keeping
        ~3 s per remaining task back spreads the tries over the whole queue: a try happens whenever the slack above
        the reserve covers it, and every quick skip adds to the slack. Only on a set whose tries mostly fail: on a set
        like Set 2 front-loading costs little (simulated) and spreading would cut its answers a little."""
        n = max(0, tasks_left - 1)
        fair = secs_left / max(1, tasks_left)
        per = config.SKIP_COST
        if fair < config.TIGHT_FAIR and self.hard_set():
            # A FIXED number of seconds per remaining task, set once when the set turns out hard: all but SPREAD_SLACK
            # of each task's share then (at most SPREAD_RESERVE). Tries drain the slack above it and every quick skip
            # refills it, so tries spread over the whole queue. (A reserve recomputed from the current seconds per
            # task rescales with every decision and never holds anything back.)
            if self.spread_per is None:
                self.spread_per = max(per, min(config.SPREAD_RESERVE, fair - config.SPREAD_SLACK))
                print(f"[policy] hard set: keeping {self.spread_per:.1f}s per remaining task back", flush=True)
            per = max(per, self.spread_per)
        return n * per

    @staticmethod
    def yield_of(k):
        """(answers per second of trying, seconds per try) of a kind, smoothed towards a prior: a kind Set 1
        answered starts at 1 answer in 2 tries of 8 s."""
        p0 = 0.5 if (k.seeded or k.validated) else 0.25
        if k.play is not None and getattr(k.play, "set1_rate", None) is not None:
            p0 = k.play.set1_rate   # v47: how often Set 1's tasks of this kind got a confirmed answer
        n0, s0 = 2.0, config.YIELD_PRIOR_SECS
        rate = (k.answers + n0 * p0) / (k.tries + n0)
        secs = (k.secs + n0 * s0) / (k.tries + n0)
        return rate / max(1.0, secs), secs

    def gate(self, k, secs_left, tasks_left, reserve):
        """True if this kind earns enough answers per second for the time left. The kinds seen so far, in the
        proportions they come up, are ranked by answers per second; the time the remaining tasks of the best kinds
        would take is added up until it uses the time left: kinds below that line get only their deterministic paths
        (or an instant skip), so the seconds go where answers come fastest. In Sets 2/3 (about 4 s per task) not every
        task can be worked; v40 worked them in queue order and ran out of time on slow kinds."""
        if not self.kinds or not config.GATE:
            return True
        ks = [x for x in self.kinds.values() if x.seen]
        total = sum(x.seen for x in ks)
        if total < config.GATE_MIN_SEEN:
            return True
        if k.seen - k.last_try_seen >= 2 * config.RETRY_EVERY:
            return True     # a fresh look now and then: a kind's first tries can be unlucky
        budget = secs_left - reserve
        acc, line = 0.0, None
        for y, x in sorted(((self.yield_of(x)[0], x) for x in ks), key=lambda i: -i[0]):
            acc += x.seen / total * tasks_left * self.yield_of(x)[1]
            if acc > budget:
                line = y
                break
        return line is None or self.yield_of(k)[0] >= line

    def decide_set1(self, k, secs_left, tasks_left, fast_applies, budget_ok):
        """v50 Set 1 mode (the queue is matching the hardcoded table): every task the table does not answer gets a
        real try with its fair share of the time left (seconds per remaining UNKNOWN task: leftovers roll forward).
        No kind is switched off: v45-agent's Set 1 skipped labs, counts and estimates by the tight-set rules and ended
        with 8 of 15 minutes unused. Only kinds Set 1 never answered (a month of visits) get one try, then a skip."""
        self.last_why = ""
        reserve = max(0, tasks_left - 1) * config.SKIP_COST
        if not budget_ok:
            return self._fast_only(fast_applies, secs_left, reserve, want=5.0)
        if k.play is not None and k.play.skip_hard and k.answers == 0 and k.explores >= 1:
            self.last_why = "kind never answered on Set 1 (tried once this run)"
            return self._fast_only(fast_applies, secs_left, reserve, want=4.0)
        fair = (secs_left - reserve) / max(1, tasks_left) + config.SKIP_COST
        cap = min(config.SET1_MAX, max(config.SET1_MIN, config.SET1_STRETCH * fair), secs_left - reserve)
        if cap < 3:
            return self._fast_only(fast_applies, secs_left, reserve)
        return ("explore" if k.play is not None and k.play.skip_hard else "normal"), cap

    def decide(self, k, secs_left, tasks_left, fast_applies, budget_ok):
        self.last_why = ""
        fair = secs_left / max(1, tasks_left)
        reserve = self.reserve_for(secs_left, tasks_left)
        mode, cap = self._decide(k, secs_left, tasks_left, fast_applies, budget_ok)
        if mode in ("normal", "quick") and not self.gate(k, secs_left, tasks_left, reserve):
            y, secs = self.yield_of(k)
            self.last_why = f"below the answers-per-second line ({y:.3f}/s, {secs:.0f}s a try)"
            mode, cap = self._fast_only(fast_applies, secs_left, reserve, want=min(4.0, max(2.0, fair)))
        # v48 floor: the rules above switch kinds off one by one; on a hard set (Set 3) they all go dark after 10-15
        # minutes and every later task is skipped. The best kinds so far always keep getting full tries.
        if mode in ("fast-only", "skip") and budget_ok and self.is_top(k):
            c = min(config.FLOOR_CAP, secs_left - reserve)
            if c >= config.FLOOR_MIN_CAP:
                self.last_why = ""
                return "normal", c
        # v51: the spread reserve is for model tries; code paths (1-3 s, no model) still run when it is used up
        if mode == "skip" and fast_applies and self.spread_per is not None and budget_ok:
            c = min(3.0, secs_left - max(0, tasks_left - 1) * config.SKIP_COST)
            if c >= 1.5:
                return "fast-only", c
        # v48: when time is roomy (Set 1: 165 of 224 answered from the table, ~15 s per remaining task; v46 finished Set 1 4 min early) a try may
        # run longer than REPLAY_MAX: v46's Set 1 lost 19 tasks to model time-outs at 14 s
        if mode == "normal" and fair > config.REPLAY_MIN:
            cap = max(cap, min(config.ROOMY_MAX, 1.3 * fair, secs_left - reserve))
        return mode, cap

    def is_top(self, k):
        """k is one of the FLOOR_KINDS kinds with the best answers per second so far (a kind that has answered here,
        or one Set 1 answered that has not failed too often yet)."""
        if not self.kinds or config.FLOOR_KINDS <= 0:
            return False

        def alive(x):
            if x.play is not None and x.play.skip_hard and not x.answers:
                return False
            return x.answers > 0 or (x.seeded and x.tries < 2 * config.SEEDED_TRIES)
        ks = [x for x in self.kinds.values() if x.seen and alive(x)]
        top = sorted(ks, key=lambda x: -self.yield_of(x)[0])[:config.FLOOR_KINDS]
        return k in top

    def _decide(self, k, secs_left, tasks_left, fast_applies, budget_ok):
        fair = secs_left / max(1, tasks_left)
        reserve = self.reserve_for(secs_left, tasks_left)

        def can_spend(c):
            return secs_left - c >= reserve

        def explore_ok(c, extra=0.0):
            return self.explore_spent + c <= (config.EXPLORE_SHARE + extra) * config.SHIFT_SECONDS and can_spend(c)

        if not budget_ok:
            return self._fast_only(fast_applies, secs_left, reserve, want=min(5.0, max(2.0, fair * 1.5)))
        play = k.play
        if play and play.skip_hard and k.answers == 0:
            # Set 1 never answered these in time (a month of visits, hundreds of rows): one exploring try per set
            # in case this clinic's lists are short, then deterministic paths only
            if k.explores < 1 and fair >= 4.0 and explore_ok(config.EXPLORE_SECONDS):
                return "explore", config.EXPLORE_SECONDS
            return self._fast_only(fast_applies, secs_left, reserve, want=min(5.0, max(2.0, fair)))
        if k.seeded and not (k.answers or k.validated):
            # known from Set 1 but not yet answered here: written off only after a fair number of real tries
            written_off = k.tries >= config.SEEDED_TRIES and k.rate < 0.12
        else:
            written_off = (k.explores >= config.EXPLORE_TRIES and not k.proven) or \
                          (k.tries >= 6 and k.rate < 0.15)
        if k.proven and not written_off:
            avg = k.avg_answer_secs
            base = min(config.REPLAY_MAX, max(config.REPLAY_MIN, config.REPLAY_STRETCH * fair))
            # a kind that answers in A seconds gets about 1.5 A (it needs that much; more is wasted)
            cap = base if avg is None else min(config.REPLAY_MAX, max(config.REPLAY_MIN, 1.5 * avg + 1.0))
            if avg is not None and k.tries >= 4 and fair < 6:
                # time is tight: a kind that rarely answers and is slow is not worth its seconds
                if k.rate < 0.35 and avg > 2.5 * fair:
                    return self._fast_only(fast_applies, secs_left, reserve, want=min(5.0, max(2.0, fair)))
            if not can_spend(cap):
                cap = secs_left - reserve
                if cap < max(2.5, 0.5 * config.REPLAY_MIN):   # v51: a 3 s model try only burns its seconds
                    return self._fast_only(fast_applies, secs_left, reserve)
            return "normal", cap
        if not written_off and k.explores < config.EXPLORE_TRIES:
            cap = config.EXPLORE_SECONDS
            if explore_ok(cap):
                return "explore", cap
            if fair < config.QUICK_MIN_FAIR:
                # short tries of a kind never answered almost never answer (v40 Set 3): keep the seconds
                return self._fast_only(fast_applies, secs_left, reserve, want=min(5.0, max(2.0, fair)))
            cap = min(config.QUICK_MAX, max(config.QUICK_MIN, 1.2 * fair))
            return ("quick", cap) if can_spend(cap) else self._fast_only(fast_applies, secs_left, reserve)
        # written off: a retry every RETRY_EVERY tasks of the kind when time allows, else deterministic paths only
        if k.seen - k.last_try_seen >= config.RETRY_EVERY:
            if k.seeded:
                cap = min(config.REPLAY_MAX, max(config.REPLAY_MIN, config.REPLAY_STRETCH * fair))
                if can_spend(cap):
                    return "normal", cap
            elif explore_ok(config.EXPLORE_SECONDS, extra=0.08):
                return "explore", config.EXPLORE_SECONDS
        return self._fast_only(fast_applies, secs_left, reserve, want=min(5.0, max(2.0, 1.5 * fair)))

    @staticmethod
    def _fast_only(fast_applies, secs_left, reserve, want=4.0):
        cap = min(want, secs_left - reserve)
        if fast_applies and cap >= 1.5:
            return "fast-only", cap
        return "skip", 0


async def run():
    start = time.time()
    os.makedirs(config.WORK_DIR, exist_ok=True)
    site, llm, queue = Site(), LLM(), Queue()
    rules = Rules(llm)
    kinds = Kinds(rules)
    brain = Brain(site, llm, rules, kinds)
    learner = Learner(brain, kinds, llm)
    policy = Policy(kinds.kinds)

    site_task = asyncio.create_task(site.start())
    model_task = asyncio.create_task(llm.pick_model())

    async def warm():
        BACKGROUND.set(True)
        await site.ready.wait()
        try:
            provs = await site.providers()
            await brain.load_directory()
            log(f"provider directory: {len(provs)} providers")
        except Exception as e:
            log(f"warm-up failed: {e!r}")
    warm_task = asyncio.create_task(warm())

    stats = {"answered": 0, "skipped": 0, "messages": 0, "table": 0}
    tasks_seen = 0
    set1_mode = False
    state = await queue.current()
    # v45: the shift length comes from the queue, not only from SHIFT_SECONDS. If the env var is missing or stale
    # (900 on Set 3's 1800 s shift), the agent planned for 225 tasks and $8 on a 458-task set: generous caps on the
    # first half, then "no time" skips for the rest (v43 Set 3: 21 correct, 437 skipped).
    config.adopt_shift(state.get("seconds_left"))
    est_tasks = config.expected_tasks()
    log(f"shift {config.SHIFT_SECONDS:.0f}s: planning for ~{est_tasks} tasks, model budget ${config.BUDGET:.2f}; "
        f"queue state keys {sorted(state.keys())}")
    shift_end = time.time() + float(state.get("seconds_left", config.SHIFT_SECONDS)) - config.SAFETY_SECONDS
    while state.get("status") == "open":
        item = state["item"]
        text = item.get("text") or ""
        shift_end = min(shift_end, time.time() + float(state.get("seconds_left", 1e9)) - config.SAFETY_SECONDS)
        if item["kind"] == "message":
            rules.add(text)
            stats["messages"] += 1
            idx = len(rules.items) - 1
            log(f"{item['id']} message #{stats['messages']} acknowledged ({len(text)} chars)")
            log(f"   MESSAGE TEXT: {text!r}")
            state = await queue.close(item["id"], acknowledge=True)
            learner.on_message(idx, text)
            continue

        known = known_set1.lookup(text)
        if known is not None:
            set1_mode = True
            stats["answered"] += 1
            stats["table"] += 1
            state = await queue.close(item["id"], answer=known)
            log(f"{item['id']} ANSWER {known!r} in 0.0s src=table | task: {text!r}")
            continue

        try:
            await model_task
        except Exception as e:
            log(f"model choice failed: {e!r}")
        if not site.ready.is_set():
            try:
                await asyncio.wait_for(site.ready.wait(), max(1.0, shift_end - time.time() - 5))
            except asyncio.TimeoutError:
                pass
        try:
            tasks_seen += 1
            tasks_left = max(1, est_tasks - tasks_seen + 1)
            if set1_mode and known_set1.unknown_left(item["id"]) is not None:
                tasks_left = known_set1.unknown_left(item["id"]) + 1
            secs_left = shift_end - time.time()
            if secs_left <= 0.5:
                log("shift is over")
                break
            k = kinds.of(text)
            k.seen += 1
            fast_applies = brain.fast.matches(text)
            budget_ok = not llm.budget_gone and llm.spent < config.BUDGET * config.LOOP_BUDGET_SHARE
            decide = policy.decide_set1 if set1_mode and config.SET1_MODE else policy.decide
            mode, cap = decide(k, secs_left, tasks_left, fast_applies, budget_ok)

            # An account suspension: WAIT for it to lift. Skipping costs no time, so v25 skipped ~45 tasks in a row
            # during one; waiting costs the same seconds either way, and the tasks after it are still answerable.
            why_skip = policy.last_why or ("written off (kind never answered)" if mode == "skip" else "no time")
            if site.is_suspended() and mode != "skip":
                w0 = time.time()
                while site.is_suspended() and time.time() < shift_end - 5:
                    await asyncio.sleep(min(1.0, max(0.05, site.suspended_until - time.time())))
                log(f"{item['id']} waited {time.time() - w0:.0f}s for the account suspension to end")
                secs_left = shift_end - time.time()
                mode, cap = decide(k, secs_left, tasks_left, fast_applies, budget_ok)
            t0 = time.time()
            cap = max(0.0, min(cap, config.SET1_MAX if set1_mode else config.TASK_HARD_MAX, shift_end - t0))
            susp_before = site.suspensions
            if mode == "skip" or cap < 1.0:
                verdict, value, info = "skip", None, {"why": why_skip, "src": "-"}
                k.skipped_fast += 1
            else:
                deadline = t0 + cap
                try:
                    verdict, value, info = await asyncio.wait_for(
                        brain.solve(text, k, deadline, mode="fast-only" if mode == "fast-only" else "normal",
                                tight=secs_left / max(1, tasks_left) < config.TIGHT_FAIR), cap + 2.0)
                except asyncio.TimeoutError:
                    verdict, value, info = "skip", None, {"why": "hard timeout", "src": "-"}
                except BudgetExhausted:
                    verdict, value, info = "skip", None, {"why": "model budget gone", "src": "-"}
                except Exception as e:
                    verdict, value, info = "skip", None, {"why": f"error {e!r}"[:150], "src": "-"}
            dt_ = time.time() - t0
            if mode == "explore":
                policy.explore_spent += dt_
            if time.time() > shift_end + config.SAFETY_SECONDS:
                log("shift is over")
                break
            suspended_during = site.suspensions != susp_before
            if mode in ("normal", "explore", "quick") and not suspended_during:
                k.tries += 1
                k.secs += dt_
                k.last_try_seen = k.seen
                if mode == "explore":
                    k.explores += 1
            if verdict == "answer":
                if mode == "fast-only":
                    k.tries += 1
                k.answers += 1
                k.ans_secs.append(dt_)
                stats["answered"] += 1
                if info.get("src") in ("loop", "final"):
                    kinds.learn(k, text, value, info.get("route", []), info.get("slots"))
                state = await queue.close(item["id"], answer=value)
            else:
                stats["skipped"] += 1
                if k.play is None and info.get("src") == "loop" and info.get("route"):
                    # v51: a task no category fits: keep the pages the model chose as the kind's starting pages, so
                    # the next task worded this way does not explore from scratch (answered tasks already do this)
                    kinds.learn_pages(k, info.get("route", []), info.get("slots"))
                state = await queue.close(item["id"], skip=True)
            log(f"{item['id']} {verdict.upper()} {value!r} in {dt_:.1f}s src={info.get('src', '-')} mode={mode} "
                f"cap={cap:.0f} kind={k.key[:40]} ({k.answers}/{k.tries}) | {info.get('why', '')} "
                f"conf={info.get('conf', '')} pages={len(info.get('route', []))} | task: {text!r}")
            log(f"   left {state.get('seconds_left', 0):.0f}s tasks_left~{tasks_left - 1} spent ${llm.spent:.3f} "
                f"explore {policy.explore_spent:.0f}s {stats}")
        except Exception as e:   # never let one task end the run: skip it and go on
            log(f"{item['id']} ERROR {e!r}"[:300])
            try:
                state = await queue.close(item['id'], skip=True)
            except Exception:
                state = await queue.current()
    log(f"done: {state} {stats} spent=${llm.spent:.3f} calls={llm.calls} wall={time.time() - start:.0f}s")
    for k in sorted(kinds.kinds.values(), key=lambda x: -x.seen):
        log(f"   kind {k.key[:60]}: seen {k.seen}, tries {k.tries}, answered {k.answers}, explores {k.explores}, "
            f"instant skips {k.skipped_fast}, {k.secs:.0f}s, examples {len(k.examples)}")
    site_task.cancel()
    warm_task.cancel()
    for j in learner.jobs:
        j.cancel()
    await site.close()


async def _run():
    # a large default pool for asyncio.to_thread (PDF text, python tool); the default is 8 threads on 4 CPUs
    import concurrent.futures
    asyncio.get_running_loop().set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=32))
    await run()


def main():
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
