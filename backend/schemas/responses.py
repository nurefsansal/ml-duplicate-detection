from pydantic import BaseModel
from typing import Any


class HealthResponse(BaseModel):
    status: str


class NormalizeResponse(BaseModel):
    totalRecords: int
    normalizedRecords: list[dict[str, Any]]


class DetectResponse(BaseModel):
    sessionId: str
    uploadId: int | None = None
    candidatePairs: int
    duplicatePairs: int
    insertedRows: int
    duplicates: list[dict[str, Any]]