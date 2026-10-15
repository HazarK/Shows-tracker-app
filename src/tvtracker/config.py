"""Environment configuration for the bot and the daily season check."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import tzinfo
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(Exception):
    """Raised when required settings are missing or invalid."""


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    tmdb_api_key: str
    database_path: Path
    check_timezone: tzinfo
    check_hour: int
    allowed_chat_ids: frozenset[int] | None


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    env = os.environ if environ is None else environ
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    api_key = env.get("TMDB_API_KEY", "").strip()
    if not token:
        raise ConfigError("TELEGRAM_BOT_TOKEN is required")
    if not api_key:
        raise ConfigError("TMDB_API_KEY is required")

    database_raw = env.get("DATABASE_PATH", "data/tvtracker.sqlite").strip()
    database_path = Path(database_raw or "data/tvtracker.sqlite")

    timezone_name = env.get("CHECK_TIMEZONE", "UTC").strip() or "UTC"
    try:
        check_timezone: tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError(f"Unknown CHECK_TIMEZONE: {timezone_name}") from exc

    hour_raw = env.get("CHECK_HOUR", "9").strip() or "9"
    try:
        check_hour = int(hour_raw)
    except ValueError as exc:
        raise ConfigError("CHECK_HOUR must be an integer from 0 to 23") from exc
    if check_hour < 0 or check_hour > 23:
        raise ConfigError("CHECK_HOUR must be an integer from 0 to 23")

    return Config(
        telegram_bot_token=token,
        tmdb_api_key=api_key,
        database_path=database_path,
        check_timezone=check_timezone,
        check_hour=check_hour,
        allowed_chat_ids=_parse_allowed_chat_ids(env.get("TELEGRAM_ALLOWED_CHAT_IDS")),
    )


def _parse_allowed_chat_ids(raw: str | None) -> frozenset[int] | None:
    if raw is None or raw.strip() == "":
        return None
    chat_ids: list[int] = []
    for part in raw.split(","):
        piece = part.strip()
        if not piece:
            continue
        try:
            chat_ids.append(int(piece))
        except ValueError as exc:
            raise ConfigError(
                "TELEGRAM_ALLOWED_CHAT_IDS must be a comma-separated list of integers"
            ) from exc
    return frozenset(chat_ids)
