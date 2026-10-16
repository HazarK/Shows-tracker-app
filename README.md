# TV Season Tracker

A Telegram bot that follows the shows you add and messages you when a new season's premiere date has arrived. Show facts come from [TMDB](https://www.themoviedb.org/). Seasons that were already out when a show was added are stored silently, so each new season sends one alert.

Streaming availability is out of scope. An alert means the premiere date has arrived, not that a title is on a particular service.

## Commands

- `/add <show name>` — search TMDB and confirm the match on inline buttons
- `/list` — show the shows you follow
- `/remove <show name>` — stop following a show after you confirm the match
- `/cancel` — dismiss the current choice
- `/help` — show the commands

`/add` and `/remove` ask you to pick when several titles match. A choice expires after 15 minutes, and a new `/add` or `/remove` replaces any choice that is still open.

## How an alert is sent once

A new season is a numbered season whose TMDB premiere date is today or earlier in `CHECK_TIMEZONE`. Season 0 and specials are ignored.

When a show is confirmed, seasons that are already out are saved as `baseline` and no message is sent. The daily check sends `🎬 New season available: {title} — Season {n}` only for a season number that is not stored yet, then writes that row after Telegram accepts the message. A failed send stays unrecorded and is retried on the next run. A skipped day still sends the alert later, because the check compares TMDB with the seasons already stored.

## Run the bot

Telegram delivers each update to one place. Use either the hosted webhook or the local process.

### Hosted on Supabase

The hosted bot is two Edge Functions and a Postgres database. Nothing has to stay running between a Telegram message and the daily check. Use a Supabase project of its own. The free tier is enough.

Install the [Supabase CLI](https://supabase.com/docs/guides/cli), then from this repo:

```bash
supabase login
supabase link --project-ref <project-ref>
```

`<project-ref>` is the id in the project URL, `https://<project-ref>.supabase.co`.

Create two random strings, then set the function secrets. Supabase injects `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Keep every secret out of git.

```bash
supabase secrets set \
  TELEGRAM_BOT_TOKEN=<bot-token> \
  TMDB_API_KEY=<tmdb-key> \
  TELEGRAM_WEBHOOK_SECRET=<random-string> \
  CRON_SECRET=<another-random-string> \
  CHECK_TIMEZONE=UTC
```

`CHECK_TIMEZONE` decides whether a premiere date is today or earlier. It does not choose the hour. Leave `TELEGRAM_ALLOWED_CHAT_IDS` unset to allow any chat.

Deploy the database and the functions:

```bash
supabase db push
supabase functions deploy telegram-webhook --no-verify-jwt
supabase functions deploy check-seasons --no-verify-jwt
```

`supabase/config.toml` sets `verify_jwt = false` for both functions. Telegram does not send a Supabase JWT. Each function checks its own secret instead. A webhook call without the matching secret gets `401`.

Point Telegram at the webhook. `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET` must be set in the shell, and the secret must be the same value stored above.

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=https://<project-ref>.supabase.co/functions/v1/telegram-webhook" \
  --data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  --data-urlencode 'allowed_updates=["message","callback_query"]'
```

Schedule the daily check in the Supabase dashboard under Cron. Enable the `pg_cron` extension first. The timeout field is in milliseconds.

- Schedule: `0 9 * * *` (09:00 UTC every day)
- Type: HTTP request
- Method: POST
- URL: `https://<project-ref>.supabase.co/functions/v1/check-seasons`
- Header: `x-cron-secret` set to the `CRON_SECRET` value
- Header: `Content-Type: application/json`
- Body: `{}`
- Timeout: `30000`

The cron clock is UTC. It does not read `CHECK_HOUR`. A `401` in the `check-seasons` log means the header does not match `CRON_SECRET`.

To run the local process again, remove the webhook first:

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
```

The local SQLite file and the hosted database are separate. Shows followed in one are not copied to the other.

### Local process

The local process long-polls Telegram, so it does not need a public URL. The daily check runs in the same process.

- Python 3.12 or newer
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A TMDB v3 API key from [themoviedb.org settings](https://www.themoviedb.org/settings/api)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Fill in `TELEGRAM_BOT_TOKEN` and `TMDB_API_KEY` in `.env`, then start the bot:

```bash
python -m tvtracker
```

If `python` is not the virtualenv interpreter, use `.venv/bin/python -m tvtracker`.

Run the season check once, without waiting for `CHECK_HOUR`:

```bash
python -m tvtracker.jobs.check_seasons
```

If nobody is following a show, that command exits without calling TMDB. If the process is stopped at `CHECK_HOUR`, that day's check waits until the next day.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_PATH` | SQLite file for the local process. Default: `data/tvtracker.sqlite` |
| `CHECK_TIMEZONE` | Timezone used to decide whether a premiere date has arrived. Default: `UTC` |
| `CHECK_HOUR` | Hour (0–23) in that timezone for the local daily check. Default: `9`. The hosted cron does not read this. |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Optional comma-separated chat ids. Empty means any chat can use the bot. |
| `TELEGRAM_WEBHOOK_SECRET` | Shared secret Telegram sends to `telegram-webhook`. Hosted bot only. |
| `CRON_SECRET` | Shared secret the daily job sends to `check-seasons`. Hosted bot only. |

To allow only specific chats, send `/start`, read `start chat_id=...` from the local process log or from the `telegram-webhook` function log, and set `TELEGRAM_ALLOWED_CHAT_IDS` to that id. On Supabase, update the secret. A redeploy is not required.

```bash
supabase secrets set TELEGRAM_ALLOWED_CHAT_IDS=<chat-id>
```

## Tests

```bash
.venv/bin/pytest
deno test supabase/functions/_shared/seasons_test.ts supabase/functions/_shared/check_test.ts
```

Pytest uses a temporary SQLite file, recorded TMDB JSON fixtures, and fakes for Telegram. It does not call the network. The Deno tests cover the hosted season filter and the once-per-season check. They do not call Telegram, TMDB, or Supabase.

To run those checks before each commit:

```bash
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit scripts/check-git-root.sh
```
