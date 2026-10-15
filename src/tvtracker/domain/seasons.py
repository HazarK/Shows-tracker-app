"""Pure rules for which seasons count as newly released."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class Season:
    season_number: int
    air_date: date | None


def newly_released(seasons: Iterable[Season], today: date) -> list[Season]:
    """Numbered seasons whose premiere date is known and is today or earlier.

    Season 0 and specials are ignored. A missing or future premiere date is ignored.
    Duplicate season numbers keep the first occurrence.
    """
    chosen: dict[int, Season] = {}
    for season in seasons:
        if season.season_number < 1 or season.air_date is None or season.air_date > today:
            continue
        chosen.setdefault(season.season_number, season)
    return [chosen[number] for number in sorted(chosen)]
