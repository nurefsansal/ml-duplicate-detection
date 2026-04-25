from pydantic import BaseModel, ConfigDict, Field

class RecordIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    adSoyad: str = ""
    tcKimlikNo: str = ""
    telefon: str = ""
    email: str = ""
    sehir: str = ""

class DetectRequest(BaseModel):
    records: list[RecordIn] = Field(default_factory=list)
    uploadId: int | None = None
    normalizationRunId: int | None = None
    minRulesToMatch: int = Field(default=2, ge=1, le=4)
    saveToDb: bool = False
    sessionId: str | None = None

class DetectFromUrlRequest(BaseModel):
    url: str
    method: str = "GET"
    apiKey: str | None = None
    minRulesToMatch: int = 2
    saveToDb: bool = False
    sessionId: str | None = None


class ColumnMappingItem(BaseModel):
    sourceColumnName: str
    targetFieldName: str
    confidence: float | None = None
    mappingType: str | None = None


class SaveColumnMappingsRequest(BaseModel):
    mappings: list[ColumnMappingItem] = Field(default_factory=list)
    replaceExisting: bool = True


class NormalizeRequest(BaseModel):
    records: list[RecordIn] = Field(default_factory=list)
    uploadId: int | None = None
    mappings: list[ColumnMappingItem] | None = None


class NormalizeFromUploadRequest(BaseModel):
    uploadId: int = Field(ge=1)
