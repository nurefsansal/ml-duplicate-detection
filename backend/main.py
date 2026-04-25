from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.detect import router as detect_router
from backend.api.routes.admin import router as admin_router
from backend.api.routes.health import router as health_router
from backend.api.routes.normalize import router as normalize_router
from backend.api.routes.mappings import router as mappings_router
from backend.api.routes.uploads import router as uploads_router

app = FastAPI(title="Dedupli-AI API", version="0.1.0")


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
app.include_router(mappings_router, prefix="/api/v1")
app.include_router(uploads_router, prefix="/api/v1")