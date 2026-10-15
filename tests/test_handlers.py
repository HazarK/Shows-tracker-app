from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from telegram.ext import Application

from tvtracker.bot.handlers import (
    Button,
    add_show,
    cancel_pending,
    handle_callback,
    help_message,
    list_shows,
    register_handlers,
    rejection_for,
    remove_show,
    start_message,
)
from tvtracker.bot.messages import (
    API_UNAVAILABLE,
    CHOICE_EXPIRED,
    CHOICE_INVALID,
    EMPTY_LIST,
    PRIVATE_BOT,
    button_label,
    found_prompt,
    new_season_message,
    not_found_message,
)
from tvtracker.config import load_config
from tvtracker.db.repository import Repository
from tvtracker.domain.seasons import Season
from tvtracker.jobs.check_seasons import check_all
from tvtracker.tmdb.client import ShowDetails, ShowNotFound, ShowSearchResult, TmdbUnavailable

from fakes import FakeNotifier, FakeTmdb

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 15)
CHAT = 42


def _severance_details() -> ShowDetails:
    return ShowDetails(
        95396,
        "Severance",
        2022,
        (
            Season(0, date(2022, 3, 25)),
            Season(1, date(2022, 2, 18)),
            Season(2, date(2025, 1, 17)),
            Season(3, None),
            Season(4, date(2026, 12, 1)),
        ),
    )


def test_prd_copy():
    assert not_found_message("XYZ") == (
        "I couldn't find a show matching <b>XYZ</b>. Try another title."
    )
    assert EMPTY_LIST == "You aren't following any shows yet. Use /add <show name> to add one."
    assert new_season_message("Severance", 3) == "🎬 New season available: Severance — Season 3"
    assert found_prompt("Severance", 2022) == (
        "I found <b>Severance (2022)</b>. Is this the show you want to follow?"
    )
    assert not_found_message("A & B <show>") == (
        "I couldn't find a show matching <b>A &amp; B &lt;show&gt;</b>. Try another title."
    )
    assert len(button_label("A" * 80, 2022)) == 60


def test_start_and_help_share_the_command_list():
    assert start_message() == help_message()
    assert "/add <show name>" in help_message().text
    assert "/remove <show name>" in help_message().text


def test_allowlist():
    assert rejection_for(1, None) is None
    assert rejection_for(2, frozenset({2})) is None
    denied = rejection_for(1, frozenset({2}))
    assert denied is not None
    assert denied.text == PRIVATE_BOT


def test_list_empty_and_populated(repo):
    assert list_shows(CHAT, repo=repo).text == EMPTY_LIST
    repo.add_tracked_show(
        CHAT, tmdb_id=1, title="Severance", first_air_year=2022, baseline_seasons=[]
    )
    repo.add_tracked_show(
        CHAT, tmdb_id=2, title="Untitled", first_air_year=None, baseline_seasons=[]
    )

    text = list_shows(CHAT, repo=repo).text

    assert text == "You're following:\n• Severance (2022)\n• Untitled"


def test_add_usage_not_found_and_api_down(repo):
    tmdb = FakeTmdb()
    assert add_show(CHAT, "  ", tmdb=tmdb, repo=repo, now=NOW).text == "Usage: /add <show name>"

    tmdb.search_error = TmdbUnavailable("down")
    assert add_show(CHAT, "Severance", tmdb=tmdb, repo=repo, now=NOW).text == API_UNAVAILABLE

    tmdb.search_error = None
    missing = add_show(CHAT, "XYZ", tmdb=tmdb, repo=repo, now=NOW)
    assert missing.text == not_found_message("XYZ")
    assert missing.parse_mode == "HTML"
    assert repo.get_pending_choice(CHAT, NOW) is None


def test_add_one_match_asks_for_confirmation(repo):
    tmdb = FakeTmdb()
    tmdb.results = [ShowSearchResult(95396, "Severance", 2022)]

    outgoing = add_show(CHAT, "Severance", tmdb=tmdb, repo=repo, now=NOW)

    assert outgoing.text == found_prompt("Severance", 2022)
    assert outgoing.buttons == (
        (Button("Confirm", "add:95396"), Button("Cancel", "add:cancel")),
    )
    assert tmdb.searches == [("Severance", 5)]


