import logging
import os
from itertools import combinations

import pandas as pd

logger = logging.getLogger(__name__)

# Tek bir blokta maksimum kayıt sayısı.
# Bu sınırı aşan bloklar (örn. İstanbul'daki herkes) atlanır.
_MAX_BLOCK_SIZE = 500

# Toplam üretilecek maksimum aday çift sayısı
_MAX_TOTAL_PAIRS = 50_000


def _max_pairs_from_env() -> int:
    raw = os.getenv("DETECTION_MAX_PAIRS", str(_MAX_TOTAL_PAIRS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = _MAX_TOTAL_PAIRS
    return max(1, value)


def _pairs_from_group(indexes: list[int]) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    if len(indexes) < 2:
        return pairs
    for left, right in combinations(sorted(indexes), 2):
        pairs.add((left, right))
    return pairs


def _collect_pairs_by_column(
    df: pd.DataFrame,
    column: str,
    *,
    max_block_size: int = _MAX_BLOCK_SIZE,
    max_pairs: int | None = None,
    existing_pairs: set[tuple[int, int]] | None = None,
    metadata: dict[str, object] | None = None,
) -> set[tuple[int, int]]:
    """
    Belirtilen kolona göre blocking yapar.
    max_block_size'ı aşan gruplar atlanır (büyük şehirler, yaygın isimler gibi).
    """
    pairs: set[tuple[int, int]] = set()
    pair_limit = _max_pairs_from_env() if max_pairs is None else int(max_pairs)
    pool = existing_pairs if existing_pairs is not None else pairs

    if column not in df.columns:
        return pairs

    valid_df = df[df[column].notna() & (df[column].astype(str).str.strip() != "")]
    if valid_df.empty:
        return pairs

    grouped = valid_df.groupby(column).groups
    skipped_groups = 0

    for group_key, index_values in grouped.items():
        indexes = list(index_values)
        if len(indexes) > max_block_size:
            skipped_groups += 1
            logger.info(
                "Blocking: skip large block field=%s key=%s size=%d max_block_size=%d",
                column, group_key, len(indexes), max_block_size,
            )
            if metadata is not None:
                skip_log = metadata.setdefault("skipped_blocks", [])
                if isinstance(skip_log, list):
                    skip_log.append(
                        {
                            "field": column,
                            "block_key": str(group_key),
                            "block_size": int(len(indexes)),
                        }
                    )
            continue
        for pair in _pairs_from_group(indexes):
            if len(pool) >= pair_limit:
                logger.warning(
                    "Blocking: max pair limit reached (%d). Early stop on field=%s",
                    pair_limit,
                    column,
                )
                if metadata is not None:
                    metadata["limited"] = True
                return pairs
            if pair in pool:
                continue
            pairs.add(pair)
            if existing_pairs is not None:
                existing_pairs.add(pair)

    if skipped_groups > 0:
        logger.info(
            "Blocking: '%s' kolonu için %d büyük grup atlandı (max_block_size=%d).",
            column, skipped_groups, max_block_size,
        )

    return pairs


def generate_candidate_pairs(
    df: pd.DataFrame,
    *,
    max_pairs: int | None = None,
    return_metadata: bool = False,
) -> list[tuple[int, int]] | tuple[list[tuple[int, int]], dict[str, object]]:
    """
    Multi-pass blocking — performans odaklı versiyon.

    Öncelik sırası (güçten zayıfa):
    1. clean_tc             — TC kimlik no (unique, güçlü sinyal)
    2. clean_phone          — Telefon numarası
    3. email_normalized_key — Email (normalize edilmiş)
    4. name_phonetic_key    — Fonetik isim anahtarı

    ÖNEMLİ: clean_city KASITLI OLARAK ÇIKARILDI.
    Sebep: Şehir bazlı blocking, büyük şehirlerde O(n²) patlama yaratır.
    Şehir bilgisi yine de karşılaştırma (comparison) aşamasında kullanılır,
    sadece blocking aşamasında değil.

    Toplam çift sayısı _MAX_TOTAL_PAIRS ile sınırlandırılır.
    """
    pair_limit = _max_pairs_from_env() if max_pairs is None else max(1, int(max_pairs))
    all_pairs: set[tuple[int, int]] = set()
    metadata: dict[str, object] = {
        "limited": False,
        "max_pairs": pair_limit,
        "skipped_blocks": [],
    }

    # 1. Güçlü kimlik sinyalleri — küçük bloklar, yüksek precision
    _collect_pairs_by_column(
        df,
        "clean_tc",
        max_block_size=20,
        max_pairs=pair_limit,
        existing_pairs=all_pairs,
        metadata=metadata,
    )
    _collect_pairs_by_column(
        df,
        "clean_phone",
        max_block_size=100,
        max_pairs=pair_limit,
        existing_pairs=all_pairs,
        metadata=metadata,
    )
    _collect_pairs_by_column(
        df,
        "email_normalized_key",
        max_block_size=100,
        max_pairs=pair_limit,
        existing_pairs=all_pairs,
        metadata=metadata,
    )
    _collect_pairs_by_column(
        df,
        "clean_muhatap_no",
        max_block_size=50,
        max_pairs=pair_limit,
        existing_pairs=all_pairs,
        metadata=metadata,
    )

    # Erken çıkış: güçlü sinyaller zaten yeterli çift ürettiyse devam etme
    if len(all_pairs) >= pair_limit:
        metadata["limited"] = True
        logger.info(
            "Blocking: Güçlü sinyallerden %d çift üretildi, limit aşıldı. "
            "Fonetik isim bloğu atlanıyor.", len(all_pairs)
        )
        limited_pairs = sorted(all_pairs)[:pair_limit]
        if return_metadata:
            return limited_pairs, metadata
        return limited_pairs

    # 2. Fonetik isim — orta güçte, ama popüler isimler için blok boyutu sınırla
    _collect_pairs_by_column(
        df,
        "name_phonetic_key",
        max_block_size=200,
        max_pairs=pair_limit,
        existing_pairs=all_pairs,
        metadata=metadata,
    )

    if len(all_pairs) > pair_limit:
        metadata["limited"] = True
        logger.warning(
            "Blocking: Toplam çift sayısı %d, limit %d'e kırpılıyor.",
            len(all_pairs), pair_limit,
        )
        limited_pairs = sorted(all_pairs)[:pair_limit]
        if return_metadata:
            return limited_pairs, metadata
        return limited_pairs

    logger.info("Blocking: Toplam %d aday çift üretildi.", len(all_pairs))
    final_pairs = sorted(all_pairs)
    if return_metadata:
        return final_pairs, metadata
    return final_pairs
