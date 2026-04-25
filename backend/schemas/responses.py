from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class FileUploadIngestResponse(BaseModel):
    uploadId: int
    fileName: str
    totalRecords: int
    sourceColumns: list[str]


class NormalizeResponse(BaseModel):
    totalRecords: int
    normalizedRecords: list[dict[str, Any]]
    uploadId: int | None = None
    normalizationRunId: int | None = None
    totalProcessed: int | None = None
    successCount: int | None = None
    failedCount: int | None = None
    previewRows: list[dict[str, Any]] | None = None
    validationWarnings: list[str] | None = None


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


class ColumnMappingSuggestion(BaseModel):
    sourceColumnName: str
    targetFieldName: str
    confidence: float
    mappingType: str = "direct"


class ColumnMappingResponse(BaseModel):
    uploadId: int
    sourceColumns: list[str]
    suggestions: list[ColumnMappingSuggestion] = Field(default_factory=list)


class TargetFieldResponse(BaseModel):
    fields: list[str]
