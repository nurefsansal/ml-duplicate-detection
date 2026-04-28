from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class NormalizeResponse(BaseModel):
    totalRecords: int
    normalizedRecords: list[dict[str, Any]]
    uploadId: int | None = None
    normalizationRunId: int | None = None
    totalProcessed: int | None = None
    successCount: int | None = None
    failedCount: int | None = None
    previewRows: list[dict[str, Any]] = Field(default_factory=list)
    validationWarnings: list[str] = Field(default_factory=list)
    upload_id: int | None = None
    normalization_run_id: int | None = None
    total_processed: int | None = None
    success_count: int | None = None
    failed_count: int | None = None
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


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
    jobId: int | None = None
    uploadId: int | None = None
    normalizationRunId: int | None = None
    detectionRunId: int | None = None
    candidatePairs: int
    candidatePairsLimited: bool = False
    duplicatePairs: int
    duplicateGroupCount: int = 0
    affectedRecordCount: int = 0
    insertedRows: int
    totalRecords: int | None = None
    duplicates: list[DuplicatePairResponse]
