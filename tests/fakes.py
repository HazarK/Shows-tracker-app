from tvtracker.tmdb.client import ShowDetails, ShowSearchResult


class FakeTmdb:
    def __init__(self) -> None:
        self.results: list[ShowSearchResult] = []
        self.details: dict[int, ShowDetails] = {}
        self.search_error: Exception | None = None
        self.detail_errors: dict[int, Exception] = {}
        self.searches: list[tuple[str, int]] = []
        self.lookups: list[int] = []

    def search_tv(self, query: str, limit: int = 5) -> list[ShowSearchResult]:
        self.searches.append((query, limit))
        if self.search_error is not None:
            raise self.search_error
        return self.results[:limit]

    def get_tv(self, tmdb_id: int) -> ShowDetails:
        self.lookups.append(tmdb_id)
        error = self.detail_errors.get(tmdb_id)
        if error is not None:
            raise error
        return self.details[tmdb_id]


class FakeNotifier:
    def __init__(self, fail_on_calls: set[int] | None = None) -> None:
        self.messages: list[tuple[int, str]] = []
        self.fail_on_calls = fail_on_calls or set()
        self.calls = 0

    def send(self, chat_id: int, text: str) -> None:
        self.calls += 1
        if self.calls in self.fail_on_calls:
            raise RuntimeError("telegram down")
        self.messages.append((chat_id, text))
