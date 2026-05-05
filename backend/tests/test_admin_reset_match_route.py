import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app


def test_reset_match_openapi_path_exists() -> None:
    schema = app.openapi()
    assert "/api/v1/admin/matches/{match_id}/reset" in schema["paths"]
    post = schema["paths"]["/api/v1/admin/matches/{match_id}/reset"]["post"]
    assert post is not None
