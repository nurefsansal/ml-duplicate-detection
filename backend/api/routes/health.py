from fastapi import APIRouter
from backend.schemas.responses import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}