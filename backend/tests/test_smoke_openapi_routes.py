"""Manuel smoke script ile uyumlu OpenAPI yolları (backend.tests.smoke_detect_admin)."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app  # noqa: E402


def test_openapi_has_detect_and_admin_pending_paths() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/detect" in paths
    assert "post" in paths["/api/v1/detect"]
    assert "/api/v1/admin/pending-matches" in paths
    assert "/api/v1/admin/approve-match" in paths


def test_openapi_has_institution_upload() -> None:
    schema = app.openapi()
    assert "/api/v1/uploads/from-institution-db" in schema["paths"]


def test_openapi_has_narrative_report_export() -> None:
    schema = app.openapi()
    assert "/api/v1/reports/export/narrative_report.txt" in schema["paths"]
    assert "get" in schema["paths"]["/api/v1/reports/export/narrative_report.txt"]
