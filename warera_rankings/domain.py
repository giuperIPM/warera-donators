from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

ITALY_ID = "6813b6d446e731854c7ac7a2"
TOP_PLAYERS = 50
ROME = ZoneInfo("Europe/Rome")


class RankingError(Exception):
    pass


@dataclass(frozen=True)
class Week:
    start: datetime
    end: datetime

    @classmethod
    def containing(cls, instant: datetime) -> "Week":
        if instant.tzinfo is None:
            raise ValueError("Il timestamp deve includere il fuso orario")
        local = instant.astimezone(ROME)
        start = (local - timedelta(days=local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return cls(start.astimezone(UTC), (start + timedelta(days=7)).astimezone(UTC))


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


class RankingRow(BaseModel):
    position: int
    player_id: str
    username: str | None
    donated: Decimal
    donation_count: int
    wealth_total: Decimal | None
    company_value: Decimal | None
    wealth_without_companies: Decimal | None
    ratio_percent: Decimal | None
    profile_status: str


class WeeklyRanking(BaseModel):
    country: str = "it"
    timezone: str = "Europe/Rome"
    week_start: datetime
    week_end: datetime
    donations_until: datetime
    generated_at: datetime
    coverage: str
    donor_count: int
    donation_count: int
    rows: list[RankingRow]
