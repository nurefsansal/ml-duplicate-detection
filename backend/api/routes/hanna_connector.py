"""Hanna DB connector API routes.

Salt-okunur bağlantı, tablo önizleme ve güvenli sorgu erişimi sağlar.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.database_connector_service import (
    DatabaseConnectionDetails,
    DatabaseConnectorService,
)

router = APIRouter()


class ConnectorConnectionInput(BaseModel):
    host: str = Field(..., min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    db_schema: str | None = None
    sslmode: str | None = None
    label: str = Field(default="kurum-db")

    def to_details(self) -> DatabaseConnectionDetails:
        return DatabaseConnectionDetails(
            host=self.host,
            port=self.port,
            database=self.database,
            username=self.username,
            password=self.password,
            db_schema=self.db_schema,
            sslmode=self.sslmode,
            label=self.label,
        )


class ReadOnlyQueryRequest(BaseModel):
    connection: ConnectorConnectionInput
    sql: str = Field(..., min_length=1)
    params: dict[str, Any] | None = None


class TablePreviewRequest(BaseModel):
    connection: ConnectorConnectionInput
    limit: int = Field(default=50, ge=1, le=500)


def _build_service(connection: ConnectorConnectionInput) -> DatabaseConnectorService:
    return DatabaseConnectorService.from_details(connection.to_details())


@router.post("/connector/test")
def connector_test(connection: ConnectorConnectionInput):
    try:
        service = _build_service(connection)
        return {
            "success": True,
            "connection": service.masked_connection(),
            "health": service.healthcheck(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Connector connection test failed: {exc}") from exc


@router.post("/connector/tables")
def connector_tables(connection: ConnectorConnectionInput):
    try:
        service = _build_service(connection)
        return {"success": True, "tables": service.list_tables()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Table list could not be loaded: {exc}") from exc


@router.post("/connector/tables/{table_name}/preview")
def connector_table_preview(table_name: str, payload: TablePreviewRequest):
    try:
        service = _build_service(payload.connection)
        return {
            "success": True,
            "table_name": table_name,
            "limit": payload.limit,
            "rows": service.preview_table(table_name, limit=payload.limit),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Table preview failed: {exc}") from exc


@router.post("/connector/query")
def connector_query(payload: ReadOnlyQueryRequest):
    try:
        service = _build_service(payload.connection)
        rows = service.fetch_rows(payload.sql, payload.params)
        return {"success": True, "count": len(rows), "rows": rows}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc