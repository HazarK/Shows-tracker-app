import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest

from tvtracker.db.repository import AlreadyTracking
from tvtracker.domain.seasons import Season

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)


def test_database_uses_wal(repo):
    connection = sqlite3.connect(repo.db_path)
    try:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        connection.close()
    assert mode == "wal"


def test_add_list_and_empty(repo):
    assert repo.list_tracked_shows(1) == []
    assert repo.list_all_tracked_shows() == []

    saved = repo.add_tracked_show(
        1,
        tmdb_id=95396,
        title="Severance",
        first_air_year=2022,
        baseline_seasons=[],
        added_at=NOW,
    )

    assert saved.telegram_chat_id == 1
    assert saved.tmdb_id == 95396
    assert repo.list_tracked_shows(1) == [saved]
    assert repo.list_tracked_shows(2) == []


def test_same_show_can_be_tracked_by_two_chats(repo):
    repo.add_tracked_show(
        1, tmdb_id=5, title="Severance", first_air_year=2022, baseline_seasons=[]
    )
    repo.add_tracked_show(
        2, tmdb_id=5, title="Severance", first_air_year=2022, baseline_seasons=[]
    )

    assert len(repo.list_all_tracked_shows()) == 2


def test_duplicate_show_for_the_same_chat_raises(repo):
    repo.add_tracked_show(
        1, tmdb_id=5, title="Severance", first_air_year=2022, baseline_seasons=[]
    )

    with pytest.raises(AlreadyTracking):
        repo.add_tracked_show(
            1, tmdb_id=5, title="Severance", first_air_year=2022, baseline_seasons=[]
        )

    assert len(repo.list_tracked_shows(1)) == 1


def test_list_is_ordered_by_title(repo):
    repo.add_tracked_show(
        1, tmdb_id=2, title="beta", first_air_year=None, baseline_seasons=[]
    )
    repo.add_tracked_show(
        1, tmdb_id=1, title="Alpha", first_air_year=2010, baseline_seasons=[]
    )

    assert [show.title for show in repo.list_tracked_shows(1)] == ["Alpha", "beta"]


def test_remove_deletes_only_the_owners_show_and_cascades_seasons(repo):
    first = repo.add_tracked_show(
        1,
        tmdb_id=5,
        title="Severance",
        first_air_year=2022,
        baseline_seasons=[Season(1, date(2022, 2, 18))],
    )
    second = repo.add_tracked_show(
        2,
        tmdb_id=5,
        title="Severance",
        first_air_year=2022,
        baseline_seasons=[Season(1, date(2022, 2, 18))],
    )

    assert repo.remove_tracked_show(1, second.id) is False
    assert repo.get_tracked_show(2, second.id) is not None
    assert repo.remove_tracked_show(1, first.id) is True
    assert repo.get_tracked_show(1, first.id) is None
    assert repo.seen_seasons(first.id) == []
    assert len(repo.seen_seasons(second.id)) == 1


def test_baseline_seasons_are_stored_once(repo):
    show = repo.add_tracked_show(
        1,
        tmdb_id=5,
        title="Severance",
        first_air_year=2022,
        baseline_seasons=[
            Season(1, date(2022, 1, 1)),
            Season(1, date(2022, 1, 2)),
            Season(2, None),
        ],
    )

    seen = repo.seen_seasons(show.id)
    assert [(season.season_number, season.status, season.air_date) for season in seen] == [
        (1, "baseline", date(2022, 1, 1)),
        (2, "baseline", None),
    ]
    assert repo.seen_season_numbers(show.id) == {1, 2}


def test_notified_season_is_recorded_once_and_does_not_replace_baseline(repo):
    show = repo.add_tracked_show(
        1,
        tmdb_id=5,
        title="Severance",
        first_air_year=2022,
        baseline_seasons=[Season(1, date(2022, 2, 18))],
    )

    assert repo.record_notified_season(show.id, 1, date(2022, 2, 18), notified_at=NOW) is False
    assert repo.seen_seasons(show.id)[0].status == "baseline"

    assert repo.record_notified_season(show.id, 3, date(2026, 10, 15), notified_at=NOW) is True
    assert repo.record_notified_season(show.id, 3, date(2026, 10, 15), notified_at=NOW) is False
    notified = repo.seen_seasons(show.id)[1]
    assert notified.status == "notified"
    assert notified.notified_at is not None


def test_title_search_prefers_an_exact_match(repo):
    repo.add_tracked_show(
        1, tmdb_id=1, title="Severance", first_air_year=2022, baseline_seasons=[]
    )
    repo.add_tracked_show(
        1,
        tmdb_id=2,
        title="Severance: Aftershow",
        first_air_year=2024,
        baseline_seasons=[],
    )

    exact = repo.find_tracked_by_title(1, "severance")
    assert [show.title for show in exact] == ["Severance"]
    partial = repo.find_tracked_by_title(1, "after")
    assert [show.title for show in partial] == ["Severance: Aftershow"]
    assert repo.find_tracked_by_title(1, "nope") == []


def test_pending_choice_roundtrip_expiry_and_replace(repo):
    expires = NOW + timedelta(minutes=15)
    repo.set_pending_choice(7, "add", {"tmdb_ids": [9]}, expires)
    pending = repo.get_pending_choice(7, NOW)
    assert pending is not None
    assert pending.action == "add"
    assert pending.payload == {"tmdb_ids": [9]}

    repo.set_pending_choice(7, "remove", {"show_ids": [4]}, expires)
    replaced = repo.get_pending_choice(7, NOW)
    assert replaced is not None
    assert replaced.action == "remove"
    assert replaced.payload == {"show_ids": [4]}

    assert repo.get_pending_choice(7, expires) is None
    assert repo.get_pending_choice(7, NOW) is None

    repo.set_pending_choice(7, "add", {"tmdb_ids": [1]}, expires)
    repo.clear_pending_choice(7)
    assert repo.get_pending_choice(7, NOW) is None
