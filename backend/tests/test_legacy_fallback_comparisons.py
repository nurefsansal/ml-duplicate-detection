from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.requests import RecordIn
from backend.services.matching_service import run_matching
from backend.services.rule_matching_service import _prepare_clean_dataframe


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


def test_fallback_legacy_produces_non_zero_email_and_phone_scores(monkeypatch) -> None:
    records = [
        make_record(
            "Zehra Bagis",
            telefon="054463982",
            email="zehra@gmail.com",
            sehir="Ankara",
        ),
        make_record(
            "Zehra Bagis",
            telefon="054362862",
            email="zehrabagis@gmail.com",
            sehir="Ankara",
        ),
    ]
    df_clean = _prepare_clean_dataframe(records)

    def _raise_splink(*args, **kwargs):
        raise RuntimeError("splink disabled for test")

    monkeypatch.setattr(
        "backend.services.matching_service.run_splink_detection",
        _raise_splink,
    )

    results, model_version = run_matching(
        df_clean=df_clean,
        min_rules_to_match=1,
    )
    assert model_version == "fallback_legacy_v1"
    assert len(results) >= 1

    pair = results[0]
    assert pair["decisionSource"] == "fallback_legacy"
    assert pair["fieldComparisons"]["email"]["score0To100"] > 0
    assert pair["fieldComparisons"]["phone"]["score0To100"] > 0
