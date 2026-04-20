from __future__ import annotations

from datetime import UTC, datetime
import io
import re

import httpx
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from src.db import create_db_engine, save_duplicates
from src.matching import EntityMatcher, MatchConfig
from src.preprocess import DataCleaner


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
    method: str = Field(default="GET")
    apiKey: str | None = None
    minRulesToMatch: int = Field(default=2, ge=1, le=4)
    saveToDb: bool = False
    sessionId: str | None = None


def _canonical_name(value: str) -> str:
    # Canonical token form improves stability for swapped name/surname order.
    tokens = [token for token in value.split(" ") if token]
    unique_sorted = sorted(set(tokens))
    return " ".join(unique_sorted)


def _phonetic_name_key(value: str) -> str:
    # Lightweight TR-friendly phonetic key for stronger normalization clustering.
    if not value:
        return ""
    text = re.sub(r"[^A-Z]", "", value.upper())
    no_vowels = re.sub(r"[AEIIOOUU]", "", text)
    collapsed = re.sub(r"(.)\1+", r"\1", no_vowels)
    return collapsed[:16]


def _normalize_email_key(value: str) -> str:
    if not value:
        return ""
    email = value.strip().lower()
    if "@" not in email:
        return email
    user, domain = email.split("@", 1)
    user = user.split("+", 1)[0].replace(".", "")
    return f"{user}@{domain}"


def _to_dataframe(records: list[RecordIn]) -> pd.DataFrame:
    rows = [
        {
            "Ad Soyad": item.adSoyad,
            "TC": item.tcKimlikNo,
            "Telefon": item.telefon,
            "E-mail": item.email,
            "Şehir": item.sehir,
        }
        for item in records
    ]
    return pd.DataFrame(rows)


def _json_rows(df: pd.DataFrame) -> list[dict]:
    safe_df = df.where(pd.notna(df), None)
    return safe_df.to_dict(orient="records")


