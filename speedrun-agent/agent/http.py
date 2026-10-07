"""Tiny JSON-over-HTTP helper on the standard library (no extra packages in the image)."""
import asyncio
import json
import urllib.error
import urllib.request


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


async def request(method, url, body=None, headers=None, timeout=130):
    return await asyncio.to_thread(_request, method, url, body, headers, timeout)
