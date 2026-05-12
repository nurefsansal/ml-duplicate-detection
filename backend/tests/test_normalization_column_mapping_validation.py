import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.routes.normalization_runs_route import (  # noqa: E402
    ColumnMappingItem,
    column_mappings_are_actionable,
)


def test_column_mappings_are_actionable_requires_canonical_target() -> None:
    assert column_mappings_are_actionable(None) is False
    assert column_mappings_are_actionable([]) is False
    assert (
        column_mappings_are_actionable(
            [ColumnMappingItem(source_column="x", target_field="other")]
        )
        is False
    )
    assert (
        column_mappings_are_actionable(
            [ColumnMappingItem(source_column="x", target_field="name")]
        )
        is True
    )
    assert (
        column_mappings_are_actionable(
            [
                ColumnMappingItem(source_column="a", target_field="other"),
                ColumnMappingItem(source_column="b", target_field="tc"),
            ]
        )
        is True
    )
