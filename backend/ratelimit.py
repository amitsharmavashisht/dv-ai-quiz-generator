"""Per-IP sliding window limiter.

In-memory, so it resets on restart and does not span multiple workers.
Fine for one container. Swap the dict for Redis when you scale out.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from config import get_settings

settings = get_settings()
_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    # Render / Railway / Nginx put the real address first in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check(ip: str) -> tuple[bool, int]:
    """Return (allowed, seconds_until_reset)."""
    now = time.time()
    window = settings.RATE_LIMIT_WINDOW_SEC

    with _lock:
        bucket = _hits[ip]
        while bucket and now - bucket[0] > window:
            bucket.popleft()

        if len(bucket) >= settings.RATE_LIMIT_COUNT:
            return False, int(window - (now - bucket[0])) + 1

        bucket.append(now)

        if len(_hits) > 5000:  # cheap garbage collection
            for key in [k for k, v in _hits.items() if not v]:
                del _hits[key]

    return True, 0
