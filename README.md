# TV Season Tracker

Telegram bot that tracks shows you add and messages you when a new season's premiere date has arrived. Show facts come from [TMDB](https://www.themoviedb.org/). Seasons that were already out when you added a show are stored silently, so each new season sends one alert.

## Prerequisites

- Python 3.12 or newer
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A TMDB v3 API key from [themoviedb.org settings](https://www.themoviedb.org/settings/api)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Fill in `TELEGRAM_BOT_TOKEN` and `TMDB_API_KEY` in `.env`.

| Variable | Purpose |
| --- | --- |
| `DATABASE_PATH` | SQLite file. Default: `data/tvtracker.sqlite` |
| `CHECK_TIMEZONE` | Timezone used for "has this premiere date arrived?". Default: `UTC` |
| `CHECK_HOUR` | Hour (0–23) in that timezone for the daily check. Default: `9` |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Optional comma-separated chat ids. Empty means any chat can use the bot |

To lock the bot to yourself, send `/start`, read `start chat_id=...` in the process log, and put that id in `TELEGRAM_ALLOWED_CHAT_IDS`.

## Run the bot

Use the virtualenv interpreter. On this Mac, `python` is Python 3.10 and skips the virtualenv even after `source .venv/bin/activate`.

```bash
.venv/bin/python -m tvtracker
```

The process long-polls Telegram, so it does not need a public URL. Leave it running. The daily season check runs in this same process at `CHECK_HOUR`. If the process is stopped at that hour, that day's check waits until the next day. Use the one-shot command below to run it immediately.

## Run the season check once

```bash
.venv/bin/python -m tvtracker.jobs.check_seasons
```

Use this locally instead of waiting for `CHECK_HOUR`. If nobody is following a show, the command exits without calling TMDB.

## Commands

- `/add <show name>` — search TMDB and confirm the match on inline buttons
- `/list` — show the shows you follow
- `/remove <show name>` — stop following a show after you confirm the match (asks you to pick if several titles match)
- `/cancel` — dismiss the current choice
- `/help` — show the commands

A choice expires after 15 minutes. `/add` and `/remove` replace any choice that is still open.

## Tests

```bash
.venv/bin/pytest
```

Tests use a temporary SQLite file, recorded TMDB JSON fixtures, and fakes for Telegram. They do not call the network.

This clone runs those tests before each commit. On a new clone, install the hook once:

```bash
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit scripts/check-git-root.sh
```

## How a season is alerted once

A new season is a numbered season (not season 0 or a special) whose TMDB premiere date is today or earlier in `CHECK_TIMEZONE`. Streaming availability is out of scope.

When you confirm a show, those already-released seasons are saved as `baseline` and no message is sent. The daily job sends `🎬 New season available: {title} — Season {n}` only for a season number that is not stored yet, then writes the row after Telegram accepts the message. A failed send stays unrecorded and is retried on the next run.
