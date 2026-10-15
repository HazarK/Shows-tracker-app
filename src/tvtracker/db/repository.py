"""SQLite persistence for users, tracked shows, and season notifications."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from tvtracker.domain.seasons import Season


class AlreadyTracking(Exception):
    """The chat is already following this TMDB show."""

    def __init__(self, tmdb_id: int) -> None:
        self.tmdb_id = tmdb_id
        super().__init__(f"already tracking tmdb id {tmdb_id}")


@dataclass(frozen=True)
class TrackedShow:
    id: int
    telegram_chat_id: int
    tmdb_id: int
    title: str
    first_air_year: int | None
    added_at: str


@dataclass(frozen=True)
class SeenSeason:
    season_number: int
    air_date: date | None
    status: str
    notified_at: str | None


@dataclass(frozen=True)
class PendingChoice:
    telegram_chat_id: int
    action: str
    payload: dict
    expires_at: datetime


class Repository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        with self._connect() as conn:
            if self.db_path != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL").fetchone()
            conn.executescript(schema)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def add_tracked_show(
        self,
        telegram_chat_id: int,
        *,
        tmdb_id: int,
        title: str,
        first_air_year: int | None,
        baseline_seasons: Sequence[Season],
        added_at: datetime | None = None,
    ) -> TrackedShow:
        added = added_at or datetime.now(timezone.utc)
        baseline: dict[int, Season] = {}
        for season in baseline_seasons:
            baseline.setdefault(season.season_number, season)

        with self._connect() as conn:
            user_id = self._get_or_create_user(conn, telegram_chat_id, added)
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO tracked_shows (
                        user_id, tmdb_id, title, first_air_year, added_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, tmdb_id, title, first_air_year, _iso(added)),
                )
            except sqlite3.IntegrityError as exc:
                raise AlreadyTracking(tmdb_id) from exc
            show_id = cursor.lastrowid
            if show_id is None:
                raise RuntimeError("tracked show insert did not return an id")
            for season in baseline.values():
                conn.execute(
                    """
                    INSERT INTO seen_seasons (
                        tracked_show_id, season_number, air_date, status, notified_at
                    )
                    VALUES (?, ?, ?, 'baseline', NULL)
                    """,
                    (show_id, season.season_number, _date_text(season.air_date)),
                )

        saved = self.get_tracked_show(telegram_chat_id, int(show_id))
        if saved is None:
            raise RuntimeError("tracked show disappeared after insert")
        return saved

    def list_tracked_shows(self, telegram_chat_id: int) -> list[TrackedShow]:
        with self._connect() as conn:
            rows = conn.execute(
                f"{_SHOW_SELECT} WHERE u.telegram_chat_id = ? "
                "ORDER BY ts.title COLLATE NOCASE, ts.id",
                (telegram_chat_id,),
            ).fetchall()
        return [_row_to_show(row) for row in rows]

    def list_all_tracked_shows(self) -> list[TrackedShow]:
        with self._connect() as conn:
            rows = conn.execute(f"{_SHOW_SELECT} ORDER BY ts.id").fetchall()
        return [_row_to_show(row) for row in rows]

    def get_tracked_show(
        self, telegram_chat_id: int, tracked_show_id: int
    ) -> TrackedShow | None:
        with self._connect() as conn:
            row = conn.execute(
                f"{_SHOW_SELECT} WHERE u.telegram_chat_id = ? AND ts.id = ?",
                (telegram_chat_id, tracked_show_id),
            ).fetchone()
        if row is None:
            return None
        return _row_to_show(row)

    def remove_tracked_show(self, telegram_chat_id: int, tracked_show_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM tracked_shows
                WHERE id = ?
                  AND user_id = (SELECT id FROM users WHERE telegram_chat_id = ?)
                """,
                (tracked_show_id, telegram_chat_id),
            )
            return cursor.rowcount == 1

    def find_tracked_by_title(self, telegram_chat_id: int, query: str) -> list[TrackedShow]:
        shows = self.list_tracked_shows(telegram_chat_id)
        needle = query.casefold().strip()
        exact = [show for show in shows if show.title.casefold() == needle]
        if exact:
            return exact
        return [show for show in shows if needle in show.title.casefold()]

    def seen_seasons(self, tracked_show_id: int) -> list[SeenSeason]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT season_number, air_date, status, notified_at
                FROM seen_seasons
                WHERE tracked_show_id = ?
                ORDER BY season_number
                """,
                (tracked_show_id,),
            ).fetchall()
        return [
            SeenSeason(
                season_number=int(row["season_number"]),
                air_date=_text_date(row["air_date"]),
                status=str(row["status"]),
                notified_at=None if row["notified_at"] is None else str(row["notified_at"]),
            )
            for row in rows
        ]

    def seen_season_numbers(self, tracked_show_id: int) -> set[int]:
        return {season.season_number for season in self.seen_seasons(tracked_show_id)}

    def record_notified_season(
        self,
        tracked_show_id: int,
        season_number: int,
        air_date: date,
        notified_at: datetime | None = None,
    ) -> bool:
        when = _iso(notified_at or datetime.now(timezone.utc))
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO seen_seasons (
                    tracked_show_id, season_number, air_date, status, notified_at
                )
                VALUES (?, ?, ?, 'notified', ?)
                ON CONFLICT (tracked_show_id, season_number) DO NOTHING
                """,
                (tracked_show_id, season_number, air_date.isoformat(), when),
            )
            return cursor.rowcount == 1

    def set_pending_choice(
        self,
        telegram_chat_id: int,
        action: str,
        payload: dict,
        expires_at: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_choices (
                    telegram_chat_id, action, payload_json, expires_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT (telegram_chat_id) DO UPDATE SET
                    action = excluded.action,
                    payload_json = excluded.payload_json,
                    expires_at = excluded.expires_at
                """,
                (telegram_chat_id, action, json.dumps(payload), _iso(expires_at)),
            )

    def get_pending_choice(
        self, telegram_chat_id: int, now: datetime
    ) -> PendingChoice | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT telegram_chat_id, action, payload_json, expires_at
                FROM pending_choices
                WHERE telegram_chat_id = ?
                """,
                (telegram_chat_id,),
            ).fetchone()
            if row is None:
                return None
            expires_at = _parse_iso(str(row["expires_at"]))
            if expires_at <= _as_utc(now):
                conn.execute(
                    "DELETE FROM pending_choices WHERE telegram_chat_id = ?",
                    (telegram_chat_id,),
                )
                return None
            return PendingChoice(
                telegram_chat_id=int(row["telegram_chat_id"]),
                action=str(row["action"]),
                payload=json.loads(str(row["payload_json"])),
                expires_at=expires_at,
            )

    def clear_pending_choice(self, telegram_chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_choices WHERE telegram_chat_id = ?",
                (telegram_chat_id,),
            )

    def _get_or_create_user(
        self, conn: sqlite3.Connection, telegram_chat_id: int, now: datetime
    ) -> int:
        conn.execute(
            """
            INSERT INTO users (telegram_chat_id, created_at)
            VALUES (?, ?)
            ON CONFLICT (telegram_chat_id) DO NOTHING
            """,
            (telegram_chat_id, _iso(now)),
        )
        row = conn.execute(
            "SELECT id FROM users WHERE telegram_chat_id = ?",
            (telegram_chat_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("user row missing after insert")
        return int(row["id"])


_SHOW_SELECT = """
    SELECT
        ts.id,
        u.telegram_chat_id,
        ts.tmdb_id,
        ts.title,
        ts.first_air_year,
        ts.added_at
    FROM tracked_shows ts
    JOIN users u ON u.id = ts.user_id
"""


def _row_to_show(row: sqlite3.Row) -> TrackedShow:
    year = row["first_air_year"]
    return TrackedShow(
        id=int(row["id"]),
        telegram_chat_id=int(row["telegram_chat_id"]),
        tmdb_id=int(row["tmdb_id"]),
        title=str(row["title"]),
        first_air_year=None if year is None else int(year),
        added_at=str(row["added_at"]),
    )


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="seconds")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)


def _date_text(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _text_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)
