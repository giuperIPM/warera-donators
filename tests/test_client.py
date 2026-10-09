import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from warera_rankings.client import WarEraClient
from warera_rankings.domain import ITALY_ID, RankingError


def result(data):
    return {"result": {"data": data}}


def execute(handler, action):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await action(WarEraClient(http, "test-key"))

    return asyncio.run(run())


def transaction(**changes):
    return {
        "_id": "tx",
        "transactionType": "donation",
        "buyerId": "a",
        "sellerCountryId": ITALY_ID,
        "money": 0.1,
        "createdAt": "2026-10-09T08:00:00Z",
        **changes,
    }


def test_page_input_auth_cursor_and_decimal_parsing():
    def handler(request):
        assert request.headers["X-API-Key"] == "test-key"
        assert json.loads(request.url.params["input"]) == {
            "countryId": ITALY_ID,
            "transactionType": "donation",
            "limit": 100,
            "cursor": "first",
        }
        return httpx.Response(200, json=result({"items": [transaction()], "nextCursor": "second"}))

    page = execute(handler, lambda client: client.donation_page("first"))
    assert page.donations[0].amount == Decimal("0.1")
    assert page.cursor == "second"


@pytest.mark.parametrize(
    "data",
    [
        {"wrong": []},
        {"items": [], "hasMore": True},
        {"items": [transaction(money=-1)]},
        {"items": [transaction(money="NaN")]},
        {"items": [transaction(createdAt="2026-10-09T08:00:00")]},
        {"items": [transaction(buyerId=None)]},
    ],
)
def test_invalid_donation_data_fails_explicitly(data):
    with pytest.raises(RankingError):
        execute(lambda _: httpx.Response(200, json=result(data)), lambda c: c.donation_page(None))


def test_profiles_use_one_batch_and_handle_individual_errors():
    def handler(request):
        assert request.url.path.endswith("user.getUserById,user.getUserById")
        assert request.url.params["batch"] == "1"
        assert json.loads(request.url.params["input"]) == {
            "0": {"userId": "a"},
            "1": {"userId": "b"},
        }
        return httpx.Response(
            200,
            json=[
                result(
                    {
                        "_id": "a",
                        "username": "Alice",
                        "avatarUrl": "https://media.warera.io/avatars/alice.jpg",
                        "leveling": {"level": 26},
                        "stats": {
                            "wealth": {"total": 100.1, "companies": 20},
                        },
                    }
                ),
                {"error": {"message": "missing"}},
            ],
        )

    profiles = execute(handler, lambda client: client.profiles(["a", "b"]))
    assert list(profiles) == ["a"]
    assert profiles["a"].wealth_total == Decimal("100.1")
    assert profiles["a"].avatar_url == "https://media.warera.io/avatars/alice.jpg"
    assert profiles["a"].level == 26


def test_missing_optional_profile_fields_do_not_discard_wealth():
    profiles = execute(
        lambda _: httpx.Response(
            200,
            json=[
                result(
                    {
                        "_id": "a",
                        "username": "Alice",
                        "stats": {"wealth": {"total": 100, "companies": 20}},
                    }
                )
            ],
        ),
        lambda client: client.profiles(["a"]),
    )
    assert profiles["a"].wealth_total == 100
    assert profiles["a"].avatar_url is None
    assert profiles["a"].level is None


def test_wrong_profile_id_is_not_assigned_to_another_player():
    profiles = execute(
        lambda _: httpx.Response(200, json=[result({"_id": "b", "username": "Bob"})]),
        lambda client: client.profiles(["a"]),
    )
    assert profiles == {}


def test_auth_error_is_not_retried_or_exposed():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, json={"error": "sensitive token"})

    with pytest.raises(RankingError, match="HTTP 401"):
        execute(handler, lambda client: client.donation_page(None))
    assert len(calls) == 1


def test_rate_limit_waits_before_retry(monkeypatch):
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr("warera_rankings.client.asyncio.sleep", sleep)
    responses = iter(
        [
            httpx.Response(429, headers={"ratelimit-reset": "12", "Retry-After": "15"}),
            httpx.Response(200, json=result({"items": []})),
        ]
    )
    execute(lambda _: next(responses), lambda client: client.donation_page(None))
    assert waits == [0, 15]


def test_retries_are_bounded(monkeypatch):
    async def sleep(seconds):
        pass

    monkeypatch.setattr("warera_rankings.client.asyncio.sleep", sleep)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    with pytest.raises(RankingError):
        execute(handler, lambda client: client.donation_page(None))
    assert len(calls) == 3
