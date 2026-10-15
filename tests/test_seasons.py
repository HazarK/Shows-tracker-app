from datetime import date

from tvtracker.domain.seasons import Season, newly_released

TODAY = date(2026, 10, 15)


def test_newly_released_keeps_numbered_seasons_on_or_before_today():
    seasons = [
        Season(0, date(2022, 3, 25)),
        Season(2, TODAY),
        Season(1, date(2022, 2, 18)),
        Season(3, None),
        Season(4, date(2026, 12, 1)),
        Season(1, date(2020, 1, 1)),
    ]

    released = newly_released(seasons, TODAY)

    assert released == [
        Season(1, date(2022, 2, 18)),
        Season(2, TODAY),
    ]
