import io
import os

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.preprocess import DataCleaner
from backend.schemas.requests import NormalizeFromUploadRequest, NormalizeRequest
from backend.schemas.responses import NormalizeResponse
from backend.services.mapping_service import (
    get_mappings,
    get_raw_record_rows_for_upload,
    get_raw_rows_for_upload,
    persist_upload_normalization_results,
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.schemas.requests import NormalizeRequest
from backend.schemas.responses import NormalizeResponse
from backend.services.normalization_persistence_service import (
    persist_normalization_pipeline,
)
from backend.services.normalization_service import (
    build_column_mapping_definitions,
    canonicalize_upload_dataframe,
    to_dataframe,
)

router = APIRouter()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _norm_key(value: str) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _mapping_to_dataframe(records: list[dict], mappings: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["Ad Soyad", "TC", "Telefon", "E-mail", "Şehir", "Adres"])

    normalized_rows = []
    normalized_map = {_norm_key(item.get("sourceColumnName", "")): item for item in mappings}
    fallback_aliases = {
        "name": {"adsoyad", "ad", "name", "fullname", "fullname", "musteriadi", "muhatapadi"},
        "phone": {"telefon", "tel", "gsm", "phone", "mobile"},
        "tc": {"tc", "tckn", "tckimlikno", "kimlikno", "identity"},
        "email": {"email", "eposta", "mail"},
        "city": {"sehir", "şehir", "city", "il"},
        "address": {"adres", "address", "acikadres"},
    }

    for row in records:
        out = {
            "Ad Soyad": "",
            "TC": "",
            "Telefon": "",
            "E-mail": "",
            "Şehir": "",
            "Adres": "",
        }
        for source_col, value in row.items():
            key = _norm_key(source_col)
            mapped = normalized_map.get(key)
            target = mapped.get("targetFieldName") if mapped else None

            if not target:
                for t_name, aliases in fallback_aliases.items():
                    if key in aliases:
                        target = t_name
                        break

            if target == "name":
                out["Ad Soyad"] = str(value or "")
            elif target == "tc":
                out["TC"] = str(value or "")
            elif target == "phone":
                out["Telefon"] = str(value or "")
            elif target == "email":
                out["E-mail"] = str(value or "")
            elif target == "city":
                out["Şehir"] = str(value or "")
            elif target == "address":
                out["Adres"] = str(value or "")
            elif target == "ignored":
                continue
        normalized_rows.append(out)

    return pd.DataFrame(normalized_rows)


def _normalize_dataframe(df_raw: pd.DataFrame) -> dict:
    cleaner = DataCleaner()
    normalized = cleaner.process(df_raw)

    normalized["canonical_name"] = normalized["clean_name"].apply(canonical_name)
    normalized["name_phonetic_key"] = normalized["canonical_name"].apply(phonetic_name_key)
    normalized["email_normalized_key"] = normalized["clean_email"].apply(normalize_email_key)

    selected_cols = [
        "Ad Soyad",
        "Şehir",
        "Telefon",
        "TC",
        "E-mail",
        "Adres",
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
    return {"totalRecords": len(df_raw), "normalizedRecords": json_rows(selected)}


@router.post("/normalize", response_model=NormalizeResponse)
def normalize(payload: NormalizeRequest, db: Session = Depends(get_db)):
    if payload.uploadId is not None:
        raw_rows = get_raw_rows_for_upload(db, payload.uploadId)
        if not raw_rows:
            raise HTTPException(status_code=404, detail="Upload için ham kayıt bulunamadı")
        mappings = payload.mappings if payload.mappings is not None else get_mappings(db, payload.uploadId).get("suggestions", [])
        df_raw = _mapping_to_dataframe(raw_rows, mappings)
        return _normalize_dataframe(df_raw)

    if not payload.records:
        raise HTTPException(status_code=400, detail="records veya uploadId zorunludur")

    df_raw = to_dataframe(payload.records)
    return _normalize_dataframe(df_raw)


@router.post("/normalize/from-upload", response_model=NormalizeResponse)
def normalize_from_upload(payload: NormalizeFromUploadRequest, db: Session = Depends(get_db)):
    pairs = get_raw_record_rows_for_upload(db, payload.uploadId)
    if not pairs:
        raise HTTPException(status_code=404, detail="Upload için ham kayıt bulunamadı")
    raw_rows = [p[1] for p in pairs]
    raw_ids = [p[0] for p in pairs]
    mappings = get_mappings(db, payload.uploadId).get("suggestions", [])
    df_raw = _mapping_to_dataframe(raw_rows, mappings)
    result = _normalize_dataframe(df_raw)
    norm_list = result["normalizedRecords"]
    total = int(result["totalRecords"])
    success_count = len(norm_list)
    failed_count = max(0, total - success_count)

    validation_warnings: list[str] = []
    if norm_list and all(
        not str(r.get("clean_name") or r.get("Ad Soyad") or "").strip() for r in norm_list
    ):
        validation_warnings.append(
            "Tüm kayıtlarda ad alanı boş görünüyor; kolon eşlemesini kontrol edin.",
        )

    try:
        run_id = persist_upload_normalization_results(
            db,
            payload.uploadId,
            norm_list,
            raw_ids,
            success_count=success_count,
            failed_count=failed_count,
        )
    except ValueError as exc:
        if str(exc) == "raw_id missing during normalization":
            raise HTTPException(
                status_code=500,
                detail="raw_id missing during normalization",
            ) from exc
        raise

    preview_rows = norm_list[:5]
    return {
        **result,
        "uploadId": payload.uploadId,
        "normalizationRunId": run_id,
        "totalProcessed": total,
        "successCount": success_count,
        "failedCount": failed_count,
        "previewRows": preview_rows,
        "validationWarnings": validation_warnings,
    }
@router.post("/normalize", response_model=NormalizeResponse)
def normalize(payload: NormalizeRequest):
    df_raw = to_dataframe(payload.records)
    mapping_definitions = build_column_mapping_definitions(list(df_raw.columns))

    return persist_normalization_pipeline(
        original_df=df_raw.copy(),
        processing_df=df_raw,
        source_type="api",
        source_name="normalize_api",
        file_name="normalize_request.json",
        created_by="api_normalize",
        upload_id=payload.uploadId,
        mapping_definitions=mapping_definitions,
    )


@router.post("/normalize-file", response_model=NormalizeResponse)
async def normalize_file(
    file: UploadFile = File(...),
    uploadId: int | None = Form(default=None),
):
    filename = (file.filename or "").lower()
    content = await file.read()

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df_original = pd.read_excel(io.BytesIO(content))
            source_type = "excel"
        elif filename.endswith(".csv"):
            df_original = pd.read_csv(io.StringIO(content.decode("utf-8")))
            source_type = "csv"
        else:
            raise HTTPException(
                status_code=400,
                detail="Sadece .xlsx, .xls ve .csv dosyalari destekleniyor",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Dosya okunamadi: {exc}") from exc

    mapping_definitions = build_column_mapping_definitions(
        [str(column) for column in df_original.columns]
    )

    for col in ["TC", "Telefon", "E-mail", "Şehir"]:
        if col not in df_raw.columns:
            df_raw[col] = ""

    return _normalize_dataframe(df_raw)
    try:
        df_processing = canonicalize_upload_dataframe(df_original)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return persist_normalization_pipeline(
        original_df=df_original,
        processing_df=df_processing,
        source_type=source_type,
        source_name=file.filename or "uploaded_file",
        file_name=file.filename or "uploaded_file",
        created_by="api_normalize_file",
        upload_id=uploadId,
        mapping_definitions=mapping_definitions,
    )
