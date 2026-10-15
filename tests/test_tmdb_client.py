import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from tvtracker.domain.seasons import Season
from tvtracker.tmdb.client import (
    ShowNotFound,
    ShowSearchResult,
    TmdbClient,
    TmdbUnavailable,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _client(handler) -> TmdbClient:
    http = httpx.Client(
        base_url="https://api.themoviedb.org/3",
        transport=httpx.MockTransport(handler),
    )
    return TmdbClient("secret-key", client=http)


def test_search_maps_fixture_and_sends_the_api_key():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = request.url.params["query"]
        seen["api_key"] = request.url.params["api_key"]
        payload = json.loads((FIXTURES / "search_severance.json").read_text())
        return httpx.Response(200, json=payload)

    results = _client(handler).search_tv("Severance")

    assert seen == {"query": "Severance", "api_key": "secret-key"}
    assert results == [
        ShowSearchResult(95396, "Severance", 2022),
        ShowSearchResult(123, "Severance: The Documentary", None),
    ]


def test_search_stops_at_the_requested_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        payload = json.loads((FIXTURES / "search_six.json").read_text())
        return httpx.Response(200, json=payload)

    results = _client(handler).search_tv("Show", limit=5)

    assert [result.tmdb_id for result in results] == [1, 2, 3, 4, 5]


def test_get_tv_maps_season_fixture():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/3/tv/95396"
        payload = json.loads((FIXTURES / "tv_severance.json").read_text())
        return httpx.Response(200, json=payload)

    details = _client(handler).get_tv(95396)

    assert details.tmdb_id == 95396
    assert details.title == "Severance"
    assert details.first_air_year == 2022
    assert details.seasons == (
        Season(0, date(2022, 3, 25)),
        Season(1, date(2022, 2, 18)),
        Season(2, date(2025, 1, 17)),
        Season(3, None),
    )


def test_get_tv_skips_invalid_season_rows_and_unparseable_dates():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "id": 7,
                "name": "Example",
                "first_air_date": None,
                "seasons": [
                    {"name": "missing number"},
                    {"season_number": 1, "air_date": "soon"},
                ],
            },
        )

    details = _client(handler).get_tv(7)

    assert details.first_air_year is None
    assert details.seasons == (Season(1, None),)


def test_get_tv_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(404, json={"status_code": 34})

    with pytest.raises(ShowNotFound):
        _client(handler).get_tv(404)


def test_http_and_network_errors_do_not_include_the_api_key():
    def unavailable(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={"status_message": "down"})

    with pytest.raises(TmdbUnavailable) as http_error:
        _client(unavailable).search_tv("Severance")
    assert "secret-key" not in str(http_error.value)

    def broken(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.ConnectError("network down")

    with pytest.raises(TmdbUnavailable) as network_error:
        _client(broken).get_tv(1)
    assert network_error.value.__cause__ is None
    assert "secret-key" not in str(network_error.value)


def test_incomplete_details_are_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"id": 1, "name": "Example"})

    with pytest.raises(TmdbUnavailable):
        _client(handler).get_tv(1)
