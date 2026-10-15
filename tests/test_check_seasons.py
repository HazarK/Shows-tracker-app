from datetime import date

from tvtracker.bot.messages import new_season_message
from tvtracker.domain.seasons import Season
from tvtracker.jobs.check_seasons import check_all
from tvtracker.tmdb.client import ShowDetails, TmdbUnavailable

from fakes import FakeNotifier, FakeTmdb

TODAY = date(2026, 10, 15)


def _track(repo, chat_id: int, tmdb_id: int, title: str, baseline: list[Season]):
    return repo.add_tracked_show(
        chat_id,
        tmdb_id=tmdb_id,
        title=title,
        first_air_year=2022,
        baseline_seasons=baseline,
    )


def test_empty_tracking_list_does_not_call_tmdb(repo):
    tmdb = FakeTmdb()
    tmdb.detail_errors[1] = TmdbUnavailable("should not be called")
    notifier = FakeNotifier()

    result = check_all(repo, tmdb, notifier, TODAY)

    assert result.checked == 0
    assert result.notified == 0
    assert result.failed == 0
    assert tmdb.lookups == []
    assert notifier.messages == []


def test_job_ignores_specials_null_dates_and_future_seasons(repo):
    _track(repo, 10, 5, "Severance", [])
    tmdb = FakeTmdb()
    tmdb.details[5] = ShowDetails(
        5,
        "Renamed on TMDB",
        2022,
        (
            Season(0, date(2022, 3, 25)),
            Season(1, date(2022, 2, 18)),
            Season(2, None),
            Season(3, date(2026, 12, 1)),
        ),
    )
    notifier = FakeNotifier()

    result = check_all(repo, tmdb, notifier, TODAY)

    assert result == result.__class__(checked=1, notified=1, failed=0)
    assert notifier.messages == [(10, new_season_message("Severance", 1))]
    assert "Renamed on TMDB" not in notifier.messages[0][1]


def test_second_run_does_not_repeat_a_notification(repo):
    _track(repo, 10, 5, "Severance", [])
    tmdb = FakeTmdb()
    tmdb.details[5] = ShowDetails(
        5,
        "Severance",
        2022,
        (Season(1, date(2022, 2, 18)), Season(2, TODAY)),
    )
    notifier = FakeNotifier()

    first = check_all(repo, tmdb, notifier, TODAY)
    second = check_all(repo, tmdb, notifier, TODAY)

    assert first.notified == 2
    assert second.notified == 0
    assert [text for _, text in notifier.messages] == [
        new_season_message("Severance", 1),
        new_season_message("Severance", 2),
    ]


def test_baseline_seasons_are_not_sent(repo):
    _track(
        repo,
        10,
        5,
        "Severance",
        [Season(1, date(2022, 2, 18)), Season(2, date(2025, 1, 17))],
    )
    tmdb = FakeTmdb()
    tmdb.details[5] = ShowDetails(
        5,
        "Severance",
        2022,
        (
            Season(1, date(2022, 2, 18)),
            Season(2, date(2025, 1, 17)),
            Season(3, TODAY),
        ),
    )
    notifier = FakeNotifier()

    result = check_all(repo, tmdb, notifier, TODAY)

    assert result.notified == 1
    assert notifier.messages == [(10, "🎬 New season available: Severance — Season 3")]


def test_failed_send_is_retried_and_later_seasons_still_go_out(repo):
    show = _track(repo, 10, 5, "Severance", [])
    tmdb = FakeTmdb()
    tmdb.details[5] = ShowDetails(
        5,
        "Severance",
        2022,
        (Season(1, date(2022, 2, 18)), Season(2, TODAY)),
    )
    notifier = FakeNotifier(fail_on_calls={1})

    first = check_all(repo, tmdb, notifier, TODAY)

    assert first.notified == 1
    assert first.failed == 1
    assert notifier.messages == [(10, new_season_message("Severance", 2))]
    assert repo.seen_season_numbers(show.id) == {2}

    retry = FakeNotifier()
    second = check_all(repo, tmdb, retry, TODAY)

    assert second.notified == 1
    assert retry.messages == [(10, new_season_message("Severance", 1))]
    third = check_all(repo, tmdb, FakeNotifier(), TODAY)
    assert third.notified == 0


def test_one_show_lookup_failure_does_not_block_the_next(repo):
    _track(repo, 10, 5, "Broken", [])
    _track(repo, 11, 6, "Fine", [])
    tmdb = FakeTmdb()
    tmdb.detail_errors[5] = TmdbUnavailable("down")
    tmdb.details[6] = ShowDetails(6, "Fine", 2020, (Season(1, date(2024, 1, 1)),))
    notifier = FakeNotifier()

    result = check_all(repo, tmdb, notifier, TODAY)

    assert result.checked == 2
    assert result.failed == 1
    assert result.notified == 1
    assert notifier.messages == [(11, new_season_message("Fine", 1))]
