from pydantic import BaseModel, ConfigDict, Field

class RecordIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    adSoyad: str = ""
    tcKimlikNo: str = ""
    telefon: str = ""
    email: str = ""
    sehir: str = ""

class NormalizeRequest(BaseModel):
    records: list[RecordIn] = Field(default_factory=list, min_length=1)

class DetectRequest(BaseModel):
    records: list[RecordIn] = Field(default_factory=list, min_length=1)
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