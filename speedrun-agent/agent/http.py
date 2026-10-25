"""Tiny JSON-over-HTTP helper on the standard library (no extra packages in the image).

v40: requests run in their own thread pools. asyncio.to_thread shares one small default pool (8 threads on 4 CPUs);
model calls that a task's deadline has already given up on keep their thread until their HTTP timeout, so a burst
of slow model calls could leave the QUEUE's own requests waiting for a free thread: the whole shift stood still.
The queue now has a pool of its own, and model calls a large one."""
import asyncio
import concurrent.futures
import json
import urllib.error
import urllib.request

_POOLS = {
    "queue": concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="queue"),
    "llm": concurrent.futures.ThreadPoolExecutor(max_workers=64, thread_name_prefix="llm"),
}


def _request(method, url, body=None, headers=None, timeout=130):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": {"code": "http_%d" % e.code, "message": raw[:300].decode("utf-8", "replace")}}
    except Exception as e:  # network error, timeout
        return 0, {"error": {"code": "network", "message": str(e)[:300]}}


async def request(method, url, body=None, headers=None, timeout=130, pool="llm"):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_POOLS.get(pool, _POOLS["llm"]), _request, method, url, body, headers, timeout)
