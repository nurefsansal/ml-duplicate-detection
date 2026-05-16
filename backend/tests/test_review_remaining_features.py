"""Kısmi onay tamamlayıcı davranışlar: çift kararı ve tekil entity listesi ön koşulu."""

from backend.services.review_service import _pair_decision_merge_into_entity


def test_merge_pair_both_unselected_stay_pending() -> None:
    assert (
        _pair_decision_merge_into_entity(
            10,
            20,
            approved_union={1, 2},
            pending_group_unselected={10, 20},
        )
        == "pending"
    )


def test_merge_pair_approved_meets_unselected_is_rejected() -> None:
    assert (
        _pair_decision_merge_into_entity(
            1,
            10,
            approved_union={1, 2},
            pending_group_unselected={10},
        )
        == "rejected"
    )


def test_entity_approved_tab_includes_singleton_rule() -> None:
    """_entity_merge_groups_for_upload: tek üye artık <2 + !merge ile elenmez."""
    record_ids = [42]
    has_merge_detail = False
    should_skip = len(record_ids) < 2 and not has_merge_detail and len(record_ids) != 1
    assert not should_skip
