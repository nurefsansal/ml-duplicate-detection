import io

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from src.preprocess import DataCleaner
from backend.schemas.requests import NormalizeRequest
from backend.schemas.responses import NormalizeResponse
from backend.services.normalization_service import (
    to_dataframe,
    json_rows,
    canonical_name,
    phonetic_name_key,
    normalize_email_key,
)

router = APIRouter()


@router.post("/normalize", response_model=NormalizeResponse)
def normalize(payload: NormalizeRequest):
    df_raw = to_dataframe(payload.records)

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
        "normalizedRecords": json_rows(selected),
    }


@router.post("/normalize-file", response_model=NormalizeResponse)
async def normalize_file(file: UploadFile = File(...)):
    filename = (file.filename or "").lower()
    content = await file.read()

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df_raw = pd.read_excel(io.BytesIO(content))
        elif filename.endswith(".csv"):
            df_raw = pd.read_csv(io.StringIO(content.decode("utf-8")))
        else:
            raise HTTPException(
                status_code=400,
                detail="Sadece .xlsx, .xls ve .csv dosyaları destekleniyor",
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Dosya okunamadı: {exc}")

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
        "şehir": "Şehir",
        "city": "Şehir",
        "il": "Şehir",
    }

    df_raw.columns = [column_map.get(str(col).lower().strip(), col) for col in df_raw.columns]

    if "Ad Soyad" not in df_raw.columns:
        raise HTTPException(status_code=400, detail="Eksik zorunlu kolon: Ad Soyad")

    for col in ["TC", "Telefon", "E-mail", "Şehir"]:
        if col not in df_raw.columns:
            df_raw[col] = ""

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
        "normalizedRecords": json_rows(selected),
    }