from collections import defaultdict
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from .config import QuitConfig
from .domain import (
    ITALY_ID,
    MAX_CANDIDATES,
    TOP_PLAYERS,
    Donation,
    DonationPage,
    Profile,
    QuitExclusion,
    RankingError,
    RankingRow,
    Week,
    WeeklyRanking,
)
from .quit_detection import ActivitySnapshot, assess_quit


class WarEraGateway(Protocol):
    async def donation_page(self, cursor: str | None) -> DonationPage: ...

    async def profiles(self, player_ids: list[str]) -> dict[str, Profile]: ...


class RankingService:
    def __init__(
        self,
        gateway: WarEraGateway,
        max_pages: int = 200,
        quit_config: QuitConfig | None = None,
        previous_activity: ActivitySnapshot | None = None,
    ):
        self.gateway = gateway
        self.max_pages = max_pages
        self.quit_config = quit_config or QuitConfig()
        self.previous_activity = previous_activity
        self.activity_snapshot: ActivitySnapshot | None = None

    async def calculate(self, instant: datetime) -> WeeklyRanking:
        week = Week.previous(instant)
        totals: dict[str, Decimal] = defaultdict(Decimal)
        counts: dict[str, int] = defaultdict(int)
        donations: dict[str, list[Donation]] = defaultdict(list)
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
                elif donation.created_at < week.end and donation.country_id == ITALY_ID:
                    totals[donation.player_id] += donation.amount
                    counts[donation.player_id] += 1
                    if self.quit_config.enabled:
                        donations[donation.player_id].append(donation)
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

        player_ids = sorted(totals, key=lambda player: (-totals[player], player))[:MAX_CANDIDATES]
        wealth_observed_at = datetime.now(UTC)
        profiles = await self.gateway.profiles(player_ids) if player_ids else {}
        exclusions = None
        if self.quit_config.enabled:
            self.activity_snapshot = ActivitySnapshot(
                observed_at=wealth_observed_at,
                players={
                    player: profile.activity
                    for player, profile in profiles.items()
                    if profile is not None and profile.activity is not None
                },
            )
            exclusions = []
            for player in player_ids:
                profile = profiles.get(player)
                if profile is None:
                    continue
                assessment = assess_quit(
                    profile,
                    donations[player],
                    week,
                    wealth_observed_at,
                    self.previous_activity,
                    self.quit_config,
                )
                if assessment.suspected:
                    exclusions.append(
                        QuitExclusion(
                            player_id=player, username=profile.username, assessment=assessment
                        )
                    )
        excluded_ids = {player.player_id for player in exclusions or []}
        rows = [
            self._row(index, player, totals[player], counts[player], profiles.get(player))
            for index, player in enumerate(player_ids, start=1)
        ]
        eligible = [
            row
            for row in rows
            if row.ratio_percent is not None and row.player_id not in excluded_ids
        ]
        eligible.sort(key=lambda row: (-row.ratio_percent, -row.donated, row.player_id))
        finalists = [
            row.model_copy(
                update={
                    "position": position,
                    "ratio_percent": row.ratio_percent.quantize(
                        Decimal("0.001"), rounding=ROUND_HALF_UP
                    ),
                }
            )
            for position, row in enumerate(eligible[:TOP_PLAYERS], start=1)
        ]
        return WeeklyRanking(
            week_start=week.start,
            week_end=week.end,
            donations_until=week.end,
            generated_at=datetime.now(UTC),
            wealth_observed_at=wealth_observed_at,
            coverage=coverage,
            donor_count=len(totals),
            candidate_count=len(player_ids),
            donation_count=sum(counts.values()),
            donated_total=sum(totals.values(), Decimal(0)),
            rows=finalists,
            quit_exclusions=exclusions,
        )

    @staticmethod
    def _row(
        position: int, player: str, donated: Decimal, count: int, profile: Profile | None
    ) -> RankingRow:
        total = profile.wealth_total if profile else None
        companies = profile.company_value if profile else None
        available = total - companies if total is not None and companies is not None else None
        ratio = donated * 100 / available if available is not None and available > 0 else None
        return RankingRow(
            position=position,
            player_id=player,
            username=profile.username if profile else None,
            avatar_url=profile.avatar_url if profile else None,
            level=profile.level if profile else None,
            donated=donated,
            donation_count=count,
            wealth_total=total,
            company_value=companies,
            wealth_without_companies=available,
            ratio_percent=ratio,
        )
