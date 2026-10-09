from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from warera_rankings.config import QuitConfig, load_config
from warera_rankings.domain import ITALY_ID, Activity, Donation, Profile, RankingError, Week
from warera_rankings.quit_detection import (
    ActivitySnapshot,
    assess_quit,
    concentration,
    load_snapshot,
    save_snapshot,
)

WEEK = Week.previous(datetime(2026, 10, 5, tzinfo=UTC))
CONFIG = QuitConfig(enabled=True)


def donation(index, amount=100, minutes=0):
    return Donation(
        str(index),
        "a",
        ITALY_ID,
        Decimal(amount),
        WEEK.end - timedelta(hours=1) + timedelta(minutes=minutes),
    )


def profile(**activity):
    return Profile(
        "a",
        "Alice",
        Decimal("10050"),
        Decimal("10000"),
        activity=Activity(**activity),
    )


def assess(player, donations=None, previous=None, observed_at=WEEK.end, config=CONFIG):
    return assess_quit(
        player,
        donations or [donation(1), donation(2, minutes=1)],
        WEEK,
        observed_at,
        previous,
        config,
    )


def test_liquidation_exceeds_residual_wealth_and_triggers_four_signals():
    result = assess(profile(money=0, equipment_value=0, last_work_at=WEEK.end - timedelta(hours=2)))
    assert result.suspected
    assert result.signals == [
        "low_money",
        "low_equipment",
        "concentrated_donations",
        "donations_exceed_wealth",
    ]
    assert result.unknown_signals == ["low_missions"]
    assert result.weekly_works is None


def test_missing_values_are_unknown_not_zero_and_do_not_trigger_quit():
    result = assess(profile())
    assert not result.suspected
    assert set(result.unknown_signals) == {"low_work", "low_missions", "low_money", "low_equipment"}


def test_high_donation_ratio_alone_does_not_exclude_player():
    result = assess(profile(money=50, equipment_value=1000))
    assert "donations_exceed_wealth" in result.signals
    assert not result.suspected


def test_depleted_assets_without_donation_exceeding_wealth_do_not_trigger_quit():
    player = Profile(
        "a",
        "Alice",
        Decimal("2000"),
        Decimal("500"),
        activity=Activity(money=0, equipment_value=0, last_work_at=WEEK.start),
    )
    result = assess(player)
    assert len(result.signals) >= 4
    assert not result.suspected


def test_minimum_signal_threshold_is_configurable():
    player = profile(money=0, equipment_value=0)
    assert assess(player).suspected
    assert not assess(player, config=QuitConfig(enabled=True, minimum_signals=5)).suspected


def test_concentration_uses_amount_and_a_sliding_window_not_transaction_count():
    donations = [donation(1, 1), donation(2, 1, 1), donation(3, 98, 20)]
    assert concentration(donations, 10) == Decimal("0.02")
    assert concentration([donation(1)], 10) == 0
    assert concentration([], 10) == 0
    assert concentration([donation(1, 0), donation(2, 0)], 10) == 0
    assert concentration([donation(1, 80), donation(2, 20, 10)], 10) == 1


def test_weekly_counts_are_deltas_between_boundary_snapshots():
    previous = ActivitySnapshot(
        observed_at=WEEK.start,
        players={"a": Activity(works_count=1000, missions_count=1000)},
    )
    result = assess(profile(works_count=1005, missions_count=1002), previous=previous)
    assert result.weekly_works == 5
    assert result.weekly_missions == 2
    assert {"low_work", "low_missions"}.issubset(result.signals)


@pytest.mark.parametrize("late_baseline,late_current", [(True, False), (False, True)])
def test_late_execution_cannot_claim_weekly_activity_counts(late_baseline, late_current):
    previous = ActivitySnapshot(
        observed_at=WEEK.start + timedelta(days=1) if late_baseline else WEEK.start,
        players={"a": Activity(works_count=1000, missions_count=1000)},
    )
    observed = WEEK.end + timedelta(days=1) if late_current else WEEK.end
    result = assess(
        profile(works_count=1001, missions_count=1001), previous=previous, observed_at=observed
    )
    assert result.weekly_works is None
    assert result.weekly_missions is None
    assert "low_work" in result.unknown_signals


def test_counter_reset_is_unknown_and_recent_activity_is_not_inactivity():
    previous = ActivitySnapshot(
        observed_at=WEEK.start,
        players={"a": Activity(works_count=1000, missions_count=1000)},
    )
    result = assess(
        profile(works_count=1, missions_count=1, last_work_at=WEEK.end, last_mission_at=WEEK.end),
        previous=previous,
    )
    assert result.weekly_works is None
    assert result.weekly_missions is None
    assert "low_work" not in result.signals
    assert "low_missions" not in result.signals


def test_first_run_uses_last_activity_dates_without_waiting_seven_days():
    result = assess(profile(last_work_at=WEEK.start, last_mission_at=WEEK.start))
    assert {"low_work", "low_missions"}.issubset(result.signals)


def test_snapshot_keeps_first_observation_and_round_trips(tmp_path):
    target = tmp_path / "activity.json"
    assert load_snapshot(target) is None
    initial = ActivitySnapshot(observed_at=WEEK.end, players={"a": Activity(works_count=100)})
    save_snapshot(target, initial)
    save_snapshot(target, ActivitySnapshot(observed_at=WEEK.end + timedelta(days=1), players={}))
    assert load_snapshot(target) == initial


def test_invalid_snapshot_fails_explicitly(tmp_path):
    target = tmp_path / "activity.json"
    target.write_text('{"observed_at":"2026-10-05T00:00:00","players":{}}')
    with pytest.raises(RankingError, match="Snapshot"):
        load_snapshot(target)


def test_config_switch_and_threshold_validation(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text("[quit_detection]\nenabled = false\nmax_money = 25\n")
    config = load_config(target)
    assert not config.enabled
    assert config.max_money == 25
    target.write_text("[quit_detection]\nconcentration_share = 1.5\n")
    with pytest.raises(RankingError, match="Configurazione"):
        load_config(target)
