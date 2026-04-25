import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.schemas.responses import FileUploadIngestResponse
from backend.services.raw_ingest_service import ingest_file_to_raw_records

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/uploads/file", response_model=FileUploadIngestResponse)
async def upload_spreadsheet_for_ingest(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    filename = file.filename or "upload"
    try:
        result = ingest_file_to_raw_records(db, filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Yükleme başarısız: {exc}") from exc

    if result.get("totalRecords", 0) < 1:
        raise HTTPException(
            status_code=400,
            detail="Ham kayıt oluşturulamadı, dosya yeniden yüklenmeli.",
        )

    return result
