# TV Season Tracker

Telegram bot that tracks shows you add and messages you when a new season's premiere date has arrived. Show facts come from [TMDB](https://www.themoviedb.org/). Seasons that were already out when you added a show are stored silently, so each new season sends one alert.

## Run on Supabase

The hosted bot is two Edge Functions and a Postgres database. Nothing has to stay running on your laptop. Between a Telegram message and the daily check, the functions are asleep.

Use a Supabase project of its own, separate from any other app. The free tier is enough.

Stop the local process first if it is running (`python -m tvtracker`). Telegram delivers each update to one place. After the webhook below is set, the laptop process no longer receives commands.

### 1. Link the project

Install the [Supabase CLI](https://supabase.com/docs/guides/cli), then from this repo:

```bash
supabase login
supabase link --project-ref <project-ref>
```

`<project-ref>` is the id in the project URL, `https://<project-ref>.supabase.co`.

### 2. Set secrets

Create two random strings for the webhook secret and the cron secret. Then:

```bash
supabase secrets set \
  TELEGRAM_BOT_TOKEN=<bot-token> \
  TMDB_API_KEY=<tmdb-key> \
  TELEGRAM_WEBHOOK_SECRET=<random-string> \
  CRON_SECRET=<another-random-string> \
  CHECK_TIMEZONE=UTC
```

`CHECK_TIMEZONE` decides whether a premiere date is today or earlier. It does not choose the hour. Leave `TELEGRAM_ALLOWED_CHAT_IDS` unset until you have read your chat id in step 6.

Supabase injects `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` into the functions. Do not put these secrets in git.

### 3. Deploy the database and the functions

```bash
supabase db push
supabase functions deploy telegram-webhook --no-verify-jwt
supabase functions deploy check-seasons --no-verify-jwt
```

`supabase/config.toml` also sets `verify_jwt = false` for both functions. Telegram does not send a Supabase JWT. Each function checks its own secret instead.

### 4. Point Telegram at the webhook

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=https://<project-ref>.supabase.co/functions/v1/telegram-webhook" \
  --data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  --data-urlencode 'allowed_updates=["message","callback_query"]'
```

The secret token is the `TELEGRAM_WEBHOOK_SECRET` from step 2. A call without that header gets `401`.

To use the local process again later, remove the webhook and start the laptop process:

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
```

### 5. Schedule the daily check

In the Supabase dashboard, open Cron and create a job:

- Schedule: `0 9 * * *` (09:00 UTC every day)
- Type: HTTP request
- Method: POST
- URL: `https://<project-ref>.supabase.co/functions/v1/check-seasons`
- Header: `x-cron-secret` set to the `CRON_SECRET` value
- Header: `Content-Type: application/json`
- Body: `{}`
- Timeout: 30 seconds if the form asks for one

The cron clock is UTC. It does not read `CHECK_HOUR`. A 401 in the function log means the header does not match `CRON_SECRET`.

If a day is skipped, the next run still sends the alert. The check compares TMDB with the seasons already stored, rather than only looking at the last day.

### 6. Lock the bot to your chat

Send `/start` to the bot. In the Supabase dashboard, open Edge Functions → `telegram-webhook` → Logs and find `start chat_id=...`. Updating the secret is enough; you do not need to redeploy:

```bash
supabase secrets set TELEGRAM_ALLOWED_CHAT_IDS=<chat-id>
```

Shows already stored in the local SQLite file are not copied. Add them again in Telegram. Seasons that are already out are saved as baseline, so you do not get a burst of old alerts.

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

The process long-polls Telegram, so it does not need a public URL. Leave it running. Do not start it while the Supabase webhook from above is set; delete that webhook first. The daily season check runs in this same process at `CHECK_HOUR`. If the process is stopped at that hour, that day's check waits until the next day. Use the one-shot command below to run it immediately.

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
deno test supabase/functions/_shared/seasons_test.ts supabase/functions/_shared/check_test.ts
```

Pytest uses a temporary SQLite file, recorded TMDB JSON fixtures, and fakes for Telegram. It does not call the network. The Deno tests cover the hosted season filter and the once-per-season check. They do not call Telegram, TMDB, or Supabase.

This clone runs those tests before each commit. On a new clone, install the hook once:

```bash
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit scripts/check-git-root.sh
```

## How a season is alerted once

A new season is a numbered season (not season 0 or a special) whose TMDB premiere date is today or earlier in `CHECK_TIMEZONE`. Streaming availability is out of scope.

When you confirm a show, those already-released seasons are saved as `baseline` and no message is sent. The daily job sends `🎬 New season available: {title} — Season {n}` only for a season number that is not stored yet, then writes the row after Telegram accepts the message. A failed send stays unrecorded and is retried on the next run.
