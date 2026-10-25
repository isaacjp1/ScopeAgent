"""All tunables in one place (v41). Every value can be overridden with an env var in the Dockerfile."""
import os


def _f(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def _list(name, default):
    return [m.strip() for m in os.environ.get(name, default).split(",") if m.strip()]


QUEUE_URL = os.environ.get("QUEUE_URL", "").rstrip("/")
SITE_URL = os.environ.get("SITE_URL", "https://practice.speedrun.scopehealth.com").rstrip("/")
SITE_USERNAME = os.environ.get("SITE_USERNAME", "agent")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "agent")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
SHIFT_SECONDS = _f("SHIFT_SECONDS", 900)
WORK_DIR = os.environ.get("WORK_DIR", "/tmp/work")

# ---------------------------------------------------------------- models
# MODEL wins if set; otherwise the first of MODEL_PREFS the endpoint lists. The loop model must call tools well.
MODEL = os.environ.get("MODEL", "")
MODEL_PREFS = _list("MODEL_PREFS", "anthropic/claude-sonnet-5.5,anthropic/claude-sonnet-5,google/gemini-3.8-flash,"
                                   "google/gemini-3.5-flash,google/gemini-2.5-flash,anthropic/claude-haiku-4.5")
# Fast model: vision reads (phone screenshots, scanned documents), the best-guess call, and the loop once
# STRONG_BUDGET_SHARE of the budget is spent (keeps the cheap paths alive to the end of the shift).
FALLBACK_PREFS = _list("FALLBACK_PREFS", "google/gemini-3.8-flash,google/gemini-3.7-flash,google/gemini-3.5-flash,"
                                         "google/gemini-2.5-flash,anthropic/claude-haiku-4.5")
STRONG_PREFS = _list("STRONG_PREFS", "anthropic/claude-sonnet-5.5,anthropic/claude-opus-5.5")
QUICK_PREFS = _list("QUICK_PREFS", "google/gemini-3.8-flash,google/gemini-3.7-flash,anthropic/claude-haiku-4.5")
STRONG_BUDGET_SHARE = _f("STRONG_BUDGET_SHARE", 0.7)
REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "low")

# ---------------------------------------------------------------- time policy (see main.Policy)
SAFETY_SECONDS = _f("SAFETY_SECONDS", 2.5)    # stop this close to the end of the shift
TASK_HARD_MAX = _f("TASK_HARD_MAX", 30)       # no task ever holds the queue longer than this (wall clock)
EXPLORE_SECONDS = _f("EXPLORE_SECONDS", 22)   # first tries of a kind never seen answered
EXPLORE_SHARE = _f("EXPLORE_SHARE", 0.22)     # at most this share of the shift goes to exploring tries
EXPLORE_TRIES = int(_f("EXPLORE_TRIES", 2))   # exploring tries per kind before it is written off
RETRY_EVERY = int(_f("RETRY_EVERY", 7))       # a written-off kind gets one more exploring try every N of its tasks
# v47: an answer takes ~10 s (v46 Set 1 live answers: 6.5-14.4 s; 19 skips were model time-outs under shorter
# caps). Fewer tries at full length, chosen by the answers-per-second gate:
REPLAY_MIN = _f("REPLAY_MIN", 12)              # a kind answered before gets clamp(REPLAY_STRETCH x fair, MIN, MAX)
REPLAY_MAX = _f("REPLAY_MAX", 16)
REPLAY_STRETCH = _f("REPLAY_STRETCH", 2.2)
QUICK_MIN = _f("QUICK_MIN", 3.5)              # an unproven kind when the explore budget is used: a short try
QUICK_MAX = _f("QUICK_MAX", 7)
QUICK_MIN_FAIR = _f("QUICK_MIN_FAIR", 99)    # below this many seconds per task left, no quick tries (deterministic only)
GATE = os.environ.get("GATE", "1") == "1"     # answers-per-second gate (main.Policy.gate); 0 = off
GATE_MIN_SEEN = int(_f("GATE_MIN_SEEN", 25))  # tasks seen before the gate decides anything
YIELD_PRIOR_SECS = _f("YIELD_PRIOR_SECS", 12)  # prior seconds per try of a kind (smoothing)
SEEDED_TRIES = int(_f("SEEDED_TRIES", 8))
SPREAD_RESERVE = _f("SPREAD_RESERVE", 3.0)   # v51: seconds kept per remaining task on a tight set (was 0.6)
SPREAD_HARD_RATE = _f("SPREAD_HARD_RATE", 0.3)  # ... when fewer than this share of tries answer
SPREAD_MIN_TRIES = int(_f("SPREAD_MIN_TRIES", 20))  # ... measured over at least this many tries
SPREAD_SLACK = _f("SPREAD_SLACK", 0.9)       # ... leaving this much of each task's share free for tries
SET1_MODE = os.environ.get("SET1_MODE", "1") == "1"   # v50: fair share of the time, no switch-offs, on Set 1
SET1_MIN = _f("SET1_MIN", 12)                 # a Set 1 try gets at least this ...
SET1_MAX = _f("SET1_MAX", 45)                 # ... and at most this
SET1_STRETCH = _f("SET1_STRETCH", 1.15)       # share of the per-task time a try may use (answers end early)
FLOOR_KINDS = int(_f("FLOOR_KINDS", 2))       # v48: the best kinds so far are never switched off
FLOOR_CAP = _f("FLOOR_CAP", 12)               # their cap when the other rules would have skipped them
FLOOR_MIN_CAP = _f("FLOOR_MIN_CAP", 6)
ROOMY_MAX = _f("ROOMY_MAX", 24)               # cap when seconds per remaining task exceed REPLAY_MAX (Set 1)
TIGHT_FAIR = _f("TIGHT_FAIR", 6)             # seconds per remaining task below which a set counts as tight
EARLY_EXIT = os.environ.get("EARLY_EXIT", "1") == "1"   # v48: drop a try at once when it is off track     # a playbook kind Set 1 answered is written off after this many tries
SKIP_COST = _f("SKIP_COST", 0.6)              # seconds a written-off task costs (to plan the time left)
MIN_CONFIDENCE = _f("MIN_CONFIDENCE", 0.6)    # answer only above this (wrong = -1)
FINAL_MIN_CONFIDENCE = _f("FINAL_MIN_CONFIDENCE", 0.7)
FINAL_MIN_READ = int(_f("FINAL_MIN_READ", 1200))
FINAL_RESERVE = _f("FINAL_RESERVE", 2.2)
MAX_TURNS = int(_f("MAX_TURNS", 9))
SUSPEND_WAIT_MAX = _f("SUSPEND_WAIT_MAX", 6)  # a task waits at most this long for a site suspension to end

