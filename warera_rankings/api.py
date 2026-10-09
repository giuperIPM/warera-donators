import asyncio
import os
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Response

from .client import WarEraClient
from .domain import Week
from .service import RankingService
from .storage import RankingStore
from .worker import RankingUpdater


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = RankingStore(Path(os.environ.get("WARERA_DATABASE", "data/rankings.sqlite3")))
    app.state.updater = None
    api_key = os.environ.get("WARERA_API_KEY", "").strip()
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "warera-rankings/0.1"}) as http:
        task = None
        if api_key:
            updater = RankingUpdater(RankingService(WarEraClient(http, api_key)), app.state.store)
            app.state.updater = updater
            task = asyncio.create_task(updater.run())
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


app = FastAPI(title="WarEra Rankings", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    updater = app.state.updater
    return {
        "status": "ok",
        "automatic_updates": updater is not None,
        "last_error": updater.last_error if updater else "api_key_missing",
        "last_attempt": updater.last_attempt if updater else None,
    }


@app.get("/api/rankings/weekly")
async def weekly_ranking(response: Response) -> dict:
    ranking = app.state.store.latest()
    if ranking is None:
        raise HTTPException(503, "Classifica non ancora disponibile", headers={"Retry-After": "30"})
    now = datetime.now(UTC)
    updater = app.state.updater
    response.headers["Cache-Control"] = "no-store"
    return {
        "ranking": ranking.model_dump(mode="json"),
        "stale": ranking.donations_until < now - timedelta(minutes=30)
        or ranking.week_start != Week.containing(now).start,
        "automatic_updates": updater is not None,
        "last_error": updater.last_error if updater else "api_key_missing",
    }
