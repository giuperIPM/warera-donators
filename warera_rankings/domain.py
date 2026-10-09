from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, Field, model_serializer

ITALY_ID = "6813b6d446e731854c7ac7a2"
MAX_CANDIDATES = 50
TOP_PLAYERS = 10


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


class Activity(BaseModel):
    last_work_at: AwareDatetime | None = None
    last_mission_at: AwareDatetime | None = None
    works_count: int | None = Field(default=None, ge=0)
    missions_count: int | None = Field(default=None, ge=0)
    money: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    equipment_value: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)


@dataclass(frozen=True)
class Profile:
    id: str
    username: str
    wealth_total: Decimal | None
    company_value: Decimal | None
    avatar_url: str | None = None
    level: int | None = None
    activity: Activity | None = None


class QuitAssessment(BaseModel):
    suspected: bool
    signals: list[str]
    unknown_signals: list[str]
    weekly_works: int | None
    weekly_missions: int | None
    concentration_share: Decimal


class QuitExclusion(BaseModel):
    player_id: str
    username: str
    assessment: QuitAssessment


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
    candidate_count: int
    donation_count: int
    donated_total: Decimal
    rows: list[RankingRow]
    quit_exclusions: list[QuitExclusion] | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        result = handler(self)
        if self.quit_exclusions is None:
            result.pop("quit_exclusions", None)
        return result
