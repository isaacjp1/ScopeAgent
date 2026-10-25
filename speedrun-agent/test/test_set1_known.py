"""Replays the real Set 1 queue (224 tasks + 16 messages, from test/set1/) against the mock clinic and a model that
always skips. Checks (v40) that every verified Set 1 answer goes out exactly, at once, and that the rest still run.

    python test/test_set1_known.py
    MOCK_SUSPEND=25,25 python test/test_set1_known.py   # the clinic suspends the account after every 25 page loads
                                                        # for 25 s: no task may overrun its cap by more than 3 s, and
                                                        # each suspension sets the back-off at most once (v29)
"""
import asyncio
import csv
import glob
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ.update({"QUEUE_URL": "http://127.0.0.1:8832", "SITE_URL": "http://127.0.0.1:8831",
                   "LLM_BASE_URL": "http://127.0.0.1:8833/v1", "LLM_API_KEY": "x", "SHIFT_SECONDS": "900",
                   "MODEL": "fake", "WORK_DIR": "/tmp/wd_s1", "DEBUG_PAGES": "0", "RECON": "0",
                   "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")})
import mock_wrenfield as mw  # noqa: E402


class Model(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._json({"data": [{"id": "fake"}]})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._json({"choices": [{"message": {"role": "assistant", "content": "{}", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "skip_task", "arguments": "{\"reason\": \"test\"}"}}]},
            "finish_reason": "tool_calls"}], "usage": {"cost": 0.0}})


tasks = list(csv.DictReader(open(os.path.join(HERE, "set1", "set1_tasks.csv"), encoding="utf-8")))
items = [{"id": r["id"], "kind": "task", "text": r["task"]} for r in tasks]
for f in glob.glob(os.path.join(HERE, "set1", "set1_rules", "*.md")):
    iid = os.path.basename(f).split("_")[0]
    items.append({"id": iid, "kind": "message", "text": open(f, encoding="utf-8").read()})
items.sort(key=lambda x: int(x["id"][1:]))
mw.ITEMS[:] = items
for p in (8831, 8832, 8833):
    s = ThreadingHTTPServer(("127.0.0.1", p), {8831: mw.Site, 8832: mw.Q, 8833: Model}[p])
    threading.Thread(target=s.serve_forever, daemon=True).start()
time.sleep(0.5)

from agent import config, known_set1, main  # noqa: E402
# the mock has none of Set 1's records: keep the unknown tasks short (v40 knobs)
config.EXPLORE_SECONDS = 3.0
config.REPLAY_MIN, config.REPLAY_MAX = 2.0, 3.0
config.QUICK_MIN, config.QUICK_MAX = 1.5, 2.0
config.LEARN_EXAMPLES = False
over, backoffs = [], []
_solve = main.Brain.solve


async def timed_solve(self, task_text, kind, deadline, *a, **kw):
    res = await _solve(self, task_text, kind, deadline, *a, **kw)
    if time.time() > deadline + 3:
        over.append((round(time.time() - deadline, 1), task_text[:60]))
    return res
main.Brain.solve = timed_solve
_susp = main.Site.suspended


def counted(self, path):
    before = self.suspended_until
    _susp(self, path)
    if self.suspended_until != before:
        backoffs.append(path)
main.Site.suspended = counted
t0 = time.time()
asyncio.run(main.run())
log = {x["id"]: x for x in mw.QSTATE["log"]}
sent = {i: x["answer"] for i, x in log.items() if "answer" in x}
want = dict(known_set1._TABLE)   # v58: ANSWERS + EXTRA
ok = sum(1 for it in items if it["kind"] == "task" and known_set1._key(it["text"]) in want and want[known_set1._key(it["text"])] == sent.get(it["id"]))
print(f"{len(log)} items closed, {len(sent)} answered, {ok} known answers sent exactly, {time.time() - t0:.0f}s")
assert ok == len(known_set1._TABLE) == 200, ok
assert len(log) == len(items), (len(log), len(items))
assert not over, over
if mw.SUSP["n"]:
    print(f"suspension mode: {mw.SUSP['events']} suspension events, back-off set {len(backoffs)} times")
    assert mw.SUSP["events"] >= 1, "the mock never suspended: lower N"
    assert 1 <= len(backoffs) <= mw.SUSP["events"], (len(backoffs), mw.SUSP["events"])
print("all Set 1 known-answer checks passed")
