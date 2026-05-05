import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.database import Entity


def test_entity_model_has_canonical_muhatap_no() -> None:
    names = {c.name for c in Entity.__table__.columns}
    assert "canonical_muhatap_no" in names
