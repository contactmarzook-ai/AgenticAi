"""Admin-controlled platform settings, stored in the database and cached briefly per process."""

import threading
import time
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings as env
from ..database import SessionLocal
from ..models import PlatformSetting

KEY = "platform"
CACHE_SECONDS = 10

DEFAULTS = {
    # Steps nobody may use (keys from the node catalog).
    "disabled_nodes": [],
    # Hosts that HTTP steps and the http_get tool may call. "*" = any public host; "*.example.com" wildcards.
    "http_allowed_hosts": [],
    # Allow requests to private/internal IP ranges (intranet APIs). Off by default (SSRF protection).
    "allow_private_network": False,
    # Who may create saved connections: "builder" or "admin".
    "connections_min_role": "builder",
    # Let builders draft workflows from a plain-language description.
    "ai_builder_enabled": True,
    # Upper bound for the Wait step.
    "max_wait_seconds": 300,
}

_cache: dict = {"at": 0.0, "value": None}
_lock = threading.Lock()


def _merge(stored: Optional[dict]) -> dict:
    value = dict(DEFAULTS)
    value["http_allowed_hosts"] = list(env.http_tool_allowed_hosts)  # env provides the initial list
    if stored:
        value.update({k: v for k, v in stored.items() if k in DEFAULTS})
    return value


def get_settings(db: Optional[Session] = None, fresh: bool = False) -> dict:
    with _lock:
        if not fresh and _cache["value"] is not None and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            return dict(_cache["value"])
    own = db is None
    db = db or SessionLocal()
    try:
        row = db.get(PlatformSetting, KEY)
        value = _merge(row.value if row else None)
    finally:
        if own:
            db.close()
    with _lock:
        _cache.update(at=time.monotonic(), value=value)
    return dict(value)


def save_settings(db: Session, changes: dict) -> dict:
    row = db.get(PlatformSetting, KEY)
    current = _merge(row.value if row else None)
    current.update({k: v for k, v in changes.items() if k in DEFAULTS})
    if row is None:
        db.add(PlatformSetting(key=KEY, value=current))
    else:
        row.value = current
    db.commit()
    invalidate()
    return current


def invalidate() -> None:
    with _lock:
        _cache.update(at=0.0, value=None)
