"""Kısmi birleştirmede onaylı–bekleyen kenarların pending grafından ayrılması."""

from backend.services.review_service import _partial_approval_pair_decision


def test_both_approved_pairs_become_approved() -> None:
    approved = {1, 2, 3}
    assert (
        _partial_approval_pair_decision(1, 2, approved_set=approved, rejected_set=set())
        == "approved"
    )


def test_approved_and_unselected_boundary_is_rejected() -> None:
    approved = {1, 2}
    assert (
        _partial_approval_pair_decision(1, 9, approved_set=approved, rejected_set=set())
        == "rejected"
    )


def test_unselected_pairs_stay_pending() -> None:
    approved = {1, 2}
    assert (
        _partial_approval_pair_decision(8, 9, approved_set=approved, rejected_set=set())
        == "pending"
    )
