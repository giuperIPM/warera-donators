import asyncio
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from .domain import ITALY_ID, Donation, DonationPage, Profile, RankingError

BASE_URL = "https://api2.warera.io/trpc/"


def money(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Importo non valido")
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("Importo non valido")
    return result


def unwrap(payload: Any) -> Any:
    try:
        return payload["result"]["data"]
    except (KeyError, TypeError) as error:
        raise RankingError("Risposta WarEra non valida") from error


class WarEraClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str):
        self.http = http
        self.headers = {"X-API-Key": api_key}
        self.delay = 0.0

    async def _get(self, procedure: str, inputs: dict, batch: bool = False) -> Any:
        params = {"input": json.dumps(inputs, separators=(",", ":"))}
        if batch:
            params["batch"] = "1"
        for attempt in range(3):
            await asyncio.sleep(self.delay)
            try:
                response = await self.http.get(
                    BASE_URL + procedure, params=params, headers=self.headers
                )
            except httpx.TransportError:
                if attempt == 2:
                    raise RankingError("WarEra non raggiungibile") from None
                self.delay = 2**attempt
                continue
            self.delay = self._quota_delay(response)
            if response.status_code == 429 or response.status_code >= 500:
                self.delay = max(self.delay, 2**attempt)
                continue
            if response.is_error:
                raise RankingError(f"WarEra ha restituito HTTP {response.status_code}")
            try:
                return json.loads(response.text, parse_float=Decimal)
            except (ValueError, InvalidOperation):
                raise RankingError("Risposta JSON WarEra non valida") from None
        raise RankingError("WarEra non disponibile dopo i tentativi consentiti")

    @staticmethod
    def _quota_delay(response: httpx.Response) -> float:
        try:
            if response.status_code == 429:
                return max(
                    0,
                    float(response.headers.get("Retry-After", "0")),
                    float(response.headers.get("ratelimit-reset", "60")),
                )
            if response.headers.get("ratelimit-remaining") == "0":
                return max(0, float(response.headers.get("ratelimit-reset", "60")))
        except ValueError:
            return 60
        return 0

    async def donation_page(self, cursor: str | None) -> DonationPage:
        inputs = {"countryId": ITALY_ID, "transactionType": "donation", "limit": 100}
        if cursor is not None:
            inputs["cursor"] = cursor
        data = unwrap(await self._get("transaction.getPaginatedTransactions", inputs))
        try:
            items = data["items"]
            next_cursor = data.get("nextCursor")
            if not isinstance(items, list) or (
                next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor)
            ):
                raise ValueError
            if data.get("hasMore") and next_cursor is None:
                raise ValueError
            donations = [self._donation(item) for item in items]
            return DonationPage(donations, next_cursor)
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise RankingError("Formato delle donazioni WarEra non valido") from None

    @staticmethod
    def _donation(item: dict) -> Donation:
        if item["transactionType"] != "donation":
            raise ValueError
        timestamp = item["createdAt"]
        if not isinstance(timestamp, str):
            raise ValueError
        created_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        player = item.get("buyerId") or item.get("userId")
        country = item.get("sellerCountryId") or item.get("countryId")
        if (item.get("buyerId") and item.get("userId") and item["buyerId"] != item["userId"]) or (
            item.get("sellerCountryId")
            and item.get("countryId")
            and item["sellerCountryId"] != item["countryId"]
        ):
            raise ValueError
        if created_at.tzinfo is None or not all(
            isinstance(value, str) and value for value in (item["_id"], player, country)
        ):
            raise ValueError
        return Donation(item["_id"], player, country, money(item["money"]), created_at)

    async def profiles(self, player_ids: list[str]) -> dict[str, Profile]:
        if not player_ids:
            return {}
        if len(player_ids) > 50:
            raise ValueError("Un batch può contenere al massimo 50 player")
        inputs = {str(index): {"userId": player} for index, player in enumerate(player_ids)}
        procedure = ",".join(["user.getUserById"] * len(player_ids))
        payload = await self._get(procedure, inputs, batch=True)
        if not isinstance(payload, list) or len(payload) != len(player_ids):
            raise RankingError("Risposta batch WarEra non valida")
        profiles = {}
        for player, result in zip(player_ids, payload, strict=True):
            if isinstance(result, dict) and "error" in result:
                continue
            try:
                data = unwrap(result)
                if data["_id"] != player or not isinstance(data["username"], str):
                    raise ValueError
                stats = data.get("stats") or {}
                if not isinstance(stats, dict):
                    raise ValueError
                wealth = stats.get("wealth") or {}
                if not isinstance(wealth, dict):
                    raise ValueError
                total = money(wealth["total"]) if wealth.get("total") is not None else None
                companies = (
                    money(wealth["companies"]) if wealth.get("companies") is not None else None
                )
                profiles[player] = Profile(player, data["username"], total, companies)
            except (KeyError, TypeError, ValueError, InvalidOperation, RankingError):
                continue
        return profiles
