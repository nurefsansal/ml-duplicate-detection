from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.requests import RecordIn
from backend.services.feature_service import should_suppress_tc_conflict_pair
from test_splink_field_comparisons import first_pair, make_record, run_detection


def test_should_suppress_tc_conflict_without_contact() -> None:
    assert should_suppress_tc_conflict_pair(
        {"tc_conflict": 1, "phone_exact_match": 0, "email_exact_match": 0}
    )
    assert not should_suppress_tc_conflict_pair(
        {"tc_conflict": 1, "phone_exact_match": 1, "email_exact_match": 0}
    )
    assert not should_suppress_tc_conflict_pair(
        {"tc_conflict": 1, "phone_exact_match": 0, "email_exact_match": 1}
    )
    assert not should_suppress_tc_conflict_pair(
        {"tc_conflict": 0, "phone_exact_match": 0, "email_exact_match": 0}
    )


def test_tc_conflict_with_same_phone_still_surfaces() -> None:
    pair = first_pair(
        [
            make_record(
                "Pelin Koc",
                tc="12345678901",
                telefon="05332223344",
                email="pelin.koc@example.com",
                sehir="Ankara",
            ),
            make_record(
                "Pelin Koc",
                tc="99999999999",
                telefon="05332223344",
                email="pelin.koc+bagis@example.com",
                sehir="Ankara",
            ),
        ]
    )
    assert pair["features"]["tc_conflict"] == 1
    assert pair["features"]["phone_exact_match"] == 1


def test_tc_conflict_without_shared_contact_not_in_duplicates() -> None:
    result = run_detection(
        [
            make_record(
                "Serk Yilmaz",
                tc="11111111110",
                telefon="05321110001",
                email="serk@example.com",
                sehir="Istanbul",
            ),
            make_record(
                "Kerem Yavuz",
                tc="22222222220",
                telefon="05329998877",
                email="kerem@example.com",
                sehir="Ankara",
            ),
        ]
    )
    for duplicate in result.get("duplicates") or []:
        features = duplicate.get("features") or {}
        assert not should_suppress_tc_conflict_pair(features), (
            "TC çakışması + ortak telefon/e-posta yokken aday üretilmemeli"
        )
