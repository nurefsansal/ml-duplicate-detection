from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


@dataclass
class DatabaseConnectorConfig:
    url: str
    pool_pre_ping: bool = True
    echo: bool = False


class DatabaseConnectorService:
    """
    Basic PostgreSQL connector skeleton for external data source integrations.
    """

    def __init__(self, config: DatabaseConnectorConfig | None = None) -> None:
        default_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
        )
        self.config = config or DatabaseConnectorConfig(url=default_url)
        self._engine: Engine | None = None

    def get_engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(
                self.config.url,
                pool_pre_ping=self.config.pool_pre_ping,
                echo=self.config.echo,
            )
        return self._engine

    def healthcheck(self) -> dict[str, Any]:
        engine = self.get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"ok": True, "url": self.config.url}

    def fetch_rows(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        engine = self.get_engine()
        with engine.connect() as connection:
            result = connection.execute(text(sql), params or {})
            return [dict(row._mapping) for row in result]
