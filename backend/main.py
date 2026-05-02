# Ana veri akışı (New Pipeline):
# uploads → raw_records → column_mappings → normalization_runs → normalized_records
#         → detection_runs → match_candidates → review_actions
#
# Yeni frontend sayfaları bu sıraya göre çalışır:
#   VeriYukleme      → POST /api/v1/uploads/file
#   VeriNormalizasyon → POST /api/v1/column-mappings + POST /api/v1/normalization-runs
#   TemizVeriSeti    → GET  /api/v1/normalized-records
#   MukerrerTespit   → POST /api/v1/detect  (uploadId ile)
#   YoneticiOnayi    → GET/POST /api/v1/admin/*
#   Raporlar         → GET  /api/v1/reports/*
#
# Legacy endpoints (/normalize-file, /detect-file) hâlâ aktif fakat
# yeni ana akış tarafından kullanılmıyor.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.detect import router as detect_router
from backend.api.routes.admin import router as admin_router
from backend.api.routes.health import router as health_router
from backend.api.routes.normalize import router as normalize_router
from backend.api.routes.reports import router as reports_router
from backend.api.routes.normalized_records_route import router as normalized_records_router
from backend.api.routes.uploads_route import router as uploads_router
from backend.api.routes.normalization_runs_route import router as normalization_runs_router
from backend.api.routes.column_mappings_route import router as column_mappings_router
from backend.api.routes.auth import router as auth_router
from backend.api.routes.ml import router as ml_router
from backend.api.routes.jobs import router as jobs_router
from backend.api.routes.settings import router as settings_router

app = FastAPI(title="Dedupli-AI API", version="0.2.0")


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Dedupli-AI API is running",
        "docs": "/docs",
        "health": "/health",
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(detect_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(normalize_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(normalized_records_router, prefix="/api/v1")
app.include_router(uploads_router, prefix="/api/v1")
app.include_router(normalization_runs_router, prefix="/api/v1")
app.include_router(column_mappings_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(ml_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api")
