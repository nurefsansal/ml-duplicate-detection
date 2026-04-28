from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.blocking_service import generate_candidate_pairs


def test_large_phonetic_block_does_not_explode() -> None:
    df = pd.DataFrame(
        {
            "name_phonetic_key": ["A123"] * 1000,
            "clean_phone": [""] * 1000,
            "email_normalized_key": [""] * 1000,
            "clean_tc": [""] * 1000,
            "clean_muhatap_no": [""] * 1000,
        }
    )
    pairs, meta = generate_candidate_pairs(df, return_metadata=True)
    # name_phonetic_key blok boyutu 200 olduğu için bu blok atlanmalı
    assert pairs == []
    assert isinstance(meta.get("skipped_blocks", []), list)
    assert len(meta.get("skipped_blocks", [])) >= 1


def test_early_stop_when_max_pairs_reached(monkeypatch) -> None:
    monkeypatch.setenv("DETECTION_MAX_PAIRS", "100")
    df = pd.DataFrame(
        {
            "clean_phone": ["5550000000"] * 50,
            "email_normalized_key": [""] * 50,
            "clean_tc": [""] * 50,
            "clean_muhatap_no": [""] * 50,
            "name_phonetic_key": [""] * 50,
        }
    )
    pairs, meta = generate_candidate_pairs(df, return_metadata=True)
    assert len(pairs) == 100
    assert meta.get("limited") is True


def test_skip_large_block_continues_without_error() -> None:
    df = pd.DataFrame(
        {
            "clean_tc": [""] * 310,
            "clean_phone": (["1111111111"] * 300) + (["2222222222"] * 10),
            "email_normalized_key": [""] * 310,
            "clean_muhatap_no": [""] * 310,
            "name_phonetic_key": [""] * 310,
        }
    )
    pairs, meta = generate_candidate_pairs(df, max_pairs=5000, return_metadata=True)
    # 300'lük blok skip, 10'luk bloktan 45 çift üretilmeli
    assert len(pairs) == 45
    assert any(
        block.get("field") == "clean_phone" and int(block.get("block_size", 0)) >= 300
        for block in meta.get("skipped_blocks", [])
    )
