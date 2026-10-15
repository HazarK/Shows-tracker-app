"""Thin TMDB client. TMDB is the source of truth for show and season facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import httpx

from tvtracker.domain.seasons import Season

DEFAULT_BASE_URL = "https://api.themoviedb.org/3"


class TmdbUnavailable(Exception):
    """The TV database could not be reached or returned an error."""


class ShowNotFound(Exception):
    """TMDB has no TV show for this id."""


@dataclass(frozen=True)
class ShowSearchResult:
    tmdb_id: int
    title: str
    first_air_year: int | None


@dataclass(frozen=True)
class ShowDetails:
    tmdb_id: int
    title: str
    first_air_year: int | None
    seasons: tuple[Season, ...]


class ShowCatalog(Protocol):
    def search_tv(self, query: str, limit: int = 5) -> list[ShowSearchResult]: ...

    def get_tv(self, tmdb_id: int) -> ShowDetails: ...


class TmdbClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(base_url=base_url, timeout=20.0)

    def search_tv(self, query: str, limit: int = 5) -> list[ShowSearchResult]:
        try:
            payload = self._get("/search/tv", {"query": query})
        except ShowNotFound:
            raise TmdbUnavailable("TMDB search failed") from None
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise TmdbUnavailable("TMDB search response did not include results")

        shows: list[ShowSearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict) or "id" not in item or "name" not in item:
                continue
            shows.append(
                ShowSearchResult(
                    tmdb_id=int(item["id"]),
                    title=str(item["name"]),
                    first_air_year=_year(item.get("first_air_date")),
                )
            )
            if len(shows) >= limit:
                break
        return shows

    def get_tv(self, tmdb_id: int) -> ShowDetails:
        payload = self._get(f"/tv/{tmdb_id}")
        name = payload.get("name")
        raw_seasons = payload.get("seasons")
        if not isinstance(name, str) or not isinstance(raw_seasons, list):
            raise TmdbUnavailable("TMDB show details were incomplete")

        seasons: list[Season] = []
        for item in raw_seasons:
            if not isinstance(item, dict) or "season_number" not in item:
                continue
            seasons.append(
                Season(
                    season_number=int(item["season_number"]),
                    air_date=_air_date(item.get("air_date")),
                )
            )
        show_id = payload.get("id", tmdb_id)
        return ShowDetails(
            tmdb_id=int(show_id),
            title=name,
            first_air_year=_year(payload.get("first_air_date")),
            seasons=tuple(seasons),
        )

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict:
        query = {"api_key": self._api_key}
        if params:
            query.update(params)
        try:
            response = self._client.get(path, params=query)
        except httpx.HTTPError:
            raise TmdbUnavailable("TMDB request failed") from None
        if response.status_code == 404:
            raise ShowNotFound(path)
        if response.status_code >= 400:
            raise TmdbUnavailable(f"TMDB returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TmdbUnavailable("TMDB returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise TmdbUnavailable("TMDB returned an unexpected payload")
        return payload


def _year(value: object) -> int | None:
    if not isinstance(value, str) or len(value) < 4:
        return None
    year_text = value[:4]
    if not year_text.isdigit():
        return None
    return int(year_text)


def _air_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
