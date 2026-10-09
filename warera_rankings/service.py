from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from .domain import (
    ITALY_ID,
    TOP_PLAYERS,
    DonationPage,
    Profile,
    RankingError,
    RankingRow,
    Week,
    WeeklyRanking,
)


class WarEraGateway(Protocol):
    async def donation_page(self, cursor: str | None) -> DonationPage: ...

    async def profiles(self, player_ids: list[str]) -> dict[str, Profile]: ...


class RankingService:
    def __init__(self, gateway: WarEraGateway, max_pages: int = 200):
        self.gateway = gateway
        self.max_pages = max_pages

    async def calculate(self, instant: datetime) -> WeeklyRanking:
        week = Week.containing(instant)
        totals: dict[str, Decimal] = defaultdict(Decimal)
        counts: dict[str, int] = defaultdict(int)
        seen: set[str] = set()
        cursors: set[str] = set()
        cursor = None
        previous_date = None

        for _ in range(self.max_pages):
            page = await self.gateway.donation_page(cursor)
            reached_start = False
            for donation in page.donations:
                if donation.id in seen:
                    continue
                seen.add(donation.id)
                if previous_date is not None and donation.created_at > previous_date:
                    raise RankingError("Donazioni non ordinate per data decrescente")
                previous_date = donation.created_at
                if donation.created_at < week.start:
                    reached_start = True
                elif donation.created_at < instant and donation.country_id == ITALY_ID:
                    totals[donation.player_id] += donation.amount
                    counts[donation.player_id] += 1
            if reached_start:
                coverage = "week_boundary_reached"
                break
            if page.cursor is None:
                coverage = "history_unverified"
                break
            if not page.donations or page.cursor in cursors:
                raise RankingError("Paginazione delle donazioni non valida")
            cursors.add(page.cursor)
            cursor = page.cursor
        else:
            raise RankingError("Limite di pagine raggiunto prima di completare la scansione")

        player_ids = sorted(totals, key=lambda player: (-totals[player], player))[:TOP_PLAYERS]
        profiles = await self.gateway.profiles(player_ids) if player_ids else {}
        rows = [
            self._row(index, player, totals[player], counts[player], profiles.get(player))
            for index, player in enumerate(player_ids, start=1)
        ]
        return WeeklyRanking(
            week_start=week.start,
            week_end=week.end,
            donations_until=instant,
            generated_at=datetime.now(UTC),
            coverage=coverage,
            donor_count=len(totals),
            donation_count=sum(counts.values()),
            rows=rows,
        )

    @staticmethod
    def _row(
        position: int, player: str, donated: Decimal, count: int, profile: Profile | None
    ) -> RankingRow:
        total = profile.wealth_total if profile else None
        companies = profile.company_value if profile else None
        available = total - companies if total is not None and companies is not None else None
        ratio = donated * 100 / available if available is not None and available > 0 else None
        if profile is None:
            status = "unavailable"
        elif available is None:
            status = "wealth_missing"
        elif available <= 0:
            status = "non_positive_wealth"
        else:
            status = "ok"
        return RankingRow(
            position=position,
            player_id=player,
            username=profile.username if profile else None,
            donated=donated,
            donation_count=count,
            wealth_total=total,
            company_value=companies,
            wealth_without_companies=available,
            ratio_percent=ratio,
            profile_status=status,
        )
