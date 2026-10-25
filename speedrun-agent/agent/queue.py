"""Queue API client: GET /item and POST /item/close, with the 409 rules from the Agent interface doc."""
import asyncio

from . import config
from .http import request


class Queue:
    def __init__(self, base=None):
        self.base = (base or config.QUEUE_URL).rstrip("/")

    async def current(self):
        for attempt in range(5):
            status, data = await request("GET", f"{self.base}/item", timeout=20, pool="queue")
            if status == 200:
                return data
            await asyncio.sleep(0.3 * (attempt + 1))
        return {"status": "error", "detail": data}

    async def close(self, item_id, **field):
        """field is exactly one of answer=..., skip=True, acknowledge=True. Returns the next state."""
        body = {"id": item_id, **field}
        for attempt in range(4):
            status, data = await request("POST", f"{self.base}/item/close", body, timeout=20, pool="queue")
            if status == 200:
                return data
            if isinstance(data, dict) and "state" in data:  # 409 not_current / ended carry the state
                return data["state"]
            code = (data or {}).get("error", {}).get("code") if isinstance(data, dict) else None
            if status == 400 and "answer" in field:
                # Malformed answer: never lose the item, skip it instead.
                body = {"id": item_id, "skip": True}
                continue
            if status in (0, 500, 502, 504) or code == "network":
                await asyncio.sleep(0.3 * (attempt + 1))
                continue
            break
        return await self.current()
