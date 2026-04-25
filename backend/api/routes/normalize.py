import io

import pandas as pd
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
