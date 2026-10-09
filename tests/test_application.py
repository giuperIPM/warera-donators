import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from warera_rankings.api import app
from warera_rankings.domain import RankingError, Week, WeeklyRanking
from warera_rankings.storage import RankingStore
from warera_rankings.worker import RankingUpdater


def snapshot(instant=None):
    instant = instant or datetime.now(UTC)
    week = Week.containing(instant)
    return WeeklyRanking(
        week_start=week.start,
        week_end=week.end,
        donations_until=instant,
        generated_at=instant,
        coverage="week_boundary_reached",
        donor_count=0,
        donation_count=0,
        rows=[],
    )


def test_store_survives_reopening_and_replaces_same_week(tmp_path):
    path = tmp_path / "rankings.sqlite3"
    first = snapshot()
    store = RankingStore(path)
    store.save(first)
    assert RankingStore(path).latest() == first
    second = first.model_copy(update={"donor_count": 1})
    store.save(second)
    assert store.latest() == second


def test_failed_refresh_keeps_previous_ranking(tmp_path):
    class FailingService:
        async def calculate(self, instant):
            raise RankingError("unavailable")

    store = RankingStore(tmp_path / "rankings.sqlite3")
    previous = snapshot()
    store.save(previous)
    updater = RankingUpdater(FailingService(), store)
    asyncio.run(updater.refresh())
    assert store.latest() == previous
    assert updater.last_error == "RankingError"


def test_successful_refresh_saves_and_clears_error(tmp_path):
    ranking = snapshot()

    class Service:
        async def calculate(self, instant):
            return ranking

    store = RankingStore(tmp_path / "rankings.sqlite3")
    updater = RankingUpdater(Service(), store)
    updater.last_error = "RankingError"
    asyncio.run(updater.refresh())
    assert store.latest() == ranking
    assert updater.last_error is None


def test_api_reads_snapshot_without_api_key_or_upstream_calls(tmp_path, monkeypatch):
    monkeypatch.delenv("WARERA_API_KEY", raising=False)
    monkeypatch.setenv("WARERA_DATABASE", str(tmp_path / "rankings.sqlite3"))

    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/api/rankings/weekly")).status_code == 503
                assert (await client.get("/health")).json()["automatic_updates"] is False
                app.state.store.save(snapshot(datetime.now(UTC) - timedelta(hours=1)))
                response = await client.get("/api/rankings/weekly")
                assert response.status_code == 200
                assert response.json()["stale"] is True
                assert response.json()["ranking"]["country"] == "it"
                assert response.headers["Cache-Control"] == "no-store"

    asyncio.run(run())


def test_worker_updates_periodically_and_can_be_cancelled(tmp_path, monkeypatch):
    instants = []

    class Service:
        async def calculate(self, instant):
            instants.append(instant)
            return snapshot(instant)

    async def sleep(seconds):
        assert seconds == 900
        if len(instants) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("warera_rankings.worker.asyncio.sleep", sleep)
    updater = RankingUpdater(Service(), RankingStore(tmp_path / "rankings.sqlite3"))
    try:
        asyncio.run(updater.run())
    except asyncio.CancelledError:
        pass
    assert len(instants) == 2
