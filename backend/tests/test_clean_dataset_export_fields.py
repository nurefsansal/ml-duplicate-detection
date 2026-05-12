import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.routes.normalized_records_route import _EXPORT_FIELDS


def test_export_includes_muhatap_and_source_label() -> None:
    assert "clean_muhatap_no" in _EXPORT_FIELDS
    assert "source_label" in _EXPORT_FIELDS
    assert "merged_member_ids" in _EXPORT_FIELDS
    assert "merge_type" in _EXPORT_FIELDS
    assert "muhatap_values_before_merge" in _EXPORT_FIELDS
