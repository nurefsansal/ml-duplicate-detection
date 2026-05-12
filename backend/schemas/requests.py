from pydantic import BaseModel, ConfigDict, Field

class RecordIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    adSoyad: str = ""
    tcKimlikNo: str = ""
    telefon: str = ""
    email: str = ""
    sehir: str = ""
    adres: str = ""

class NormalizeRequest(BaseModel):
    records: list[RecordIn] = Field(default_factory=list, min_length=1)
    uploadId: int | None = None

class DetectRequest(BaseModel):
    records: list[RecordIn] = Field(default_factory=list)
    uploadId: int | None = None
    normalizationRunId: int | None = None
    minRulesToMatch: int = Field(
        default=2,
        ge=1,
        le=4,
        description=(
            "Alan kurallarından (ad, TC, telefon, e-posta vb.) kaçının eşleşmesi gerektiği. "
            "Yüksek = daha az ama daha seçici aday; Splink olasılık eşikleri / ağırlıklar ayrıca Ayarlar'dan gelir."
        ),
    )
    saveToDb: bool = False
    sessionId: str | None = None

class DetectFromUrlRequest(BaseModel):
    url: str
    method: str = "GET"
    apiKey: str | None = None
    minRulesToMatch: int = Field(
        default=2,
        ge=1,
        le=4,
        description="Alan kuralı eşiği (1–4); yüzde benzerlik değildir.",
    )
    saveToDb: bool = False
    sessionId: str | None = None