def test_add_several_matches_offers_at_most_five_buttons(repo):
    tmdb = FakeTmdb()
    tmdb.results = [
        ShowSearchResult(index, f"Show {index}", 2000 + index) for index in range(1, 7)
    ]

    outgoing = add_show(CHAT, "Show", tmdb=tmdb, repo=repo, now=NOW)

    labels = [row[0].text for row in outgoing.buttons]
    assert labels == ["Show 1 (2001)", "Show 2 (2002)", "Show 3 (2003)", "Show 4 (2004)", "Show 5 (2005)", "Cancel"]
    assert outgoing.buttons[-1][0].callback_data == "add:cancel"


def test_confirm_baselines_released_seasons_and_job_alerts_only_the_new_one(repo):
    tmdb = FakeTmdb()
    tmdb.results = [ShowSearchResult(95396, "Severance", 2022)]
    details = ShowDetails(
        95396,
        "Severance",
        2022,
        _severance_details().seasons + (Season(5, date(2026, 10, 16)),),
    )
    tmdb.details[95396] = details

    add_show(CHAT, "Severance", tmdb=tmdb, repo=repo, now=NOW)
    confirmed = handle_callback(
        CHAT, "add:95396", tmdb=tmdb, repo=repo, today=TODAY, now=NOW
    )

    assert confirmed.text == "You're now following Severance (2022)."
    show = repo.list_tracked_shows(CHAT)[0]
    assert [(season.season_number, season.status) for season in repo.seen_seasons(show.id)] == [
        (1, "baseline"),
        (2, "baseline"),
    ]
    assert repo.get_pending_choice(CHAT, NOW) is None

    silent = FakeNotifier()
    assert check_all(repo, tmdb, silent, TODAY).notified == 0

    premiere_day = date(2026, 10, 16)
    notifier = FakeNotifier()
    assert check_all(repo, tmdb, notifier, premiere_day).notified == 1
    assert notifier.messages == [(CHAT, "🎬 New season available: Severance — Season 5")]
    assert check_all(repo, tmdb, FakeNotifier(), premiere_day).notified == 0


def test_duplicate_add_is_reported_without_a_second_row(repo):
    tmdb = FakeTmdb()
    tmdb.results = [ShowSearchResult(95396, "Severance", 2022)]
    tmdb.details[95396] = _severance_details()
    add_show(CHAT, "Severance", tmdb=tmdb, repo=repo, now=NOW)
    handle_callback(CHAT, "add:95396", tmdb=tmdb, repo=repo, today=TODAY, now=NOW)

    again = add_show(CHAT, "Severance", tmdb=tmdb, repo=repo, now=NOW)

    assert again.text == "You're already following Severance (2022)."
    assert again.buttons == ()
    assert len(repo.list_tracked_shows(CHAT)) == 1


def test_confirm_api_failure_keeps_the_choice_and_not_found_clears_it(repo):
    tmdb = FakeTmdb()
    tmdb.results = [ShowSearchResult(95396, "Severance", 2022)]
    tmdb.detail_errors[95396] = TmdbUnavailable("down")
    add_show(CHAT, "Severance", tmdb=tmdb, repo=repo, now=NOW)

    unavailable = handle_callback(
        CHAT, "add:95396", tmdb=tmdb, repo=repo, today=TODAY, now=NOW
    )

    assert unavailable.text == API_UNAVAILABLE
    assert repo.get_pending_choice(CHAT, NOW) is not None

    tmdb.detail_errors[95396] = ShowNotFound("gone")
    missing = handle_callback(
        CHAT, "add:95396", tmdb=tmdb, repo=repo, today=TODAY, now=NOW
    )
    assert missing.text == "I couldn't find that show anymore. Try another title."
    assert repo.get_pending_choice(CHAT, NOW) is None


def test_expired_and_invalid_choices(repo):
    tmdb = FakeTmdb()
    tmdb.results = [
        ShowSearchResult(1, "One", 2001),
        ShowSearchResult(2, "Two", 2002),
    ]
    add_show(CHAT, "One", tmdb=tmdb, repo=repo, now=NOW)

    rejected = handle_callback(CHAT, "add:99", tmdb=tmdb, repo=repo, today=TODAY, now=NOW)
    assert rejected.text == CHOICE_INVALID
    assert repo.get_pending_choice(CHAT, NOW) is not None

    expired = handle_callback(
        CHAT,
        "add:1",
        tmdb=tmdb,
        repo=repo,
        today=TODAY,
        now=NOW + timedelta(minutes=16),
    )
    assert expired.text == CHOICE_EXPIRED
    assert repo.list_tracked_shows(CHAT) == []


