CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_chat_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracked_shows (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    tmdb_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    first_air_year INTEGER,
    added_at TEXT NOT NULL,
    UNIQUE (user_id, tmdb_id)
);

CREATE TABLE IF NOT EXISTS seen_seasons (
    id INTEGER PRIMARY KEY,
    tracked_show_id INTEGER NOT NULL REFERENCES tracked_shows (id) ON DELETE CASCADE,
    season_number INTEGER NOT NULL,
    air_date TEXT,
    status TEXT NOT NULL CHECK (status IN ('baseline', 'notified')),
    notified_at TEXT,
    UNIQUE (tracked_show_id, season_number)
);

CREATE TABLE IF NOT EXISTS pending_choices (
    telegram_chat_id INTEGER PRIMARY KEY,
    action TEXT NOT NULL CHECK (action IN ('add', 'remove')),
    payload_json TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
