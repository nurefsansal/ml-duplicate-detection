"""
Simple SQL migration runner.

This project does not use Alembic yet, so numbered SQL files under this
directory are applied in lexical order.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db"
)


def _migration_files() -> list[Path]:
    return sorted(Path(__file__).parent.glob("[0-9][0-9][0-9]_*.sql"))


def _split_statements(sql_content: str) -> list[str]:
    return [statement.strip() for statement in sql_content.split(";") if statement.strip()]


def run_migration() -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = create_engine(db_url)
    migration_files = _migration_files()

    if not migration_files:
        raise FileNotFoundError("No migration files were found.")

    with engine.connect() as connection:
        for migration_file in migration_files:
            print(f"Applying migration: {migration_file.name}")
            sql_content = migration_file.read_text(encoding="utf-8")

            for statement in _split_statements(sql_content):
                try:
                    with connection.begin():
                        connection.execute(text(statement))
                except Exception as exc:  # noqa: BLE001
                    print(f"Warning while executing statement: {exc}")

    print("Migration run completed.")


if __name__ == "__main__":
    run_migration()
