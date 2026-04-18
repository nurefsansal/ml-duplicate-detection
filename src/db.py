from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEFAULT_DATABASE_URL = "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5433/ml_duplicate_db"


def get_database_url() -> str:
    """Gets DB URL from environment or falls back to local docker defaults."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_db_engine() -> Engine:
    """Creates SQLAlchemy engine for PostgreSQL."""
    return create_engine(get_database_url(), pool_pre_ping=True)


def test_connection(engine: Engine) -> tuple[bool, str]:
    """Returns a tuple of (is_connected, message)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "PostgreSQL bağlantısı başarılı."
    except Exception as exc:  # pragma: no cover - UI-facing error path
        return False, f"PostgreSQL bağlantısı başarısız: {exc}"


def ensure_tables(engine: Engine) -> None:
    """Creates application tables if they do not exist."""
    ddl = """
    CREATE TABLE IF NOT EXISTS duplicate_results (
        id BIGSERIAL PRIMARY KEY,
        session_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL,
        rules_matched INTEGER,
        left_index BIGINT,
        right_index BIGINT,
        left_name TEXT,
        right_name TEXT,
        left_city TEXT,
        right_city TEXT,
        left_phone TEXT,
        right_phone TEXT,
        left_tc TEXT,
        right_tc TEXT,
        left_email TEXT,
        right_email TEXT,
        payload JSONB
    );
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def save_duplicates(engine: Engine, duplicates_df: pd.DataFrame, session_id: str) -> int:
    """Persists duplicate candidates to PostgreSQL and returns inserted row count."""
    if duplicates_df.empty:
        return 0

    ensure_tables(engine)

    now = datetime.utcnow()
    to_store = duplicates_df.copy()

    # Keep raw row payload for future debugging/analysis.
    to_store["payload"] = to_store.apply(lambda row: row.to_json(force_ascii=False), axis=1)
    to_store["session_id"] = session_id
    to_store["created_at"] = now

    rename_map = {
        "L_Ad Soyad": "left_name",
        "R_Ad Soyad": "right_name",
        "L_Şehir": "left_city",
        "R_Şehir": "right_city",
        "L_Telefon": "left_phone",
        "R_Telefon": "right_phone",
        "L_TC": "left_tc",
        "R_TC": "right_tc",
        "L_E-mail": "left_email",
        "R_E-mail": "right_email",
    }

    to_store = to_store.rename(columns=rename_map)

    keep_cols = [
        "session_id",
        "created_at",
        "rules_matched",
        "left_index",
        "right_index",
        "left_name",
        "right_name",
        "left_city",
        "right_city",
        "left_phone",
        "right_phone",
        "left_tc",
        "right_tc",
        "left_email",
        "right_email",
        "payload",
    ]

    for col in keep_cols:
        if col not in to_store.columns:
            to_store[col] = None

    to_store = to_store[keep_cols]
    to_store.to_sql("duplicate_results", con=engine, if_exists="append", index=False, method="multi")

    return len(to_store)
