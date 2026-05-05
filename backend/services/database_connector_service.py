from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url


@dataclass
class DatabaseConnectorConfig:
    url: str
    label: str = "hanna"
    pool_pre_ping: bool = True
    echo: bool = False


@dataclass
class DatabaseConnectionDetails:
    host: str
    port: int
    database: str
    username: str
    password: str
    db_schema: str | None = None
    sslmode: str | None = None
    label: str = "hanna"

    def to_url(self) -> str:
        url_str = f"postgresql+psycopg2://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        
        query_params = []
        if self.db_schema:
            query_params.append(f"options=-csearch_path%3D{self.db_schema}")
        if self.sslmode:
            query_params.append(f"sslmode={self.sslmode}")
        
        if query_params:
            url_str += "?" + "&".join(query_params)
        
        return url_str


class DatabaseConnectorService:
    """
    Basic PostgreSQL connector skeleton for external data source integrations.
    """

    def __init__(self, config: DatabaseConnectorConfig) -> None:
        self.config = config
        self._engine: Engine | None = None

    @classmethod
    def from_details(cls, details: DatabaseConnectionDetails) -> "DatabaseConnectorService":
        return cls(DatabaseConnectorConfig(url=details.to_url(), label=details.label))

    @staticmethod
    def _validate_read_only_sql(sql: str) -> str:
        statement = (sql or "").strip()
        if not statement:
            raise ValueError("SQL ifadesi boş olamaz.")

        compact = statement.rstrip(";").strip()
        lowered = compact.lower()
        if not lowered.startswith(("select", "with")):
            raise ValueError("Sadece SELECT veya WITH ile başlayan salt-okunur sorgular izinlidir.")
        if ";" in compact:
            raise ValueError("Tek bir salt-okunur sorgu gönderin; çoklu ifade desteklenmiyor.")
        return compact

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
        url = make_url(self.config.url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "ok": True,
            "label": self.config.label,
            "driver": url.drivername,
            "host": url.host,
            "port": url.port,
            "database": url.database,
        }

    def masked_connection(self) -> dict[str, Any]:
        url = make_url(self.config.url)
        return {
            "label": self.config.label,
            "driver": url.drivername,
            "host": url.host,
            "port": url.port,
            "database": url.database,
            "schema": url.query.get("options", "") if url.query else None,
        }

    def list_tables(self) -> list[dict[str, Any]]:
        engine = self.get_engine()
        sql = text(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
            """
        )
        with engine.connect() as connection:
            result = connection.execute(sql)
            return [dict(row._mapping) for row in result]

    def preview_table(self, table_name: str, limit: int = 50) -> list[dict[str, Any]]:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name or ""):
            raise ValueError("Geçersiz tablo adı.")
        limit = max(1, min(int(limit), 500))
        engine = self.get_engine()
        sql = text(f'SELECT * FROM "{table_name}" LIMIT :limit')
        with engine.connect() as connection:
            result = connection.execute(sql, {"limit": limit})
            return [dict(row._mapping) for row in result]

    def fetch_rows(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        statement = self._validate_read_only_sql(sql)
        engine = self.get_engine()
        with engine.connect() as connection:
            result = connection.execute(text(statement), params or {})
            return [dict(row._mapping) for row in result]
