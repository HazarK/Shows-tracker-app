"""Compare stored seasons with TMDB and notify each new season once."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from dotenv import load_dotenv

from tvtracker.bot.messages import new_season_message
from tvtracker.bot.notifier import TelegramNotifier
from tvtracker.config import ConfigError, load_config
from tvtracker.db.repository import Repository
from tvtracker.domain.seasons import newly_released
from tvtracker.runtime import configure_logging
from tvtracker.tmdb.client import ShowDetails, TmdbClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckResult:
    checked: int
    notified: int
    failed: int


class TvCatalog(Protocol):
    def get_tv(self, tmdb_id: int) -> ShowDetails: ...


class Notifier(Protocol):
    def send(self, chat_id: int, text: str) -> None: ...


def check_all(
    repo: Repository,
    tmdb: TvCatalog,
    notifier: Notifier,
    today: date,
) -> CheckResult:
    shows = repo.list_all_tracked_shows()
    if not shows:
        logger.info("season check skipped: no tracked shows")
        return CheckResult(checked=0, notified=0, failed=0)

    checked = 0
    notified = 0
    failed = 0
    for show in shows:
        checked += 1
        try:
            details = tmdb.get_tv(show.tmdb_id)
        except Exception:
            failed += 1
            logger.exception("tmdb lookup failed tmdb_id=%s", show.tmdb_id)
            continue

        seen = repo.seen_season_numbers(show.id)
        for season in newly_released(details.seasons, today):
            if season.season_number in seen or season.air_date is None:
                continue
            try:
                notifier.send(
                    show.telegram_chat_id,
                    new_season_message(show.title, season.season_number),
                )
            except Exception:
                failed += 1
                logger.exception(
                    "telegram notify failed tmdb_id=%s season=%s",
                    show.tmdb_id,
                    season.season_number,
                )
                continue
            try:
                inserted = repo.record_notified_season(
                    show.id,
                    season.season_number,
                    season.air_date,
                )
            except Exception:
                failed += 1
                logger.exception(
                    "failed to record notification tmdb_id=%s season=%s",
                    show.tmdb_id,
                    season.season_number,
                )
                continue
            seen.add(season.season_number)
            if inserted:
                notified += 1

    logger.info(
        "season check finished checked=%s notified=%s failed=%s",
        checked,
        notified,
        failed,
    )
    return CheckResult(checked=checked, notified=notified, failed=failed)


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
    today = datetime.now(config.check_timezone).date()
    check_all(repo, tmdb, notifier, today)


if __name__ == "__main__":
    main()
