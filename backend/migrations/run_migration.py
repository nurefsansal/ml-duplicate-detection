"""
SQL migration runner (numbered *.sql under this directory).

- Applies files in lexical order (001_, 002_, ... 006_, ...).
- Records each successfully applied file in schema_migrations so re-runs are safe.
- DATABASE_URL environment variable overrides the default DSN.

Usage (from repo root):

    python backend/migrations/run_migration.py

Or from backend folder:

    python migrations/run_migration.py

Dry-run (list pending only):

    python backend/migrations/run_migration.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db"
)


def _safe_console_text(value: object) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _migration_files() -> list[Path]:
    return sorted(Path(__file__).parent.glob("[0-9][0-9][0-9]_*.sql"))


def _split_statements(sql_content: str) -> list[str]:
    return [statement.strip() for statement in sql_content.split(";") if statement.strip()]


def _ensure_tracking_table(connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
            )
            """
        )
    )


def _is_applied(connection, filename: str) -> bool:
    row = connection.execute(
        text("SELECT 1 FROM schema_migrations WHERE filename = :fn LIMIT 1"),
        {"fn": filename},
    ).first()
    return row is not None


def _mark_applied(connection, filename: str) -> None:
    connection.execute(
        text("INSERT INTO schema_migrations (filename) VALUES (:fn)"),
        {"fn": filename},
    )


def run_migration(*, dry_run: bool = False) -> int:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = create_engine(db_url)
    migration_files = _migration_files()

    if not migration_files:
        print("No migration files were found.", file=sys.stderr)
        return 1

    pending: list[Path] = []

    with engine.connect() as connection:
        _ensure_tracking_table(connection)
        connection.commit()

        for migration_file in migration_files:
            if _is_applied(connection, migration_file.name):
                print(f"Skip (already applied): {migration_file.name}")
                continue
            pending.append(migration_file)

    if dry_run:
        if not pending:
            print("No pending migrations.")
        else:
            print("Pending migrations:")
            for p in pending:
                print(f"  - {p.name}")
        return 0

    for migration_file in pending:
        print(f"Applying migration: {migration_file.name}")
        sql_content = migration_file.read_text(encoding="utf-8")
        statements = _split_statements(sql_content)

        try:
            with engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
                _mark_applied(connection, migration_file.name)
        except Exception as exc:  # noqa: BLE001
            try:
                print(f"ERROR in {migration_file.name}: {exc}", file=sys.stderr)
            except UnicodeEncodeError:
                print(f"ERROR in {migration_file.name}:", file=sys.stderr)
                print(_safe_console_text(exc), file=sys.stderr)
            return 1

    print("Migration run completed.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply numbered SQL migrations.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pending migrations without applying.",
    )
    args = parser.parse_args()
    raise SystemExit(run_migration(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
