from tvtracker.config import load_config
from tvtracker.db.repository import Repository
from tvtracker.jobs.schedule import start_scheduler

from fakes import FakeNotifier, FakeTmdb


def test_scheduler_registers_a_daily_job(tmp_path):
    config = load_config(
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TMDB_API_KEY": "key",
            "DATABASE_PATH": str(tmp_path / "bot.sqlite"),
            "CHECK_HOUR": "9",
            "CHECK_TIMEZONE": "UTC",
        }
    )
    scheduler = start_scheduler(
        config,
        Repository(config.database_path),
        FakeTmdb(),
        FakeNotifier(),
    )
    try:
        job = scheduler.get_job("check_seasons")
        assert job is not None
        description = str(job.trigger)
        assert "hour='9'" in description
        assert "minute='0'" in description
        assert job.coalesce is True
        assert job.misfire_grace_time == 6 * 60 * 60
    finally:
        scheduler.shutdown(wait=False)
