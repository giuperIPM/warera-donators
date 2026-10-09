import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .domain import WeeklyRanking


class RankingStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS rankings "
                "(week_start TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, ranking: WeeklyRanking) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO rankings VALUES (?, ?) "
                "ON CONFLICT(week_start) DO UPDATE SET payload = excluded.payload",
                (ranking.week_start.isoformat(), ranking.model_dump_json()),
            )

    def latest(self) -> WeeklyRanking | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM rankings ORDER BY week_start DESC LIMIT 1"
            ).fetchone()
        return WeeklyRanking.model_validate_json(row[0]) if row else None
