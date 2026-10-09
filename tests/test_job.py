import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from warera_rankings.domain import ITALY_ID, RankingError, Week, WeeklyRanking
from warera_rankings.job import export, run


def snapshot():
    week = Week.previous(datetime.now(UTC))
    return WeeklyRanking(
        week_start=week.start,
        week_end=week.end,
        donations_until=week.end,
        generated_at=datetime.now(UTC),
        wealth_observed_at=datetime.now(UTC),
        coverage="week_boundary_reached",
        donor_count=0,
        donation_count=0,
        donated_total="0",
        rows=[],
    )


def test_export_is_a_week_named_json_file(tmp_path):
    ranking = snapshot()
    target = export(ranking, tmp_path)
    assert target.name == f"italy-{ranking.week_start.date()}.json"
    assert WeeklyRanking.model_validate_json(target.read_text()) == ranking
    assert list(tmp_path.iterdir()) == [target]


def test_failed_export_preserves_previous_result(tmp_path, monkeypatch):
    target = export(snapshot(), tmp_path)
    previous = target.read_text()

    def fail(self, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        export(snapshot(), tmp_path)
    assert target.read_text() == previous
    assert list(tmp_path.iterdir()) == [target]


def test_missing_key_fails_before_network_and_export(tmp_path):
    directory = tmp_path / "output"
    with pytest.raises(RankingError, match="WARERA_API_KEY"):
        asyncio.run(run("", directory))
    assert not directory.exists()


def test_job_fetches_closed_week_batches_profiles_and_exports(tmp_path, monkeypatch):
    week = Week.previous(datetime.now(UTC))
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["X-API-Key"] == "test-key"
        if request.url.path.endswith("transaction.getPaginatedTransactions"):
            items = []
            for id, instant in [
                ("end", week.end),
                ("included", week.start),
                ("old", week.start - timedelta(seconds=1)),
            ]:
                items.append(
                    {
                        "_id": id,
                        "buyerId": "a",
                        "sellerCountryId": ITALY_ID,
                        "transactionType": "donation",
                        "money": 10,
                        "createdAt": instant.isoformat(),
                    }
                )
            return httpx.Response(
                200, json={"result": {"data": {"items": items, "nextCursor": None}}}
            )
        assert request.url.params["batch"] == "1"
        return httpx.Response(
            200,
            json=[
                {
                    "result": {
                        "data": {
                            "_id": "a",
                            "username": "Alice",
                            "avatarUrl": "https://media.warera.io/avatars/alice.jpg",
                            "leveling": {"level": 26},
                            "stats": {"wealth": {"total": 100, "companies": 50}},
                        }
                    }
                }
            ],
        )

    client_type = httpx.AsyncClient

    def client(**kwargs):
        return client_type(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("warera_rankings.job.httpx.AsyncClient", client)
    ranking, path, calls = asyncio.run(run("test-key", tmp_path))
    data = json.loads(path.read_text())
    assert calls == len(requests) == 2
    assert ranking.donation_count == 1
    assert data["rows"][0]["donated"] == "10"
    assert data["rows"][0]["ratio_percent"] == "20"
    assert data["rows"][0]["avatar_url"] == "https://media.warera.io/avatars/alice.jpg"
    assert data["rows"][0]["level"] == 26
    assert data["coverage"] == "week_boundary_reached"
    assert "test-key" not in path.read_text()
