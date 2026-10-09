import argparse
import asyncio
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .client import WarEraClient
from .domain import RankingError, WeeklyRanking
from .service import RankingService


def export(ranking: WeeklyRanking, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"italy-{ranking.week_start.date()}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(ranking.model_dump_json(indent=2) + "\n")
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


async def run(api_key: str, directory: Path) -> tuple[WeeklyRanking, Path, int]:
    if not api_key.strip():
        raise RankingError("Configurare WARERA_API_KEY prima di eseguire il job")
    instant = datetime.now(UTC)
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "warera-rankings/0.1"}) as http:
        client = WarEraClient(http, api_key)
        async with asyncio.timeout(240):
            ranking = await RankingService(client).calculate(instant)
        return ranking, export(ranking, directory), client.request_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Top 50 donatori Italia della settimana UTC conclusa"
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    try:
        ranking, path, requests = asyncio.run(
            run(os.environ.get("WARERA_API_KEY", ""), args.output_dir)
        )
    except (RankingError, TimeoutError, OSError) as error:
        parser.exit(1, f"Errore: {str(error) or type(error).__name__}\n")
    print(
        f"{path}: {ranking.donation_count} donazioni, "
        f"{ranking.donor_count} donatori, {requests} HTTP"
    )
    if ranking.coverage == "history_unverified":
        print("Copertura dello storico non verificata: risultato provvisorio")