def test_cancel(repo):
    tmdb = FakeTmdb()
    tmdb.results = [ShowSearchResult(95396, "Severance", 2022)]
    add_show(CHAT, "Severance", tmdb=tmdb, repo=repo, now=NOW)

    assert cancel_pending(CHAT, repo=repo, now=NOW).text == "Cancelled."
    assert cancel_pending(CHAT, repo=repo, now=NOW).text == "Nothing to cancel."
    assert (
        handle_callback(
            CHAT, "add:cancel", tmdb=tmdb, repo=repo, today=TODAY, now=NOW
        ).text
        == "Cancelled."
    )


def test_remove_unique_substring_and_missing(repo):
    repo.add_tracked_show(
        CHAT, tmdb_id=1, title="Severance", first_air_year=2022, baseline_seasons=[]
    )
    tmdb = FakeTmdb()
    tmdb.results = [ShowSearchResult(9, "Other", 1999)]
    add_show(CHAT, "Other", tmdb=tmdb, repo=repo, now=NOW)
    assert repo.get_pending_choice(CHAT, NOW) is not None

    removed = remove_show(CHAT, "sev", repo=repo, now=NOW)

    assert removed.text == "Stopped following Severance (2022)."
    assert repo.list_tracked_shows(CHAT) == []
    assert repo.get_pending_choice(CHAT, NOW) is None
    assert (
        remove_show(CHAT, "Severance", repo=repo, now=NOW).text
        == "You're not following a show matching Severance."
    )
    assert remove_show(CHAT, " ", repo=repo, now=NOW).text == "Usage: /remove <show name>"


def test_remove_several_matches_waits_for_a_choice(repo):
    bear = repo.add_tracked_show(
        CHAT, tmdb_id=1, title="The Bear", first_air_year=2022, baseline_seasons=[]
    )
    repo.add_tracked_show(
        CHAT, tmdb_id=2, title="The Pitt", first_air_year=2025, baseline_seasons=[]
    )

    outgoing = remove_show(CHAT, "the", repo=repo, now=NOW)

    assert outgoing.text == "Several shows match. Which one do you want to stop following?"
    assert len(repo.list_tracked_shows(CHAT)) == 2
    confirmed = handle_callback(
        CHAT, f"rm:{bear.id}", tmdb=FakeTmdb(), repo=repo, today=TODAY, now=NOW
    )
    assert confirmed.text == "Stopped following The Bear (2022)."
    assert [show.title for show in repo.list_tracked_shows(CHAT)] == ["The Pitt"]


def test_remove_callback_rejects_an_add_payload_id(repo):
    tmdb = FakeTmdb()
    tmdb.results = [ShowSearchResult(5, "Severance", 2022)]
    add_show(CHAT, "Severance", tmdb=tmdb, repo=repo, now=NOW)

    outgoing = handle_callback(CHAT, "rm:5", tmdb=tmdb, repo=repo, today=TODAY, now=NOW)

    assert outgoing.text == CHOICE_INVALID


def test_not_found_clears_a_previous_choice(repo):
    tmdb = FakeTmdb()
    tmdb.results = [ShowSearchResult(5, "Severance", 2022)]
    add_show(CHAT, "Severance", tmdb=tmdb, repo=repo, now=NOW)
    tmdb.results = []

    add_show(CHAT, "missing", tmdb=tmdb, repo=repo, now=NOW)

    assert repo.get_pending_choice(CHAT, NOW) is None


def test_command_text_joins_arguments():
    from tvtracker.bot.handlers import _command_text

    assert _command_text(SimpleNamespace(args=["Game", "of", "Thrones"])) == "Game of Thrones"
    assert _command_text(SimpleNamespace(args=None)) == ""
    assert _command_text(SimpleNamespace(args=[])) == ""


def test_handlers_are_registered(tmp_path):
    config = load_config(
        {
            "TELEGRAM_BOT_TOKEN": "123456:" + ("A" * 35),
            "TMDB_API_KEY": "key",
            "DATABASE_PATH": str(tmp_path / "bot.sqlite"),
        }
    )
    application = Application.builder().token(config.telegram_bot_token).build()
    register_handlers(
        application,
        repo=Repository(config.database_path),
        tmdb=FakeTmdb(),
        config=config,
    )

    assert len(application.handlers[0]) == 7
