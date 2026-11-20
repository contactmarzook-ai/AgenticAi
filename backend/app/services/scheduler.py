"""Cron triggers.

Run as its own process (`python -m app.scheduler`). Safe with more than one replica:
each due trigger is claimed with a conditional UPDATE on next_run_at, so only one
process starts a given firing.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Trigger, User, Workflow
from .runs import create_run, execute_run, fail_stale_runs

logger = logging.getLogger("agentos.scheduler")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    # SQLite returns naive datetimes; treat them as UTC.
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def valid_cron(expr: str) -> bool:
    return bool(expr) and croniter.is_valid(expr)


def next_fire_time(cron: str, tz_name: str, after: Optional[datetime] = None) -> datetime:
    tz = ZoneInfo(tz_name or "UTC")
    base = (after or utcnow()).astimezone(tz)
    return croniter(cron, base).get_next(datetime).astimezone(timezone.utc)


def active_version(db: Session, group_id: str) -> Optional[Workflow]:
    return db.query(Workflow).filter(Workflow.group_id == group_id, Workflow.status == "active").first()


def start_trigger_run(db: Session, trigger: Trigger, input_data: dict, source: str):
    """Create a run for the trigger's active workflow version, as the trigger owner. Returns the Run or None."""
    wf = active_version(db, trigger.workflow_group_id)
    if wf is None:
        logger.warning("Trigger %s skipped: workflow has no active version", trigger.id)
        return None
    owner = db.get(User, trigger.owner_id) if trigger.owner_id else None
    if owner is None or not owner.is_active:
        logger.warning("Trigger %s skipped: owner missing or deactivated", trigger.id)
        return None
    return create_run(db, target=wf, user=owner, source=source, input_data=input_data, trigger_id=trigger.id)


def tick(db: Session) -> int:
    """Fire all due schedule triggers once. Returns the number of runs started."""
    now = utcnow()
    due = (
        db.query(Trigger)
        .filter(
            Trigger.type == "schedule",
            Trigger.is_enabled.is_(True),
            Trigger.next_run_at.isnot(None),
            Trigger.next_run_at <= now,
        )
        .all()
    )
    started = 0
    for trig in due:
        old_next = trig.next_run_at
        new_next = next_fire_time(trig.cron, trig.timezone, after=now)
        claimed = db.execute(
            update(Trigger)
            .where(Trigger.id == trig.id, Trigger.next_run_at == old_next)
            .values(next_run_at=new_next, last_run_at=now)
        ).rowcount
        db.commit()
        if not claimed:
            continue  # another scheduler replica took it
        db.refresh(trig)
        run = start_trigger_run(db, trig, dict(trig.input or {}), "schedule")
        if run is not None:
            execute_run(run.id)
            started += 1
    return started


def main(poll_seconds: int = 20) -> None:
    from ..config import settings
    from ..logging_config import configure_logging

    configure_logging(settings.log_level, settings.log_json)
    logger.info("Scheduler started (poll every %ss)", poll_seconds)
    while True:
        db = SessionLocal()
        try:
            n = tick(db)
            if n:
                logger.info("Started %d scheduled run(s)", n)
            fail_stale_runs(db)
        except Exception:
            logger.exception("Scheduler tick failed")
            db.rollback()
        finally:
            db.close()
        time.sleep(poll_seconds)
