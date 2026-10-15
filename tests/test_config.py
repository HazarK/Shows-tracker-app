from pathlib import Path

import pytest

from tvtracker.config import ConfigError, load_config


def test_load_config_applies_defaults(tmp_path):
    config = load_config(
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TMDB_API_KEY": "key",
        }
    )

    assert config.telegram_bot_token == "token"
    assert config.tmdb_api_key == "key"
    assert config.database_path == Path("data/tvtracker.sqlite")
    assert config.check_hour == 9
    assert getattr(config.check_timezone, "key", None) == "UTC"
    assert config.allowed_chat_ids is None


def test_load_config_parses_allowlist_and_schedule(tmp_path):
    del tmp_path
    config = load_config(
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TMDB_API_KEY": "key",
            "DATABASE_PATH": "custom/bot.sqlite",
            "CHECK_TIMEZONE": "Europe/Amsterdam",
            "CHECK_HOUR": "15",
            "TELEGRAM_ALLOWED_CHAT_IDS": "10, 20",
        }
    )

    assert config.database_path == Path("custom/bot.sqlite")
    assert config.check_hour == 15
    assert getattr(config.check_timezone, "key", None) == "Europe/Amsterdam"
    assert config.allowed_chat_ids == frozenset({10, 20})


@pytest.mark.parametrize(
    "environ",
    [
        {"TMDB_API_KEY": "key"},
        {"TELEGRAM_BOT_TOKEN": "token"},
        {"TELEGRAM_BOT_TOKEN": "token", "TMDB_API_KEY": "key", "CHECK_HOUR": "24"},
        {"TELEGRAM_BOT_TOKEN": "token", "TMDB_API_KEY": "key", "CHECK_HOUR": "noon"},
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TMDB_API_KEY": "key",
            "CHECK_TIMEZONE": "Not/AZone",
        },
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TMDB_API_KEY": "key",
            "TELEGRAM_ALLOWED_CHAT_IDS": "10,nope",
        },
    ],
)
def test_load_config_rejects_invalid_settings(environ):
    with pytest.raises(ConfigError):
        load_config(environ)
