from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.normalization_service import (
    ADDRESS_COLUMN,
    CITY_COLUMN,
    EMAIL_COLUMN,
    PHONE_COLUMN,
    TC_COLUMN,
    canonicalize_upload_dataframe,
    infer_target_field_name,
)


def test_requested_column_aliases_are_inferred() -> None:
    expectations = {
        "e-mail": "email",
        "e mail": "email",
        "eposta": "email",
        "e-posta": "email",
        "mail": "email",
        "email address": "email",
        "adres": "address",
        "a\u00e7\u0131k adres": "address",
        "ikamet adresi": "address",
        "address": "address",
        "\u015fehir": "city",
        "sehir": "city",
        "il": "city",
        "city": "city",
        "telefon": "phone",
        "gsm": "phone",
        "cep telefonu": "phone",
        "tc": "tc",
        "tckn": "tc",
        "tc kimlik no": "tc",
    }

    for source_column, expected_target in expectations.items():
        assert infer_target_field_name(source_column) == expected_target


def test_column_names_are_normalized_before_inference() -> None:
    assert infer_target_field_name("  EMAIL_ADDRESS  ") == "email"
    assert infer_target_field_name("A\u00c7IK-ADRES") == "address"
    assert infer_target_field_name("Cep_Telefonu") == "phone"


def test_canonicalize_upload_dataframe_renames_requested_aliases() -> None:
    df_raw = pd.DataFrame(
        [
            {
                "Ad Soyad": "Ayse Demir",
                "EMAIL_ADDRESS": "ayse@example.com",
                "A\u00c7IK-ADRES": "Ataturk Cad. 1",
                "Cep_Telefonu": "05550001122",
                "\u015eehir": "Ankara",
                "TCKN": "12345678901",
            }
        ]
    )

    canonical = canonicalize_upload_dataframe(df_raw)

    assert EMAIL_COLUMN in canonical.columns
    assert ADDRESS_COLUMN in canonical.columns
    assert PHONE_COLUMN in canonical.columns
    assert CITY_COLUMN in canonical.columns
    assert TC_COLUMN in canonical.columns