def _dict_records_from_df(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []

    def pick(row: pd.Series, *keys: str) -> str:
        for key in keys:
            if key in row and pd.notna(row[key]):
                value = str(row[key]).strip()
                if value:
                    return value
        return ""

    out: list[dict] = []
    for _, row in df.iterrows():
        out.append(
            {
                "adSoyad": pick(row, "Ad Soyad", "adSoyad", "name", "fullName"),
                "tcKimlikNo": pick(row, "TC", "tcKimlikNo", "tc", "identity", "idNumber"),
                "telefon": pick(row, "Telefon", "telefon", "phone", "mobile"),
                "email": pick(row, "E-mail", "email", "mail"),
                "sehir": pick(row, "Şehir", "Sehir", "sehir", "city"),
            }
        )
    return out


def _detect_core(records: list[RecordIn], min_rules_to_match: int, save_to_db: bool, session_id: str | None) -> dict:
    df_raw = _to_dataframe(records)

    cleaner = DataCleaner()
    df_clean = cleaner.process(df_raw)
    df_clean["clean_name"] = df_clean["clean_name"].apply(_canonical_name)

    matcher = EntityMatcher(config=MatchConfig(min_rules_to_match=min_rules_to_match))
    candidate_pairs, _, duplicates_features = matcher.find_duplicates(df_clean)
    duplicates_view = matcher.duplicates_as_dataframe(df_clean, duplicates_features)

    inserted = 0
    resolved_session_id = session_id or str(int(datetime.now(tz=UTC).timestamp() * 1000))

    if save_to_db and not duplicates_view.empty:
        try:
            engine = create_db_engine()
            inserted = save_duplicates(engine, duplicates_view, resolved_session_id)
        except Exception as exc:  # pragma: no cover - API fallback path
            raise HTTPException(status_code=500, detail=f"DB save failed: {exc}") from exc

    return {
        "sessionId": resolved_session_id,
        "candidatePairs": int(len(candidate_pairs)),
        "duplicatePairs": int(len(duplicates_view)),
        "insertedRows": inserted,
        "duplicates": _json_rows(duplicates_view),
    }


app = FastAPI(title="Dedupli-AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/normalize")
def normalize(payload: NormalizeRequest) -> dict:
    df_raw = _to_dataframe(payload.records)

    cleaner = DataCleaner()
    normalized = cleaner.process(df_raw)
    normalized["canonical_name"] = normalized["clean_name"].apply(_canonical_name)
    normalized["name_phonetic_key"] = normalized["canonical_name"].apply(_phonetic_name_key)
    normalized["email_normalized_key"] = normalized["clean_email"].apply(_normalize_email_key)

    selected_cols = [
        "Ad Soyad",
        "Şehir",
        "Telefon",
        "TC",
        "E-mail",
        "clean_name",
        "canonical_name",
        "name_phonetic_key",
        "clean_city",
        "clean_phone",
        "clean_tc",
        "clean_email",
        "email_normalized_key",
    ]

    selected = normalized[[col for col in selected_cols if col in normalized.columns]]

    return {
        "totalRecords": len(df_raw),
        "normalizedRecords": _json_rows(selected),
    }


@app.post("/api/v1/normalize-file")
async def normalize_file(
    file: UploadFile = File(...),
) -> dict:
    """Normalize records from an uploaded Excel/CSV file."""
    filename = (file.filename or "").lower()
    content = await file.read()

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df_raw = pd.read_excel(content)
        elif filename.endswith(".csv"):
            df_raw = pd.read_csv(io.StringIO(content.decode("utf-8")))
        else:
            raise HTTPException(
                status_code=400,
                detail="Sadece .xlsx, .xls ve .csv dosyaları destekleniyor",
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Dosya okunamadı: {exc}")

    # Map common column names
    column_map = {
        "ad soyad": "Ad Soyad",
        "ad": "Ad Soyad",
        "soyad": "Ad Soyad",
        "name": "Ad Soyad",
        "tc kimlik no": "TC",
        "tc": "TC",
        "tckn": "TC",
        "telefon": "Telefon",
        "phone": "Telefon",
        "tel": "Telefon",
        "email": "E-mail",
        "e-posta": "E-mail",
        "mail": "E-mail",
        "sehir": "Şehir",
        "city": "Şehir",
        "il": "Şehir",
    }
    df_raw.columns = [column_map.get(col.lower().strip(), col) for col in df_raw.columns]

    # Ensure required columns exist
    required_cols = ["Ad Soyad"]
    missing = [c for c in required_cols if c not in df_raw.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Eksik zorunlu kolon: {', '.join(missing)}",
        )

    # Fill missing optional columns
    for col in ["TC", "Telefon", "E-mail", "Şehir"]:
        if col not in df_raw.columns:
            df_raw[col] = ""

    # Convert to RecordIn format
    records = []
    for _, row in df_raw.iterrows():
        records.append(
            RecordIn(
                adSoyad=str(row.get("Ad Soyad", "")),
                tcKimlikNo=str(row.get("TC", "")),
                telefon=str(row.get("Telefon", "")),
                email=str(row.get("E-mail", "")),
                sehir=str(row.get("Şehir", "")),
            )
        )

    # Normalize
    cleaner = DataCleaner()
    normalized = cleaner.process(df_raw)
    normalized["canonical_name"] = normalized["clean_name"].apply(_canonical_name)
    normalized["name_phonetic_key"] = normalized["canonical_name"].apply(_phonetic_name_key)
    normalized["email_normalized_key"] = normalized["clean_email"].apply(_normalize_email_key)

    selected_cols = [
        "Ad Soyad",
        "Şehir",
        "Telefon",
        "TC",
        "E-mail",
        "clean_name",
        "canonical_name",
        "name_phonetic_key",
        "clean_city",
        "clean_phone",
        "clean_tc",
        "clean_email",
        "email_normalized_key",
    ]

    selected = normalized[[col for col in selected_cols if col in normalized.columns]]

    return {
        "totalRecords": len(df_raw),
        "normalizedRecords": _json_rows(selected),
    }


@app.post("/api/v1/detect")
def detect(payload: DetectRequest) -> dict:
    return _detect_core(
        records=payload.records,
        min_rules_to_match=payload.minRulesToMatch,
        save_to_db=payload.saveToDb,
        session_id=payload.sessionId,
    )


@app.post("/api/v1/detect-file")
async def detect_file(
    file: UploadFile = File(...),
    minRulesToMatch: int = Form(default=2),
    saveToDb: bool = Form(default=False),
    sessionId: str | None = Form(default=None),
) -> dict:
    filename = (file.filename or "").lower()
    content = await file.read()

    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(content))
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Use .xlsx, .xls or .csv")

    records = [RecordIn(**row) for row in _dict_records_from_df(df)]
    if not records:
        raise HTTPException(status_code=400, detail="File has no usable rows")

    result = _detect_core(
        records=records,
        min_rules_to_match=minRulesToMatch,
        save_to_db=saveToDb,
        session_id=sessionId,
    )
    result["totalRecords"] = len(records)
    return result


@app.post("/api/v1/detect-from-url")
async def detect_from_url(payload: DetectFromUrlRequest) -> dict:
    method = payload.method.upper().strip() or "GET"
    headers: dict[str, str] = {}
    if payload.apiKey:
        headers["Authorization"] = payload.apiKey if payload.apiKey.lower().startswith("bearer ") else f"Bearer {payload.apiKey}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        if method == "POST":
            response = await client.post(payload.url, headers=headers)
        else:
            response = await client.get(payload.url, headers=headers)

    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict):
        if isinstance(data.get("records"), list):
            raw_items = data["records"]
        elif isinstance(data.get("data"), list):
            raw_items = data["data"]
        else:
            raw_items = []
    elif isinstance(data, list):
        raw_items = data
    else:
        raw_items = []

    if not raw_items:
        raise HTTPException(status_code=400, detail="URL response does not contain a record list")

    df = pd.DataFrame(raw_items)
    records = [RecordIn(**row) for row in _dict_records_from_df(df)]
    if not records:
        raise HTTPException(status_code=400, detail="No mappable fields found in URL response")

    result = _detect_core(
        records=records,
        min_rules_to_match=payload.minRulesToMatch,
        save_to_db=payload.saveToDb,
        session_id=payload.sessionId,
    )
    result["totalRecords"] = len(records)
    return result
