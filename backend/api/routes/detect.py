import io

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.schemas.requests import DetectRequest, RecordIn
from backend.schemas.responses import DetectResponse
from backend.services.normalization_service import dict_records_from_df
from backend.services.rule_matching_service import detect_core

router = APIRouter()


@router.post("/detect", response_model=DetectResponse)
def detect(payload: DetectRequest):
    return detect_core(
        records=payload.records,
        min_rules_to_match=payload.minRulesToMatch,
        save_to_db=payload.saveToDb,
        session_id=payload.sessionId,
    )


@router.post("/detect-file", response_model=DetectResponse)
async def detect_file(
    file: UploadFile = File(...),
    minRulesToMatch: int = Form(default=2),
    saveToDb: bool = Form(default=False),
    sessionId: str | None = Form(default=None),
):
    filename = (file.filename or "").lower()
    content = await file.read()

    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(content))
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Use .xlsx, .xls or .csv",
        )

    records = [RecordIn(**row) for row in dict_records_from_df(df)]
    if not records:
        raise HTTPException(status_code=400, detail="File has no usable rows")

    result = detect_core(
        records=records,
        min_rules_to_match=minRulesToMatch,
        save_to_db=saveToDb,
        session_id=sessionId,
    )
    result["totalRecords"] = len(records)
    return result