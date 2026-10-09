import asyncio

import httpx
import pytest

from warera_rankings.domain import RankingError
from warera_rankings.memberships import MEMBERS_URL, load_confindustria_members


def fetch(handler):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await load_confindustria_members(http)

    return asyncio.run(run())


def test_public_membership_list_uses_ids_and_deduplicates():
    def handler(request):
        assert str(request.url) == MEMBERS_URL
        assert "X-API-Key" not in request.headers
        return httpx.Response(
            200,
            json=[
                {"id": "69e60890fe61f8ad03b860ba", "name": "Giancarlo_Devasini"},
                {"id": "69d4dd1c70ab5601d0eb54d9", "name": "LordPirla"},
                {"id": "69e60890fe61f8ad03b860ba", "name": "Nome cambiato"},
            ],
        )

    assert fetch(handler) == {"69e60890fe61f8ad03b860ba", "69d4dd1c70ab5601d0eb54d9"}


def test_empty_membership_list_is_valid():
    assert fetch(lambda request: httpx.Response(200, json=[])) == frozenset()


@pytest.mark.parametrize(
    "content",
    [
        '{"members": []}',
        '["69e60890fe61f8ad03b860ba"]',
        '[{"name": "Alice"}]',
        '[{"id": "invalid"}]',
        '[{"id": 42}]',
        "{",
    ],
)
def test_invalid_public_list_fails_explicitly(content):
    with pytest.raises(RankingError, match="non valida"):
        fetch(lambda request: httpx.Response(200, text=content))


@pytest.mark.parametrize("status", [404, 429, 503])
def test_http_failure_is_reported(status):
    with pytest.raises(RankingError, match="non raggiungibile"):
        fetch(lambda request: httpx.Response(status))


def test_timeout_is_reported():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(RankingError, match="non raggiungibile"):
        fetch(handler)
