"""Long-polling Telegram bot with an in-process daily season check."""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from telegram.ext import Application

from tvtracker.bot.handlers import register_handlers
from tvtracker.bot.notifier import TelegramNotifier
from tvtracker.config import ConfigError, load_config
from tvtracker.db.repository import Repository
from tvtracker.jobs.schedule import start_scheduler
from tvtracker.runtime import configure_logging, ensure_event_loop
from tvtracker.tmdb.client import TmdbClient

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    load_dotenv()
    try:
        config = load_config()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    repo = Repository(config.database_path)
    tmdb = TmdbClient(config.tmdb_api_key)
    notifier = TelegramNotifier(config.telegram_bot_token)
    scheduler = start_scheduler(config, repo, tmdb, notifier)
    application = Application.builder().token(config.telegram_bot_token).build()
    register_handlers(application, repo=repo, tmdb=tmdb, config=config)
    logger.info(
        "bot started; season check daily at %02d:00 %s",
        config.check_hour,
        getattr(config.check_timezone, "key", config.check_timezone),
    )
    ensure_event_loop()
    try:
        application.run_polling()
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
