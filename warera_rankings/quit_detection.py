from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ValidationError

from .config import QuitConfig
from .domain import Activity, Donation, Profile, QuitAssessment, RankingError, Week
from .storage import write_atomic


class ActivitySnapshot(BaseModel):
    observed_at: AwareDatetime
    players: dict[str, Activity]


def load_snapshot(path: Path) -> ActivitySnapshot | None:
    try:
        return ActivitySnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except ValidationError as error:
        raise RankingError(f"Snapshot attività non valido: {path}") from error


def save_snapshot(path: Path, snapshot: ActivitySnapshot) -> None:
    # Preserve the first observation when a closed week is recalculated later.
    if not path.exists():
        write_atomic(path, snapshot.model_dump_json(indent=2) + "\n")


def concentration(donations: list[Donation], minutes: int) -> Decimal:
    ordered = sorted(donations, key=lambda donation: donation.created_at)
    total = sum((donation.amount for donation in ordered), Decimal(0))
    if total <= 0 or len(ordered) < 2:
        return Decimal(0)
    left = 0
    amount = largest = Decimal(0)
    window = timedelta(minutes=minutes)
    for right, donation in enumerate(ordered):
        amount += donation.amount
        while donation.created_at - ordered[left].created_at > window:
            amount -= ordered[left].amount
            left += 1
        if right > left:
            largest = max(largest, amount)
    return largest / total


def weekly_delta(current: int | None, previous: int | None) -> int | None:
    if current is None or previous is None or current < previous:
        return None
    return current - previous


def assess_quit(
    profile: Profile,
    donations: list[Donation],
    week: Week,
    observed_at: datetime,
    previous: ActivitySnapshot | None,
    config: QuitConfig,
) -> QuitAssessment:
    activity = profile.activity or Activity()
    baseline = None
    if (
        previous is not None
        and week.start <= previous.observed_at <= week.start + timedelta(hours=1)
        and week.end <= observed_at <= week.end + timedelta(hours=1)
    ):
        baseline = previous.players.get(profile.id)
    works = weekly_delta(activity.works_count, baseline.works_count) if baseline else None
    missions = weekly_delta(activity.missions_count, baseline.missions_count) if baseline else None
    cutoff = week.end - timedelta(days=config.inactive_days)
    share = concentration(donations, config.concentration_minutes)
    donated = sum((donation.amount for donation in donations), Decimal(0))
    wealth = (
        profile.wealth_total - profile.company_value
        if profile.wealth_total is not None and profile.company_value is not None
        else None
    )
    checks = {
        "low_work": works <= config.max_weekly_works
        if works is not None
        else (activity.last_work_at < cutoff if activity.last_work_at is not None else None),
        "low_missions": missions <= config.max_weekly_missions
        if missions is not None
        else (activity.last_mission_at < cutoff if activity.last_mission_at is not None else None),
        "low_money": activity.money <= config.max_money if activity.money is not None else None,
        "low_equipment": activity.equipment_value <= config.max_equipment_value
        if activity.equipment_value is not None
        else None,
        "low_companies": profile.company_value <= config.max_company_value
        if profile.company_value is not None
        else None,
        "concentrated_donations": share >= config.concentration_share,
        "donations_exceed_wealth": donated > wealth if wealth is not None and wealth >= 0 else None,
    }
    signals = [name for name, matches in checks.items() if matches is True]
    depleted_assets = {"low_money", "low_equipment", "low_companies"}.intersection(signals)
    return QuitAssessment(
        suspected=(
            "donations_exceed_wealth" in signals
            and len(depleted_assets) >= 2
            and len(signals) >= config.minimum_signals
        ),
        signals=signals,
        unknown_signals=[name for name, matches in checks.items() if matches is None],
        weekly_works=works,
        weekly_missions=missions,
        concentration_share=share,
    )
