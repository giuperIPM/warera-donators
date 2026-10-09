import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from warera_rankings.domain import ITALY_ID, Donation, DonationPage, Profile, RankingError, Week
from warera_rankings.service import RankingService

NOW = datetime(2026, 10, 9, 10, tzinfo=UTC)


def donation(id, player="a", amount="10", at=None, country=ITALY_ID):
    return Donation(id, player, country, Decimal(amount), at or NOW.replace(day=1))


class Gateway:
    def __init__(self, pages, profiles=None):
        self.pages = iter(pages)
        self.data = profiles
        self.requested_players = []

    async def donation_page(self, cursor):
        return next(self.pages)

    async def profiles(self, players):
        self.requested_players = players
        if self.data is not None:
            return self.data
        return {
            player: Profile(player, player, Decimal("1000"), Decimal("0")) for player in players
        }


def calculate(gateway, max_pages=200):
    return asyncio.run(RankingService(gateway, max_pages).calculate(NOW))


def test_aggregation_deduplication_and_period_boundaries():
    start = Week.previous(NOW).start
    duplicate = donation("1", amount="0.1")
    gateway = Gateway(
        [
            DonationPage([donation("future", at=NOW), duplicate], "next"),
            DonationPage(
                [
                    duplicate,
                    donation("2", amount="0.2"),
                    donation("foreign", country="other"),
                    donation("start", at=start),
                    donation("old", at=start - timedelta(seconds=1)),
                ],
                "unused",
            ),
        ],
        {"a": Profile("a", "Alice", Decimal("100"), Decimal("50"))},
    )
    result = calculate(gateway)
    row = result.rows[0]
    assert row.donated == Decimal("10.3")
    assert row.donation_count == 3
    assert row.wealth_without_companies == 50
    assert row.ratio_percent == Decimal("20.6")
    assert result.donation_count == 3
    assert result.coverage == "week_boundary_reached"


def test_top_50_and_deterministic_ties():
    items = [donation(str(index), player=f"p{index:02}", amount=str(index)) for index in range(60)]
    items += [donation("tie", player="p60", amount="59")]
    gateway = Gateway([DonationPage(items, None)])
    result = calculate(gateway)
    assert len(result.rows) == 10
    assert result.candidate_count == 50
    assert len(gateway.requested_players) == 50
    assert gateway.requested_players[:2] == ["p59", "p60"]
    assert gateway.requested_players[-1] == "p11"
    assert result.donor_count == 61
    assert result.coverage == "history_unverified"


@pytest.mark.parametrize(
    "profile",
    [
        None,
        Profile("a", "Alice", None, Decimal("0")),
        Profile("a", "Alice", Decimal("10"), Decimal("10")),
        Profile("a", "Alice", Decimal("10"), Decimal("20")),
    ],
)
def test_non_calculable_ratios(profile):
    result = calculate(Gateway([DonationPage([donation("1")], None)], {"a": profile}))
    assert result.rows == []
    assert result.candidate_count == 1


def test_final_top_10_is_by_ratio_within_the_top_50_by_donations():
    items = [
        donation(str(index), player=f"p{index:02}", amount=str(index + 1)) for index in range(60)
    ]
    profiles = {
        f"p{index:02}": Profile(f"p{index:02}", str(index), Decimal("1000"), Decimal("0"))
        for index in range(60)
    }
    profiles["p10"] = Profile("p10", "Small wealth", Decimal("1"), Decimal("0"))
    profiles["p00"] = Profile("p00", "Outside candidates", Decimal("0.01"), Decimal("0"))
    gateway = Gateway([DonationPage(items, None)], profiles)
    result = calculate(gateway)
    assert len(result.rows) == 10
    assert result.rows[0].player_id == "p10"
    assert "p00" not in gateway.requested_players
    assert [row.position for row in result.rows] == list(range(1, 11))


def test_ratio_ordering_precedes_display_rounding():
    gateway = Gateway(
        [
            DonationPage(
                [donation("1", player="a", amount="2"), donation("2", player="b", amount="1")], None
            )
        ],
        {
            "a": Profile("a", "Alice", Decimal("200"), Decimal("0")),
            "b": Profile("b", "Bob", Decimal("99.996"), Decimal("0")),
        },
    )
    rows = calculate(gateway).rows
    assert [row.player_id for row in rows] == ["b", "a"]
    assert all(row.ratio_percent == Decimal("1.000") for row in rows)


