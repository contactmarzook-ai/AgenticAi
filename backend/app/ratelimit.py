"""Small in-process sliding-window rate limiter for unauthenticated endpoints.

Per process (and so per pod): with N API replicas the effective limit is up to N times higher.
That is enough to stop brute force and scripted abuse from one address without extra
infrastructure; the ingress can add a global limit if needed.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .audit import client_ip

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_MAX_KEYS = 50_000


def check(request: Request, bucket: str, per_minute: int) -> None:
    if per_minute <= 0:
        return
    key = (bucket, client_ip(request) or "unknown")
    now = time.monotonic()
    with _lock:
        if len(_hits) > _MAX_KEYS:  # bound memory under address-spraying
            _hits.clear()
        q = _hits[key]
        while q and q[0] <= now - 60:
            q.popleft()
        if len(q) >= per_minute:
            raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
        q.append(now)


def reset() -> None:
    with _lock:
        _hits.clear()