# ---------------------------------------------------------------- site
PAGE_POOL = int(_f("PAGE_POOL", 6))
PAGE_CHARS = int(_f("PAGE_CHARS", 7000))      # page text per page sent to the model
NAV_TIMEOUT = _f("NAV_TIMEOUT", 10)
CACHE_SECONDS = _f("CACHE_SECONDS", 240)   # v48: charts, lists and lot pages come up again
LIST_ROWS_LIMIT = int(_f("LIST_ROWS_LIMIT", 150))   # generic reads do not page lists longer than this
LIST_MAX_PAGES = int(_f("LIST_MAX_PAGES", 4))
NAME_LIST_MAX_PAGES = int(_f("NAME_LIST_MAX_PAGES", 5))   # the patient finder may walk a sorted name list this far
SHOW_MORE_MAX = int(_f("SHOW_MORE_MAX", 5))               # "Show more" clicks on a documents list
SUSPEND_BACKOFF = _f("SUSPEND_BACKOFF", 30)
NAV_WINDOW = _f("NAV_WINDOW", 10)
NAV_PER_WINDOW = int(_f("NAV_PER_WINDOW", 20))
NAV_MIN = int(_f("NAV_MIN", 8))
NAV_RAMP_EVERY = int(_f("NAV_RAMP_EVERY", 10))
NAV_BG_SHARE = _f("NAV_BG_SHARE", 0.3)

# ---------------------------------------------------------------- background learning from rule examples
LEARN_EXAMPLES = os.environ.get("LEARN_EXAMPLES", "1") == "1"
LEARN_SECONDS = _f("LEARN_SECONDS", 60)
LEARN_BUDGET_SHARE = _f("LEARN_BUDGET_SHARE", 0.15)
LEARN_MIN_BUDGET = _f("LEARN_MIN_BUDGET", 5)   # off on the $1 practice set

_dbg = os.environ.get("DEBUG_PAGES", "auto")
DEBUG = (SHIFT_SECONDS == 1200) if _dbg == "auto" else _dbg == "1"

# Known sets: shift length -> number of tasks. Others: about 4 s per task.
KNOWN_SETS = {1200: 6, 900: 225, 1800: 458, 3600: 924}
BUDGETS = {1200: 1.0, 900: 8.0, 1800: 15.0, 3600: 25.0}
BUDGET = _f("BUDGET", BUDGETS.get(int(SHIFT_SECONDS), SHIFT_SECONDS / 3600 * 25))
LOOP_BUDGET_SHARE = _f("LOOP_BUDGET_SHARE", 0.95)


def expected_tasks():
    return KNOWN_SETS.get(int(SHIFT_SECONDS), max(1, int(SHIFT_SECONDS / 4)))


def adopt_shift(seconds_left):
    """Use the shift length the queue reports (rounded to a known set) when SHIFT_SECONDS disagrees with it."""
    global SHIFT_SECONDS, BUDGET
    try:
        left = float(seconds_left)
    except (TypeError, ValueError):
        return
    if left <= 0 or abs(left - SHIFT_SECONDS) <= 120:
        return
    known = min(KNOWN_SETS, key=lambda s: abs(s - left))
    if abs(known - left) > 0.15 * known:
        return      # not a known set's length (a test clock): keep SHIFT_SECONDS
    new = float(known)
    if "BUDGET" not in os.environ:
        BUDGET = BUDGETS.get(int(new), new / 3600 * 25)
    print(f"[config] SHIFT_SECONDS {SHIFT_SECONDS:.0f} -> {new:.0f} (queue says {left:.0f}s left)", flush=True)
    SHIFT_SECONDS = new
