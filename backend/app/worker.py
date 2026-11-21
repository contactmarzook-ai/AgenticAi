"""Dedicated run worker: `python -m app.worker`.

Optional. API pods already execute runs; run this (with RUN_WORKER_ENABLED=false on the API) to
move execution into its own deployment. It polls the database for queued runs and resumes runs
whose worker stopped.
"""

import logging
import time

from .config import settings
from .logging_config import configure_logging
from .services.runs import worker


def main() -> None:
    configure_logging(settings.log_level, settings.log_json)
    logging.getLogger("agentos.worker").info(
        "Run worker started (%s threads, poll every %ss)", settings.run_worker_threads, settings.run_poll_seconds
    )
    while True:
        worker.poll_once()
        time.sleep(max(1, settings.run_poll_seconds))


if __name__ == "__main__":
    main()
