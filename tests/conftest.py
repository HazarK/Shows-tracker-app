import pytest

from tvtracker.db.repository import Repository


@pytest.fixture
def repo(tmp_path):
    return Repository(tmp_path / "data" / "test.sqlite")
