from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel

ITALY_ID = "6813b6d446e731854c7ac7a2"
TOP_PLAYERS = 50


class RankingError(Exception):
    pass


@dataclass(frozen=True)
class Week:
    start: datetime
    end: datetime

    @classmethod
    def previous(cls, instant: datetime) -> "Week":
        if instant.tzinfo is None:
            raise ValueError("Il timestamp deve includere il fuso orario")
        utc = instant.astimezone(UTC)
        end = (utc - timedelta(days=utc.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return cls(end - timedelta(days=7), end)


@dataclass(frozen=True)
class Donation:
    id: str
    player_id: str
    country_id: str
    amount: Decimal
    created_at: datetime


@dataclass(frozen=True)
class DonationPage:
    donations: list[Donation]
    cursor: str | None


@dataclass(frozen=True)
class Profile:
    id: str
    username: str
    wealth_total: Decimal | None
    company_value: Decimal | None
    avatar_url: str | None = None
    level: int | None = None


class RankingRow(BaseModel):
    position: int
    player_id: str
    username: str | None
    avatar_url: str | None
    level: int | None
    donated: Decimal
    donation_count: int
    wealth_total: Decimal | None
    company_value: Decimal | None
    wealth_without_companies: Decimal | None
    ratio_percent: Decimal | None


class WeeklyRanking(BaseModel):
    country: str = "it"
    timezone: str = "UTC"
    week_start: datetime
    week_end: datetime
    donations_until: datetime
    generated_at: datetime
    wealth_observed_at: datetime
    coverage: str
    donor_count: int
    donation_count: int
    donated_total: Decimal
    rows: list[RankingRow]
