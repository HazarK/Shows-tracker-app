"""Daily trigger for the season check. Detection itself lives in check_seasons."""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from tvtracker.config import Config
from tvtracker.db.repository import Repository
from tvtracker.jobs.check_seasons import Notifier, TvCatalog, check_all

logger = logging.getLogger(__name__)


def start_scheduler(
    config: Config,
    repo: Repository,
    tmdb: TvCatalog,
    notifier: Notifier,
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=config.check_timezone)

    def run() -> None:
        today = datetime.now(config.check_timezone).date()
        try:
            check_all(repo, tmdb, notifier, today)
        except Exception:
            logger.exception("season check failed")

    scheduler.add_job(
        run,
        trigger="cron",
        hour=config.check_hour,
        minute=0,
        id="check_seasons",
        replace_existing=True,
        coalesce=True,
        # Covers a late run while this process is still alive, such as after sleep.
        # Restarting the process does not replay a missed day.
        misfire_grace_time=6 * 60 * 60,
    )
    scheduler.start()
    return scheduler
