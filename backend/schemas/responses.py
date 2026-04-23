from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class NormalizeResponse(BaseModel):
    totalRecords: int
    normalizedRecords: list[dict[str, Any]]


class FieldComparisonResponse(BaseModel):
    rawLeftValue: str | None = None
    rawRightValue: str | None = None
    normalizedLeftValue: str | None = None
    normalizedRightValue: str | None = None
    comparisonMethod: str
    comparisonResult: str
    score0To100: int | float
    exactMatch: bool
    notes: str


class DuplicatePairResponse(BaseModel):
    pairId: str
    left_index: int
    right_index: int
    record1: dict[str, Any]
    record2: dict[str, Any]
    features: dict[str, Any]
    fieldComparisons: dict[str, FieldComparisonResponse]
    riskFlags: list[str] = Field(default_factory=list)
    ruleReasons: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    splinkMatchProbability: float | None = None
    splinkMatchWeight: float | None = None
    ml_probability: float | None = None
    decision: str
    finalDecision: str
    decisionSource: str


class DetectResponse(BaseModel):
    sessionId: str
    uploadId: int | None = None
    candidatePairs: int
    duplicatePairs: int
    insertedRows: int
    totalRecords: int | None = None
    duplicates: list[DuplicatePairResponse]