def test_equal_ratios_are_ordered_by_donations_then_id():
    gateway = Gateway(
        [
            DonationPage(
                [
                    donation("1", player="a", amount="10"),
                    donation("2", player="b", amount="20"),
                    donation("3", player="c", amount="20"),
                ],
                None,
            )
        ],
        {
            "a": Profile("a", "Alice", Decimal("100"), Decimal("0")),
            "b": Profile("b", "Bob", Decimal("200"), Decimal("0")),
            "c": Profile("c", "Chris", Decimal("200"), Decimal("0")),
        },
    )
    assert [row.player_id for row in calculate(gateway).rows] == ["b", "c", "a"]


@pytest.mark.parametrize(
    "amount,wealth,expected",
    [
        ("1", "3", "33.333"),
        ("1", "6", "16.667"),
        ("0.012345", "1000", "0.001"),
        ("0.012355", "1000", "0.001"),
        ("0.015", "1000", "0.002"),
    ],
)
def test_ratio_is_serialized_with_three_decimal_places(amount, wealth, expected):
    gateway = Gateway(
        [DonationPage([donation("1", amount=amount)], None)],
        {"a": Profile("a", "Alice", Decimal(wealth), Decimal("0"))},
    )
    row = calculate(gateway).rows[0].model_dump(mode="json")
    assert row["ratio_percent"] == expected
    assert "profile_status" not in row


def test_no_donations_skips_profile_request():
    gateway = Gateway([DonationPage([], None)])
    result = calculate(gateway)
    assert result.rows == []
    assert result.coverage == "history_unverified"
    assert gateway.requested_players == []


@pytest.mark.parametrize(
    "pages",
    [
        [DonationPage([donation("1")], "x"), DonationPage([donation("2")], "x")],
        [DonationPage([donation("1", at=datetime(2026, 9, 30, tzinfo=UTC)), donation("2")], None)],
        [DonationPage([], "next")],
    ],
)
def test_invalid_pagination_or_order_does_not_produce_ranking(pages):
    with pytest.raises(RankingError):
        calculate(Gateway(pages))


def test_page_limit_does_not_produce_partial_ranking():
    with pytest.raises(RankingError):
        calculate(Gateway([DonationPage([donation("1")], "next")]), max_pages=1)


@pytest.mark.parametrize(
    "instant,start,end",
    [
        (
            datetime(2026, 3, 29, 12, tzinfo=UTC),
            "2026-03-16T00:00:00+00:00",
            "2026-03-23T00:00:00+00:00",
        ),
        (
            datetime(2026, 10, 25, 12, tzinfo=UTC),
            "2026-10-12T00:00:00+00:00",
            "2026-10-19T00:00:00+00:00",
        ),
        (
            datetime(2026, 10, 5, 0, tzinfo=UTC),
            "2026-09-28T00:00:00+00:00",
            "2026-10-05T00:00:00+00:00",
        ),
        (
            datetime(2026, 10, 4, 22, tzinfo=UTC),
            "2026-09-21T00:00:00+00:00",
            "2026-09-28T00:00:00+00:00",
        ),
    ],
)
def test_previous_week_is_always_a_completed_utc_week(instant, start, end):
    week = Week.previous(instant)
    assert week.start.isoformat() == start
    assert week.end.isoformat() == end
    assert week.end - week.start == timedelta(days=7)


def test_end_boundary_is_excluded():
    week = Week.previous(NOW)
    gateway = Gateway(
        [
            DonationPage(
                [
                    donation("end", at=week.end),
                    donation("last", at=week.end - timedelta(microseconds=1)),
                    donation("old", at=week.start - timedelta(microseconds=1)),
                ],
                None,
            )
        ]
    )
    result = calculate(gateway)
    assert result.donation_count == 1
    assert result.donated_total == 10
    assert result.donations_until == week.end
    assert result.timezone == "UTC"


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError):
        Week.previous(datetime(2026, 10, 5))
