from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app
from backend.schemas.requests import RecordIn
from backend.services.rule_matching_service import detect_core


def make_record(
    ad_soyad: str,
    tc: str = "",
    telefon: str = "",
    email: str = "",
    sehir: str = "",
) -> RecordIn:
    return RecordIn(
        adSoyad=ad_soyad,
        tcKimlikNo=tc,
        telefon=telefon,
        email=email,
        sehir=sehir,
    )


def run_detection(records: list[RecordIn]) -> dict[str, Any]:
    result = detect_core(
        records=records,
        min_rules_to_match=2,
        save_to_db=False,
        session_id="pytest-session",
    )
    assert "duplicates" in result
    return result


def first_pair(records: list[RecordIn]) -> dict[str, Any]:
    result = run_detection(records)
    assert result["duplicates"], "Expected at least one duplicate pair"
    return result["duplicates"][0]


def find_pair(duplicates: list[dict[str, Any]], left_index: int, right_index: int) -> dict[str, Any]:
    for duplicate in duplicates:
        if (
            int(duplicate["left_index"]) == left_index
            and int(duplicate["right_index"]) == right_index
        ):
            return duplicate
    raise AssertionError(f"Pair {left_index}-{right_index} not found")


def test_same_normalized_email_is_reported_as_match() -> None:
    pair = first_pair(
        [
            make_record(
                "Ali Yilmaz",
                telefon="05321234567",
                email="Ali.Test+kampanya@example.com",
                sehir="Ankara",
            ),
            make_record(
                "Ali Yilmaz",
                telefon="05321234568",
                email="ali.test@example.com",
                sehir="Ankara",
            ),
        ]
    )

    email_comparison = pair["fieldComparisons"]["email"]
    assert pair["decisionSource"] == "splink_plus_rules"
    assert email_comparison["comparisonResult"] == "exact_match"
    assert email_comparison["exactMatch"] is True
    assert email_comparison["score0To100"] == 100
    assert email_comparison["normalizedLeftValue"] == email_comparison["normalizedRightValue"]


def test_same_phone_is_reported_as_match() -> None:
    pair = first_pair(
        [
            make_record(
                "Hasan Ates",
                telefon="0543 038 59 77",
                email="",
                sehir="Samsun",
            ),
            make_record(
                "Hasan Ates",
                telefon="+90 543 038 59 77",
                email="",
                sehir="Samsun",
            ),
        ]
    )

    phone_comparison = pair["fieldComparisons"]["phone"]
    assert phone_comparison["comparisonResult"] == "exact_match"
    assert phone_comparison["score0To100"] == 100
    assert pair["features"]["phone_exact_match"] == 1


def test_same_tckn_is_reported_as_match() -> None:
    pair = first_pair(
        [
            make_record(
                "Zeynep Kaya",
                tc="12345678901",
                telefon="05320000001",
                sehir="Istanbul",
            ),
            make_record(
                "Zeynep Kaya",
                tc="123 456 789 01",
                telefon="05320000002",
                sehir="Istanbul",
            ),
        ]
    )

    tc_comparison = pair["fieldComparisons"]["tc"]
    assert tc_comparison["comparisonResult"] == "exact_match"
    assert tc_comparison["score0To100"] == 100
    assert pair["features"]["tc_exact_match"] == 1


def test_name_variation_can_be_strong_without_being_exact() -> None:
    pair = first_pair(
        [
            make_record(
                "Hasan Ates",
                telefon="05335557788",
                sehir="Samsun",
            ),
            make_record(
                "Hasan Atesh",
                telefon="05335557788",
                sehir="Samsun",
            ),
        ]
    )

    full_name_comparison = pair["fieldComparisons"]["fullName"]
    assert full_name_comparison["exactMatch"] is False
    assert full_name_comparison["comparisonResult"] in {"strong_match", "partial_match"}
    assert full_name_comparison["score0To100"] >= 80


def test_same_surname_and_city_with_different_phone_does_not_auto_merge() -> None:
    pair = first_pair(
        [
            make_record(
                "Fatma Yilmaz",
                telefon="05320000001",
                email="fatma@example.com",
                sehir="Ankara",
            ),
            make_record(
                "Fatma Yilmaz",
                telefon="05329999999",
                email="fatma@example.com",
                sehir="Ankara",
            ),
        ]
    )

    assert pair["fieldComparisons"]["phone"]["comparisonResult"] != "exact_match"
    assert pair["finalDecision"] != "same_person"


def test_different_pairs_do_not_share_identical_breakdowns_unless_data_matches() -> None:
    result = run_detection(
        [
            make_record(
                "Ali Yilmaz",
                telefon="05321110000",
                email="ali.test+crm@example.com",
                sehir="Ankara",
            ),
            make_record(
                "Ali Yilmaz",
                telefon="05321110001",
                email="alitest@example.com",
                sehir="Ankara",
            ),
            make_record(
                "Ayse Demir",
                telefon="05445556677",
                email="",
                sehir="Izmir",
            ),
            make_record(
                "Ayse Demir",
                telefon="+90 544 555 66 77",
                email="",
                sehir="Izmir",
            ),
        ]
    )

    duplicates = result["duplicates"]
    email_pair = find_pair(duplicates, 0, 1)
    phone_pair = find_pair(duplicates, 2, 3)

    assert email_pair["fieldComparisons"] != phone_pair["fieldComparisons"]
    assert email_pair["fieldComparisons"]["email"]["score0To100"] == 100
    assert phone_pair["fieldComparisons"]["email"]["score0To100"] == 0
    assert email_pair["fieldComparisons"]["phone"]["score0To100"] == 0
    assert phone_pair["fieldComparisons"]["phone"]["score0To100"] == 100


def test_detect_endpoint_returns_explicit_field_comparison_shape() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/detect",
        json={
            "records": [
                {
                    "adSoyad": "Hasan Ates",
                    "tcKimlikNo": "13482477130",
                    "telefon": "05430385977",
                    "email": "hasan.ates@yahoo.com.tr",
                    "sehir": "Samsun",
                },
                {
                    "adSoyad": "Hasan Ates",
                    "tcKimlikNo": "134824771 30",
                    "telefon": "+90 543 038 59 77",
                    "email": "hasan.ates@yahoo.com.tr",
                    "sehir": "Samsun",
                },
            ],
            "minRulesToMatch": 2,
            "saveToDb": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["duplicates"]

    pair = payload["duplicates"][0]
    assert pair["decisionSource"] == "splink_plus_rules"
    assert "fieldComparisons" in pair
    assert "fullName" in pair["fieldComparisons"]
    assert "email" in pair["fieldComparisons"]
    assert "riskFlags" in pair
    assert "ruleReasons" in pair
    assert isinstance(pair["fieldComparisons"]["email"]["score0To100"], (int, float))
