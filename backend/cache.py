"""Quiz cache keyed on the source text and the generation settings.

The same previous year paper gets uploaded hundreds of times. Serving those
from memory turns the second and every later request into a free, instant
response. In-process only, so it resets on restart and does not span workers;
swap the dict for Redis when you run more than one container.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict

from config import get_settings

settings = get_settings()

_store: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()
_lock = threading.Lock()
_stats = {"hits": 0, "misses": 0}


def key_for(source: str, **params) -> str:
    payload = json.dumps(params, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256()
    digest.update(source.encode("utf-8", "ignore"))
    digest.update(b"\x00")
    digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def get(key: str) -> dict | None:
    if not settings.CACHE_ENABLED:
        return None
    now = time.time()
    with _lock:
        entry = _store.get(key)
        if entry is None:
            _stats["misses"] += 1
            return None
        stored_at, value = entry
        if now - stored_at > settings.CACHE_TTL_SEC:
            del _store[key]
            _stats["misses"] += 1
            return None
        _store.move_to_end(key)
        _stats["hits"] += 1
        return value


def put(key: str, value: dict) -> None:
    if not settings.CACHE_ENABLED:
        return
    with _lock:
        _store[key] = (time.time(), value)
        _store.move_to_end(key)
        while len(_store) > settings.CACHE_MAX_ENTRIES:
            _store.popitem(last=False)


def stats() -> dict:
    with _lock:
        total = _stats["hits"] + _stats["misses"]
        return {
            "enabled": settings.CACHE_ENABLED,
            "entries": len(_store),
            "hits": _stats["hits"],
            "misses": _stats["misses"],
            "hit_rate": round(_stats["hits"] / total, 3) if total else 0.0,
        }


def clear() -> None:
    with _lock:
        _store.clear()
        _stats["hits"] = 0
        _stats["misses"] = 0
