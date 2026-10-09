import argparse
import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .client import WarEraClient
from .config import QuitConfig, load_config
from .domain import RankingError, Week, WeeklyRanking
from .quit_detection import load_snapshot, save_snapshot
from .service import RankingService
from .storage import write_atomic


def export(ranking: WeeklyRanking, directory: Path) -> Path:
    target = directory / f"italy-{ranking.week_start.date()}.json"
    return write_atomic(target, ranking.model_dump_json(indent=2) + "\n")


async def run(
    api_key: str, directory: Path, quit_config: QuitConfig | None = None
) -> tuple[WeeklyRanking, Path, int]:
    if not api_key.strip():
        raise RankingError("Configurare WARERA_API_KEY prima di eseguire il job")
    instant = datetime.now(UTC)
    config = quit_config or QuitConfig()
    week = Week.previous(instant)
    previous = (
        load_snapshot(directory / f"activity-{week.start.date()}.json") if config.enabled else None
    )
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "warera-rankings/0.1"}) as http:
        client = WarEraClient(http, api_key)
        async with asyncio.timeout(240):
            service = RankingService(client, quit_config=config, previous_activity=previous)
            ranking = await service.calculate(instant)
        if service.activity_snapshot is not None:
            save_snapshot(directory / f"activity-{week.end.date()}.json", service.activity_snapshot)
        return ranking, export(ranking, directory), client.request_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Top 10 per percentuale tra i 50 maggiori donatori Italia"
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--image", action="store_true", help="Genera anche il PNG della classifica")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    args = parser.parse_args()
    try:
        ranking, path, requests = asyncio.run(
            run(os.environ.get("WARERA_API_KEY", ""), args.output_dir, load_config(args.config))
        )
        if args.image:
            try:
                from .image import render_image
            except ImportError as error:
                raise RankingError(
                    "Installare le dipendenze PNG: pip install -e '.[image]'"
                ) from error
            image = asyncio.run(render_image(ranking, path.with_suffix(".png")))
            print(image)
    except (RankingError, TimeoutError, OSError) as error:
        parser.exit(1, f"Errore: {str(error) or type(error).__name__}\n")
    print(
        f"{path}: {ranking.donation_count} donazioni, "
        f"{ranking.donor_count} donatori, {requests} HTTP"
    )
    if ranking.coverage == "history_unverified":
        print("Copertura dello storico non verificata: risultato provvisorio")
    if ranking.quit_exclusions is not None:
        print(f"Possibili quit esclusi: {len(ranking.quit_exclusions)}")
