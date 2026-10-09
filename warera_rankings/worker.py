import asyncio
import logging
import sqlite3
from datetime import UTC, datetime

from .domain import RankingError
from .service import RankingService
from .storage import RankingStore

logger = logging.getLogger(__name__)


class RankingUpdater:
    def __init__(self, service: RankingService, store: RankingStore):
        self.service = service
        self.store = store
        self.last_error: str | None = None
        self.last_attempt: datetime | None = None

    async def refresh(self) -> None:
        self.last_attempt = datetime.now(UTC)
        try:
            async with asyncio.timeout(240):
                ranking = await self.service.calculate(self.last_attempt)
                self.store.save(ranking)
        except (RankingError, TimeoutError, OSError, sqlite3.Error) as error:
            self.last_error = type(error).__name__
            logger.warning("Aggiornamento classifica fallito: %s", self.last_error)
        else:
            self.last_error = None

    async def run(self) -> None:
        while True:
            await self.refresh()
            await asyncio.sleep(900)
