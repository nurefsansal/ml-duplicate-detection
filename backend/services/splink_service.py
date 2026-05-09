from __future__ import annotations

import logging
import os
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from backend.services.advanced_matching_service import (
    hybrid_name_similarity,
    jaro_winkler_similarity,
    levenshtein_similarity,
    same_surname_name_conflict,
    token_name_similarity,
)
from backend.services.feature_service import email_similarity_score, phone_similarity_score
from backend.services.blocking_service import generate_candidate_pairs
from backend.services.resolution_service import resolve_match_decision_with_trace
from backend.services.decision_thresholds import DecisionThresholdsProb
from backend.services.scoring_app_settings import (
    compute_weighted_score_breakdown,
    load_scoring_app_settings,
)

logger = logging.getLogger(__name__)

MAX_PAIRS = 50_000
PREDICTION_THRESHOLD = 0.3


def _max_pairs_limit() -> int:
    raw = os.getenv("DETECTION_MAX_PAIRS", str(MAX_PAIRS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = MAX_PAIRS
    return max(1, value)

try:
    from splink import DuckDBAPI, Linker, SettingsCreator, block_on
    from splink.comparison_library import ExactMatch, JaroWinklerAtThresholds
    from splink.comparison_library import LevenshteinAtThresholds  # type: ignore

    SPLINK_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised when dependency is absent
    DuckDBAPI = Linker = SettingsCreator = block_on = None  # type: ignore[assignment]
    ExactMatch = JaroWinklerAtThresholds = LevenshteinAtThresholds = None  # type: ignore[assignment]
    SPLINK_IMPORT_ERROR = exc


class DetectionResults(list):
    def __init__(
        self,
        items: list[dict[str, Any]] | None = None,
        *,
        candidate_pairs: int = 0,
        candidate_pairs_total: int | None = None,
        candidate_pairs_limited: bool = False,
    ) -> None:
        super().__init__(items or [])
        self.candidate_pairs = int(candidate_pairs)
        self.candidate_pairs_total = int(
            candidate_pairs if candidate_pairs_total is None else candidate_pairs_total
        )
        self.candidate_pairs_limited = bool(candidate_pairs_limited)
        self.duplicate_pairs = len(self)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalise_mapping_key(value: str) -> str:
    text = str(value or "")
    for source, target in {
        "Ş": "S",
        "ş": "s",
        "Þ": "S",
        "þ": "s",
        "Ğ": "G",
        "ğ": "g",
        "Ü": "U",
        "ü": "u",
        "Ö": "O",
        "ö": "o",
        "Ç": "C",
        "ç": "c",
        "İ": "I",
        "ı": "i",
    }.items():
        text = text.replace(source, target)
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _pick_mapping_value(mapping: dict[str, Any], *aliases: str) -> str:
    actual_keys = {
        _normalise_mapping_key(key): key for key in mapping.keys()
    }
    for alias in aliases:
        actual_key = actual_keys.get(_normalise_mapping_key(alias))
        if actual_key is None:
            continue
        value = _safe_str(mapping.get(actual_key))
        if value:
            return value
    return ""


def _pairs_from_group(indexes: list[int]) -> set[tuple[int, int]]:
    if len(indexes) < 2:
        return set()

    pairs: set[tuple[int, int]] = set()
    ordered = sorted(int(index) for index in indexes)
    for left_pos, left_idx in enumerate(ordered):
        for right_idx in ordered[left_pos + 1 :]:
            pairs.add((left_idx, right_idx))
    return pairs


def _collect_pairs_by_column(df: pd.DataFrame, column: str) -> set[tuple[int, int]]:
    if column not in df.columns:
        return set()

    valid_mask = df[column].fillna("").astype(str).str.strip().ne("")
    if not valid_mask.any():
        return set()

    grouped = df.loc[valid_mask].groupby(column).groups
    pairs: set[tuple[int, int]] = set()
    for index_values in grouped.values():
        pairs.update(_pairs_from_group(list(index_values)))

    return pairs


def _estimate_candidate_pairs(df: pd.DataFrame) -> list[tuple[int, int]]:
    pairs, _ = generate_candidate_pairs(
        df,
        max_pairs=_max_pairs_limit(),
        return_metadata=True,
    )
    return pairs


def _split_name_parts(full_name: str) -> tuple[str, str]:
    value = _safe_str(full_name)
    if not value:
        return "", ""

    parts = [part for part in value.split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def _prepare_splink_input(df_clean: pd.DataFrame) -> pd.DataFrame:
    df_input = df_clean.copy()
    df_input["unique_id"] = df_input.index.astype(int)

    if "clean_name_ordered" not in df_input.columns:
        df_input["clean_name_ordered"] = df_input.get("clean_name", "")
    if "clean_first_name" not in df_input.columns:
        df_input["clean_first_name"] = df_input["clean_name_ordered"].apply(
            lambda value: _split_name_parts(_safe_str(value))[0]
        )
    if "clean_surname" not in df_input.columns:
        df_input["clean_surname"] = df_input["clean_name_ordered"].apply(
            lambda value: _split_name_parts(_safe_str(value))[1]
        )

    for column in (
        "clean_name",
        "clean_name_ordered",
        "clean_first_name",
        "clean_surname",
        "clean_tc",
        "clean_phone",
        "clean_email",
        "clean_city",
        "clean_address",
        "name_phonetic_key",
        "email_normalized_key",
        "name_metaphone_key",
    ):
        if column not in df_input.columns:
            df_input[column] = ""

        df_input[column] = df_input[column].apply(
            lambda value: None if _safe_str(value) == "" else _safe_str(value)
        )

    # DuckDB/Splink JaroWinkler fonksiyonları VARCHAR bekler.
    # Bazı veri setlerinde kolon dtype'ı yanlış (int) infer edilince
    # jaro_winkler_similarity(INTEGER, INTEGER) hatası alınabiliyor.
    for column in (
        "clean_name",
        "clean_name_ordered",
        "clean_first_name",
        "clean_surname",
        "email_normalized_key",
    ):
        if column in df_input.columns:
            df_input[column] = df_input[column].astype("string")

    return df_input


def _get_training_api(linker: Any) -> Any:
    return getattr(linker, "training", linker)


def _get_inference_api(linker: Any) -> Any:
    return getattr(linker, "inference", linker)


def _estimate_u(linker: Any, *, max_pairs: int) -> None:
    training_api = _get_training_api(linker)
    try:
        training_api.estimate_u_using_random_sampling(max_pairs=max_pairs)
    except Exception as exc:  # pragma: no cover - depends on dataset size and backend
        logger.warning("Splink u estimation skipped: %s", exc)


def _estimate_em(linker: Any, blocking_rule: Any, *, max_iterations: int) -> None:
    training_api = _get_training_api(linker)
    try:
        training_api.estimate_parameters_using_expectation_maximisation(
            blocking_rule,
            max_iterations=max_iterations,
        )
    except TypeError:  # pragma: no cover - compatibility branch
        try:
            training_api.estimate_parameters_using_expectation_maximisation(blocking_rule)
        except Exception as exc:  # pragma: no cover - dataset-dependent
            logger.warning("Splink EM estimation skipped for %s: %s", blocking_rule, exc)
    except Exception as exc:  # pragma: no cover - dataset-dependent
        logger.warning("Splink EM estimation skipped for %s: %s", blocking_rule, exc)


def _estimate_prior(linker: Any) -> None:
    training_api = _get_training_api(linker)
    estimator = getattr(
        training_api,
        "estimate_probability_two_random_records_match",
        None,
    )
    if estimator is None:
        return

    try:
        estimator(
            [block_on("clean_tc"), block_on("name_phonetic_key")],
            recall=0.85,
        )
    except Exception as exc:  # pragma: no cover - dataset-dependent
        logger.warning("Splink prior estimation skipped: %s", exc)


def _predict(linker: Any, *, threshold_match_probability: float | None) -> Any:
    inference_api = _get_inference_api(linker)
    kwargs: dict[str, Any] = {}
    if threshold_match_probability is not None:
        kwargs["threshold_match_probability"] = threshold_match_probability
    return inference_api.predict(**kwargs)


def _similarity_score(left: str, right: str) -> float:
    left_value = _safe_str(left)
    right_value = _safe_str(right)
    if not left_value or not right_value:
        return 0.0
    if " " in left_value or " " in right_value:
        return round(hybrid_name_similarity(left_value, right_value), 4)
    return round(jaro_winkler_similarity(left_value, right_value), 4)


def _score_to_percent(score: float) -> int:
    bounded = max(0.0, min(1.0, _safe_float(score)))
    return int(round(bounded * 100))


def _email_similarity(left_email: str, right_email: str) -> float:
    """
    İki email adresi arasında akıllı benzerlik skoru hesaplar.
    - Tamamen aynıysa 1.0
    - @ öncesi (local part) ve @ sonrası (domain) ayrı ayrı değerlendirilir
    - Domain aynıysa (gmail.com gibi) bonus puan verilir
    - Local part için SequenceMatcher + uzunluk farkı cezası uygulanır
    Skor 0.0-1.0 arasında döner.
    """
    left = _safe_str(left_email).lower()
    right = _safe_str(right_email).lower()
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    if "@" not in left or "@" not in right:
        return round(SequenceMatcher(None, left, right).ratio(), 4)

    left_local, left_domain = left.rsplit("@", 1)
    right_local, right_domain = right.rsplit("@", 1)

    domain_match = float(left_domain == right_domain)

    local_sim = SequenceMatcher(None, left_local, right_local).ratio()

    max_len = max(len(left_local), len(right_local))
    min_len = min(len(left_local), len(right_local))
    length_penalty = (max_len - min_len) / max_len if max_len > 0 else 0
    adjusted_local_sim = local_sim * (1 - length_penalty * 0.3)

    if domain_match:
        score = 0.30 + (adjusted_local_sim * 0.70)
    else:
        score = adjusted_local_sim * 0.50

    return round(min(score, 1.0), 4)


def _build_email_field_comparison(
    *,
    raw_left_value: str,
    raw_right_value: str,
    normalized_left_value: str,
    normalized_right_value: str,
    gamma_value: Any,
    clean_left_email: str = "",
    clean_right_email: str = "",
) -> dict[str, Any]:
    """
    Email karşılaştırması: exact match + fuzzy similarity hibrit.
    email_normalized_key exact match önce denenir.
    Farklıysa clean_email üzerinden fuzzy benzerlik hesaplanır.
    """
    if not normalized_left_value and not normalized_right_value:
        # Normalized key yoksa ama clean_email varsa fuzzy ile yine skor üret.
        if clean_left_email and clean_right_email:
            similarity = email_similarity_score(
                _safe_str(clean_left_email),
                _safe_str(clean_right_email),
            )
            score = _score_to_percent(similarity)
            if similarity >= 0.85:
                result = "strong_match"
                notes = f"E-posta yüksek benzerlik gösteriyor (skor: {score}/100). Muhtemelen aynı kişi."
            elif similarity >= 0.60:
                result = "partial_match"
                notes = f"E-posta kısmi benzerlik gösteriyor (skor: {score}/100). Manuel inceleme önerilir."
            elif similarity >= 0.20:
                result = "weak_match"
                notes = f"E-posta zayıf benzerlik gösteriyor (skor: {score}/100)."
            else:
                result = "mismatch"
                notes = "E-posta adresleri belirgin şekilde farklı."
            return {
                "rawLeftValue": raw_left_value or None,
                "rawRightValue": raw_right_value or None,
                "normalizedLeftValue": None,
                "normalizedRightValue": None,
                "comparisonMethod": "splink_hybrid_email_similarity",
                "comparisonResult": result,
                "score0To100": score,
                "exactMatch": False,
                "notes": notes,
            }
        return {
            "rawLeftValue": None,
            "rawRightValue": None,
            "normalizedLeftValue": None,
            "normalizedRightValue": None,
            "comparisonMethod": "splink_hybrid_email_similarity",
            "comparisonResult": "missing",
            "score0To100": 0,
            "exactMatch": False,
            "notes": "E-posta her iki kayıtta da boş.",
        }
    if not normalized_left_value or not normalized_right_value:
        # Normalized key tek tarafta yoksa, clean_email varsa fuzzy hesapla.
        if clean_left_email and clean_right_email:
            similarity = email_similarity_score(
                _safe_str(clean_left_email),
                _safe_str(clean_right_email),
            )
            score = _score_to_percent(similarity)
            if similarity >= 0.85:
                result = "strong_match"
                notes = f"E-posta yüksek benzerlik gösteriyor (skor: {score}/100). Muhtemelen aynı kişi."
            elif similarity >= 0.60:
                result = "partial_match"
                notes = f"E-posta kısmi benzerlik gösteriyor (skor: {score}/100). Manuel inceleme önerilir."
            elif similarity >= 0.20:
                result = "weak_match"
                notes = f"E-posta zayıf benzerlik gösteriyor (skor: {score}/100)."
            else:
                result = "mismatch"
                notes = "E-posta adresleri belirgin şekilde farklı."
            return {
                "rawLeftValue": raw_left_value or None,
                "rawRightValue": raw_right_value or None,
                "normalizedLeftValue": normalized_left_value or None,
                "normalizedRightValue": normalized_right_value or None,
                "comparisonMethod": "splink_hybrid_email_similarity",
                "comparisonResult": result,
                "score0To100": score,
                "exactMatch": False,
                "notes": notes,
            }
        return {
            "rawLeftValue": raw_left_value or None,
            "rawRightValue": raw_right_value or None,
            "normalizedLeftValue": normalized_left_value or None,
            "normalizedRightValue": normalized_right_value or None,
            "comparisonMethod": "splink_hybrid_email_similarity",
            "comparisonResult": "missing",
            "score0To100": 0,
            "exactMatch": False,
            "notes": "E-posta alanlarından biri boş.",
        }

    gamma = _safe_int(gamma_value, default=-999)
    # JaroWinklerAtThresholds gamması (eşikler=[0.90,0.70]) için:
    # 3: exact, 2: strong, 1: partial, 0: mismatch
    exact_match = (gamma >= 3) or (normalized_left_value == normalized_right_value)

    if exact_match:
        score = 100
        result = "exact_match"
        notes = "Normalize edilmiş e-posta anahtarı birebir eşleşti."
    else:
        sim_on_key = email_similarity_score(normalized_left_value, normalized_right_value)
        sim_on_raw = (
            email_similarity_score(_safe_str(clean_left_email), _safe_str(clean_right_email))
            if clean_left_email and clean_right_email
            else 0.0
        )
        similarity = max(sim_on_key, sim_on_raw)
        score = _score_to_percent(similarity)

        if similarity >= 0.85:
            result = "strong_match"
            notes = f"E-posta yüksek benzerlik gösteriyor (skor: {score}/100). Muhtemelen aynı kişi."
        elif similarity >= 0.60:
            result = "partial_match"
            notes = f"E-posta kısmi benzerlik gösteriyor (skor: {score}/100). Manuel inceleme önerilir."
        elif similarity >= 0.20:
            result = "weak_match"
            notes = f"E-posta zayıf benzerlik gösteriyor (skor: {score}/100)."
        else:
            result = "mismatch"
            notes = "E-posta adresleri belirgin şekilde farklı."

    return {
        "rawLeftValue": raw_left_value or None,
        "rawRightValue": raw_right_value or None,
        "normalizedLeftValue": normalized_left_value or None,
        "normalizedRightValue": normalized_right_value or None,
        "comparisonMethod": "splink_hybrid_email_similarity",
        "comparisonResult": result,
        "score0To100": score,
        "exactMatch": exact_match,
        "notes": notes,
    }


def _rename_output_column(comparison: Any, output_column_name: str) -> dict[str, Any]:
    comparison_dict = comparison.create_comparison_dict("duckdb")
    comparison_dict["output_column_name"] = output_column_name
    comparison_dict["comparison_description"] = output_column_name
    return comparison_dict


def _gamma_exact_match(
    normalized_left: str,
    normalized_right: str,
    gamma_value: Any,
    *,
    exact_level: int = 1,
) -> bool:
    if not normalized_left or not normalized_right:
        return False
    if _safe_int(gamma_value, default=-999) == exact_level:
        return True
    return normalized_left == normalized_right


def _build_exact_field_comparison(
    *,
    raw_left_value: str,
    raw_right_value: str,
    normalized_left_value: str,
    normalized_right_value: str,
    comparison_method: str,
    notes: str,
    gamma_value: Any,
    field_name: str,
    use_conflict_label: bool = False,
) -> dict[str, Any]:
    if not normalized_left_value and not normalized_right_value:
        result = "missing"
        score = 0
        exact_match = False
        final_notes = f"{field_name} her iki kayitta da bos."
    elif not normalized_left_value or not normalized_right_value:
        result = "missing"
        score = 0
        exact_match = False
        final_notes = f"{field_name} alanlarindan biri bos oldugu icin esitlik kurulamadı."
    else:
        exact_match = _gamma_exact_match(
            normalized_left_value,
            normalized_right_value,
            gamma_value,
        )
        score = 100 if exact_match else 0
        if exact_match:
            result = "exact_match"
            final_notes = notes
        else:
            result = "conflict" if use_conflict_label else "mismatch"
            final_notes = f"{field_name} normalize edilmis degerleri farkli."

    return {
        "rawLeftValue": raw_left_value or None,
        "rawRightValue": raw_right_value or None,
        "normalizedLeftValue": normalized_left_value or None,
        "normalizedRightValue": normalized_right_value or None,
        "comparisonMethod": comparison_method,
        "comparisonResult": result,
        "score0To100": score,
        "exactMatch": exact_match,
        "notes": final_notes,
    }


def _build_phone_field_comparison(
    *,
    raw_left_value: str,
    raw_right_value: str,
    normalized_left_value: str,
    normalized_right_value: str,
    gamma_value: Any,
) -> dict[str, Any]:
    """
    Telefon karşılaştırması: exact match + kademeli fuzzy similarity.

    Kademe sırası:
    1. Exact match (normalize edilmiş numara birebir aynı)
    2. Son 7 hane eşleşmesi (farklı alan kodu, aynı numara)
    3. Son 6 hane eşleşmesi
    4. Genel string similarity (SequenceMatcher)
    """
    if not normalized_left_value and not normalized_right_value:
        return {
            "rawLeftValue": None,
            "rawRightValue": None,
            "normalizedLeftValue": None,
            "normalizedRightValue": None,
            "comparisonMethod": "splink_tiered_phone_similarity",
            "comparisonResult": "missing",
            "score0To100": 0,
            "exactMatch": False,
            "notes": "Telefon her iki kayıtta da boş.",
        }
    if not normalized_left_value or not normalized_right_value:
        return {
            "rawLeftValue": raw_left_value or None,
            "rawRightValue": raw_right_value or None,
            "normalizedLeftValue": normalized_left_value or None,
            "normalizedRightValue": normalized_right_value or None,
            "comparisonMethod": "splink_tiered_phone_similarity",
            "comparisonResult": "missing",
            "score0To100": 0,
            "exactMatch": False,
            "notes": "Telefon alanlarından biri boş.",
        }

    gamma = _safe_int(gamma_value, default=-999)
    exact_match = (gamma == 1) or (normalized_left_value == normalized_right_value)

    if exact_match:
        return {
            "rawLeftValue": raw_left_value or None,
            "rawRightValue": raw_right_value or None,
            "normalizedLeftValue": normalized_left_value or None,
            "normalizedRightValue": normalized_right_value or None,
            "comparisonMethod": "splink_tiered_phone_similarity",
            "comparisonResult": "exact_match",
            "score0To100": 100,
            "exactMatch": True,
            "notes": "Telefon numarası normalize edilmiş şekilde birebir eşleşti.",
        }

    similarity = phone_similarity_score(normalized_left_value, normalized_right_value)
    score = _score_to_percent(similarity)

    if similarity >= 0.85:
        result = "strong_match"
        notes = f"Telefon numaraları güçlü benzerlik gösteriyor (skor: {score}/100)."
    elif similarity >= 0.60:
        result = "partial_match"
        notes = f"Telefon numaraları kısmi benzerlik gösteriyor (skor: {score}/100)."
    elif similarity >= 0.20:
        result = "weak_match"
        notes = f"Telefon numaraları zayıf benzerlik gösteriyor (skor: {score}/100)."
    else:
        result = "mismatch"
        notes = "Telefon numaraları belirgin şekilde farklı."

    return {
        "rawLeftValue": raw_left_value or None,
        "rawRightValue": raw_right_value or None,
        "normalizedLeftValue": normalized_left_value or None,
        "normalizedRightValue": normalized_right_value or None,
        "comparisonMethod": "splink_tiered_phone_similarity",
        "comparisonResult": result,
        "score0To100": score,
        "exactMatch": False,
        "notes": notes,
    }


def _build_jw_field_comparison(
    *,
    raw_left_value: str,
    raw_right_value: str,
    normalized_left_value: str,
    normalized_right_value: str,
    comparison_method: str,
    gamma_value: Any,
    exact_level: int,
    strong_level: int,
    partial_level: int,
    strong_threshold: float,
    partial_threshold: float,
    exact_note: str,
    strong_note: str,
    partial_note: str,
    mismatch_note: str,
    field_name: str,
) -> dict[str, Any]:
    similarity = _similarity_score(normalized_left_value, normalized_right_value)
    score = _score_to_percent(similarity)

    if not normalized_left_value and not normalized_right_value:
        result = "missing"
        exact_match = False
        notes = f"{field_name} her iki kayitta da bos."
        score = 0
    elif not normalized_left_value or not normalized_right_value:
        result = "missing"
        exact_match = False
        notes = f"{field_name} alanlarindan biri bos."
        score = 0
    else:
        gamma = _safe_int(gamma_value, default=-999)
        exact_match = gamma == exact_level or normalized_left_value == normalized_right_value
        if exact_match:
            result = "exact_match"
            notes = exact_note
            score = 100
        elif gamma == strong_level or similarity >= strong_threshold:
            result = "strong_match"
            notes = strong_note
        elif gamma == partial_level or similarity >= partial_threshold:
            result = "partial_match"
            notes = partial_note
        else:
            result = "mismatch"
            notes = mismatch_note

    return {
        "rawLeftValue": raw_left_value or None,
        "rawRightValue": raw_right_value or None,
        "normalizedLeftValue": normalized_left_value or None,
        "normalizedRightValue": normalized_right_value or None,
        "comparisonMethod": comparison_method,
        "comparisonResult": result,
        "score0To100": score,
        "exactMatch": exact_match,
        "notes": notes,
    }


def _build_address_field_comparison(
    left_record: dict[str, Any],
    right_record: dict[str, Any],
) -> dict[str, Any]:
    raw_left_value = _safe_str(left_record.get("clean_muhatap_no")) or _pick_mapping_value(
        left_record, "Muhatap No", "muhatap_no", "muhatap kodu", "customer_id"
    )
    raw_right_value = _safe_str(right_record.get("clean_muhatap_no")) or _pick_mapping_value(
        right_record, "Muhatap No", "muhatap_no", "muhatap kodu", "customer_id"
    )

    if not raw_left_value and not raw_right_value:
        return {
            "rawLeftValue": None,
            "rawRightValue": None,
            "normalizedLeftValue": None,
            "normalizedRightValue": None,
            "comparisonMethod": "not_available",
            "comparisonResult": "not_available",
            "score0To100": 0,
            "exactMatch": False,
            "notes": "Bu veri setinde muhatap kodu bulunmuyor.",
        }
    if not raw_left_value or not raw_right_value:
        return {
            "rawLeftValue": raw_left_value or None,
            "rawRightValue": raw_right_value or None,
            "normalizedLeftValue": raw_left_value or None,
            "normalizedRightValue": raw_right_value or None,
            "comparisonMethod": "exact_match(clean_muhatap_no)",
            "comparisonResult": "missing",
            "score0To100": 0,
            "exactMatch": False,
            "notes": "Muhatap Kodu alanlarindan biri bos.",
        }

    exact_match = raw_left_value == raw_right_value
    return {
        "rawLeftValue": raw_left_value,
        "rawRightValue": raw_right_value,
        "normalizedLeftValue": raw_left_value,
        "normalizedRightValue": raw_right_value,
        "comparisonMethod": "exact_match(clean_muhatap_no)",
        "comparisonResult": "exact_match" if exact_match else "conflict",
        "score0To100": 100 if exact_match else 0,
        "exactMatch": exact_match,
        "notes": (
            "Muhatap Kodu birebir eslesti; guclu eslesme sinyali."
            if exact_match
            else "Muhatap Kodu catisiyor; farkli kisi olabilir."
        ),
    }


def _build_field_comparisons(
    row: dict[str, Any],
    left_record: dict[str, Any],
    right_record: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    raw_left_name = _pick_mapping_value(left_record, "Ad Soyad", "adSoyad", "name", "full_name")
    raw_right_name = _pick_mapping_value(right_record, "Ad Soyad", "adSoyad", "name", "full_name")
    raw_left_email = _pick_mapping_value(left_record, "E-mail", "email", "mail")
    raw_right_email = _pick_mapping_value(right_record, "E-mail", "email", "mail")
    raw_left_phone = _pick_mapping_value(left_record, "Telefon", "telefon", "phone", "mobile")
    raw_right_phone = _pick_mapping_value(right_record, "Telefon", "telefon", "phone", "mobile")
    raw_left_tc = _pick_mapping_value(left_record, "TC", "tcKimlikNo", "tc")
    raw_right_tc = _pick_mapping_value(right_record, "TC", "tcKimlikNo", "tc")
    raw_left_city = _pick_mapping_value(left_record, "Sehir", "Şehir", "city")
    raw_right_city = _pick_mapping_value(right_record, "Sehir", "Şehir", "city")
    raw_left_address = _pick_mapping_value(left_record, "Adres", "adres", "address")
    raw_right_address = _pick_mapping_value(right_record, "Adres", "adres", "address")

    normalized_left_full_name = _safe_str(left_record.get("clean_name"))
    normalized_right_full_name = _safe_str(right_record.get("clean_name"))
    normalized_left_first_name = _safe_str(left_record.get("clean_first_name"))
    normalized_right_first_name = _safe_str(right_record.get("clean_first_name"))
    normalized_left_surname = _safe_str(left_record.get("clean_surname"))
    normalized_right_surname = _safe_str(right_record.get("clean_surname"))
    normalized_left_tc = _safe_str(left_record.get("clean_tc"))
    normalized_right_tc = _safe_str(right_record.get("clean_tc"))
    normalized_left_phone = _safe_str(left_record.get("clean_phone"))
    normalized_right_phone = _safe_str(right_record.get("clean_phone"))
    normalized_left_email = _safe_str(left_record.get("email_normalized_key"))
    normalized_right_email = _safe_str(right_record.get("email_normalized_key"))
    normalized_left_city = _safe_str(left_record.get("clean_city"))
    normalized_right_city = _safe_str(right_record.get("clean_city"))
    normalized_left_address = _safe_str(left_record.get("clean_address"))
    normalized_right_address = _safe_str(right_record.get("clean_address"))

    field_comparisons = {
        "fullName": _build_jw_field_comparison(
            raw_left_value=raw_left_name,
            raw_right_value=raw_right_name,
            normalized_left_value=normalized_left_full_name,
            normalized_right_value=normalized_right_full_name,
            comparison_method="splink_hybrid_jaro_token_similarity(clean_name)",
            gamma_value=row.get("gamma_clean_name"),
            exact_level=3,
            strong_level=2,
            partial_level=1,
            strong_threshold=0.92,
            partial_threshold=0.80,
            exact_note="Normalize edilmis ad soyad birebir eslesti.",
            strong_note="Ad soyad Splink Jaro-Winkler esiginde guclu benzerlik gosteriyor.",
            partial_note="Ad soyad kisitli benzerlik gosteriyor; manuel inceleme gerekebilir.",
            mismatch_note="Ad soyad alanlari dusuk benzerlikte.",
            field_name="Ad soyad",
        ),
        "firstName": _build_jw_field_comparison(
            raw_left_value=_split_name_parts(raw_left_name)[0],
            raw_right_value=_split_name_parts(raw_right_name)[0],
            normalized_left_value=normalized_left_first_name,
            normalized_right_value=normalized_right_first_name,
            comparison_method="splink_jaro_winkler(clean_first_name)",
            gamma_value=row.get("gamma_first_name"),
            exact_level=3,
            strong_level=2,
            partial_level=1,
            strong_threshold=0.95,
            partial_threshold=0.85,
            exact_note="Ad alanı normalize edilmis sekilde birebir eslesti.",
            strong_note="Ad alanı yuksek benzerlik gosteriyor.",
            partial_note="Ad alanı kismi benzerlik gosteriyor.",
            mismatch_note="Ad alanı farkli gorunuyor.",
            field_name="Ad",
        ),
        "surname": _build_jw_field_comparison(
            raw_left_value=_split_name_parts(raw_left_name)[1],
            raw_right_value=_split_name_parts(raw_right_name)[1],
            normalized_left_value=normalized_left_surname,
            normalized_right_value=normalized_right_surname,
            comparison_method="splink_jaro_winkler(clean_surname)",
            gamma_value=row.get("gamma_surname"),
            exact_level=3,
            strong_level=2,
            partial_level=1,
            strong_threshold=0.95,
            partial_threshold=0.85,
            exact_note="Soyad alanı normalize edilmis sekilde birebir eslesti.",
            strong_note="Soyad alanı yuksek benzerlik gosteriyor.",
            partial_note="Soyad alanı kismi benzerlik gosteriyor.",
            mismatch_note="Soyad alanı farkli gorunuyor.",
            field_name="Soyad",
        ),
        "tc": _build_exact_field_comparison(
            raw_left_value=raw_left_tc,
            raw_right_value=raw_right_tc,
            normalized_left_value=normalized_left_tc,
            normalized_right_value=normalized_right_tc,
            comparison_method="splink_exact_match(clean_tc)",
            notes="TC Kimlik No normalize edilmis sekilde birebir eslesti.",
            gamma_value=row.get("gamma_clean_tc"),
            field_name="TC Kimlik No",
            use_conflict_label=True,
        ),
        "phone": _build_phone_field_comparison(
            raw_left_value=raw_left_phone,
            raw_right_value=raw_right_phone,
            normalized_left_value=normalized_left_phone,
            normalized_right_value=normalized_right_phone,
            gamma_value=row.get("gamma_clean_phone"),
        ),
        "email": _build_email_field_comparison(
            raw_left_value=raw_left_email,
            raw_right_value=raw_right_email,
            normalized_left_value=normalized_left_email,
            normalized_right_value=normalized_right_email,
            gamma_value=row.get("gamma_email"),
            clean_left_email=_safe_str(left_record.get("clean_email")),
            clean_right_email=_safe_str(right_record.get("clean_email")),
        ),
        "city": _build_exact_field_comparison(
            raw_left_value=raw_left_city,
            raw_right_value=raw_right_city,
            normalized_left_value=normalized_left_city,
            normalized_right_value=normalized_right_city,
            comparison_method="splink_exact_match(clean_city)",
            notes="Sehir normalize edilmis sekilde birebir eslesti.",
            gamma_value=row.get("gamma_clean_city"),
            field_name="Sehir",
        ),
        "address": _build_jw_field_comparison(
            raw_left_value=raw_left_address,
            raw_right_value=raw_right_address,
            normalized_left_value=normalized_left_address,
            normalized_right_value=normalized_right_address,
            comparison_method="splink_jaro_winkler(clean_address)",
            gamma_value=row.get("gamma_address"),
            exact_level=3,
            strong_level=2,
            partial_level=1,
            strong_threshold=0.95,
            partial_threshold=0.80,
            exact_note="Adres normalize edilmis sekilde birebir eslesti.",
            strong_note="Adres alaninda guclu benzerlik var.",
            partial_note="Adres alaninda kismi benzerlik var.",
            mismatch_note="Adres alanlari belirgin sekilde farkli.",
            field_name="Adres",
        ),
        "muhatapNo": _build_address_field_comparison(left_record, right_record),
    }

    email_comparison = field_comparisons["email"]
    if (
        email_comparison["comparisonResult"] == "exact_match"
        and _safe_str(left_record.get("clean_email")) != _safe_str(right_record.get("clean_email"))
        and _safe_str(left_record.get("clean_email"))
        and _safe_str(right_record.get("clean_email"))
    ):
        email_comparison["notes"] = (
            "Ham e-posta yazimlari farkli olsa da normalize edilmis e-posta anahtari birebir eslesti."
        )

    return field_comparisons


def _derive_features_from_field_comparisons(
    left_record: dict[str, Any],
    right_record: dict[str, Any],
    field_comparisons: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    left_tc = _safe_str(left_record.get("clean_tc"))
    right_tc = _safe_str(right_record.get("clean_tc"))
    left_phone = _safe_str(left_record.get("clean_phone"))
    right_phone = _safe_str(right_record.get("clean_phone"))
    left_email_key = _safe_str(left_record.get("email_normalized_key"))
    right_email_key = _safe_str(right_record.get("email_normalized_key"))
    left_city = _safe_str(left_record.get("clean_city"))
    right_city = _safe_str(right_record.get("clean_city"))
    left_address = _safe_str(left_record.get("clean_address"))
    right_address = _safe_str(right_record.get("clean_address"))
    left_muhatap = _safe_str(left_record.get("clean_muhatap_no"))
    right_muhatap = _safe_str(right_record.get("clean_muhatap_no"))
    left_name = _safe_str(left_record.get("clean_name"))
    right_name = _safe_str(right_record.get("clean_name"))
    left_first = _safe_str(left_record.get("clean_first_name"))
    right_first = _safe_str(right_record.get("clean_first_name"))
    left_surname = _safe_str(left_record.get("clean_surname"))
    right_surname = _safe_str(right_record.get("clean_surname"))
    left_ordered_name = _safe_str(left_record.get("clean_name_ordered")) or left_name
    right_ordered_name = _safe_str(right_record.get("clean_name_ordered")) or right_name
    left_phonetic = _safe_str(left_record.get("name_phonetic_key"))
    right_phonetic = _safe_str(right_record.get("name_phonetic_key"))
    left_metaphone = _safe_str(left_record.get("name_metaphone_key"))
    right_metaphone = _safe_str(right_record.get("name_metaphone_key"))
    left_email_raw = _safe_str(left_record.get("clean_email"))
    right_email_raw = _safe_str(right_record.get("clean_email"))

    phone_exact = int(field_comparisons["phone"]["exactMatch"])
    email_exact = int(field_comparisons["email"]["exactMatch"])
    first_name_similarity = _similarity_score(left_first, right_first)
    surname_similarity = _similarity_score(left_surname, right_surname)
    full_name_similarity = _similarity_score(left_name, right_name)
    phone_similarity = round(phone_similarity_score(left_phone, right_phone), 4)
    email_similarity = 0.0
    if left_email_key and right_email_key:
        email_similarity = max(
            email_similarity,
            round(email_similarity_score(left_email_key, right_email_key), 4),
        )
    if left_email_raw and right_email_raw:
        email_similarity = max(
            email_similarity,
            round(email_similarity_score(left_email_raw, right_email_raw), 4),
        )
    shared_contact_flag = int(bool(phone_exact or email_exact))

    shared_contact_name_conflict = int(
        bool(
            shared_contact_flag
            and first_name_similarity < 0.55
            and surname_similarity >= 0.80
        )
    )

    household_risk_flag = int(
        bool(
            shared_contact_flag
            and surname_similarity >= 0.80
            and first_name_similarity < 0.70
        )
    )
    same_surname_name_conflict_flag = int(
        same_surname_name_conflict(left_ordered_name, right_ordered_name)
    )

    return {
        "tc_exact_match": int(field_comparisons["tc"]["exactMatch"]),
        "tc_conflict": int(bool(left_tc and right_tc and left_tc != right_tc)),
        "tc_present_both": int(bool(left_tc and right_tc)),
        "muhatap_no_exact_match": int(
            bool(left_muhatap and right_muhatap and left_muhatap == right_muhatap)
        ),
        "muhatap_no_conflict": int(
            bool(left_muhatap and right_muhatap and left_muhatap != right_muhatap)
        ),
        "muhatap_present_both": int(bool(left_muhatap and right_muhatap)),
        "phone_exact_match": phone_exact,
        "phone_match": phone_exact,
        "phone_similarity": phone_similarity,
        "phone_present_both": int(bool(left_phone and right_phone)),
        "phone_last7_match": int(
            bool(left_phone and right_phone and left_phone[-7:] == right_phone[-7:])
        ),
        "email_exact_match": email_exact,
        "email_present_both": int(
            bool(
                (left_email_raw and right_email_raw)
                or (left_email_key and right_email_key)
            )
        ),
        "city_exact_match": int(field_comparisons["city"]["exactMatch"]),
        "city_match": int(field_comparisons["city"]["exactMatch"]),
        "address_similarity": round(
            field_comparisons["address"]["score0To100"] / 100,
            4,
        ),
        "phonetic_exact_match": int(
            bool(left_phonetic and right_phonetic and left_phonetic == right_phonetic)
        ),
        "metaphone_exact_match": int(
            bool(left_metaphone and right_metaphone and left_metaphone == right_metaphone)
        ),
        "phonetic_close_match": int(
            bool(
                (left_phonetic and right_phonetic and left_phonetic == right_phonetic)
                or (left_metaphone and right_metaphone and left_metaphone == right_metaphone)
            )
        ),
        "name_similarity": full_name_similarity,
        "name_present_both": int(bool(left_name and right_name)),
        "name_jaro_winkler": _similarity_score(left_name, right_name),
        "name_token_similarity": round(
            token_name_similarity(left_ordered_name, right_ordered_name),
            4,
        ),
        "name_levenshtein_similarity": round(
            levenshtein_similarity(left_name, right_name),
            4,
        ),
        "email_similarity": email_similarity,
        "first_name_similarity": first_name_similarity,
        "surname_similarity": surname_similarity,
        "first_name_jaro_winkler": _similarity_score(left_first, right_first),
        "surname_jaro_winkler": _similarity_score(left_surname, right_surname),
        "first_name_exact_match": int(field_comparisons["firstName"]["exactMatch"]),
        "surname_exact_match": int(field_comparisons["surname"]["exactMatch"]),
        "shared_contact_flag": shared_contact_flag,
        "shared_contact_name_conflict": shared_contact_name_conflict,
        "household_risk_flag": household_risk_flag,
        "same_surname_name_conflict": same_surname_name_conflict_flag,
        "common_non_empty_fields": sum(
            [
                int(bool(left_tc and right_tc)),
                int(bool(left_phone and right_phone)),
                int(bool(left_email_key and right_email_key)),
                int(bool(left_name and right_name)),
                int(bool(left_city and right_city)),
                int(bool(left_address and right_address)),
                int(bool(left_muhatap and right_muhatap)),
            ]
        ),
    }


def _build_risk_flags(features: dict[str, Any]) -> list[str]:
    risk_flags: list[str] = []

    if features.get("tc_conflict", 0):
        risk_flags.append("tc_conflict")
    if features.get("muhatap_no_conflict", 0):
        risk_flags.append("muhatap_no_conflict")
    if features.get("shared_contact_flag", 0):
        risk_flags.append("shared_contact")
    if features.get("shared_contact_name_conflict", 0):
        risk_flags.append("shared_contact_name_conflict")
    if features.get("household_risk_flag", 0):
        risk_flags.append("household_risk")
    if features.get("same_surname_name_conflict", 0):
        risk_flags.append("same_surname_name_conflict")
    if (
        float(features.get("email_similarity", 0.0) or 0.0) >= 0.85
        and not features.get("tc_exact_match", 0)
        and not features.get("phone_exact_match", 0)
        and float(features.get("name_similarity", 0.0) or 0.0) < 0.80
    ):
        risk_flags.append("email_high_identity_weak")
    if (
        not features.get("tc_exact_match", 0)
        and not features.get("tc_conflict", 0)
        and not features.get("phone_exact_match", 0)
        and not features.get("email_exact_match", 0)
        and float(features.get("name_similarity", 0.0) or 0.0) >= 0.80
    ):
        risk_flags.append("weak_identity_evidence")
    if (
        not features.get("tc_exact_match", 0)
        and not features.get("tc_conflict", 0)
        and not features.get("phone_exact_match", 0)
        and not features.get("email_exact_match", 0)
        and not features.get("city_exact_match", 0)
    ):
        risk_flags.append("cross_city_contact_mismatch")
    if int(features.get("common_non_empty_fields", 0) or 0) <= 2:
        risk_flags.append("sparse_data")

    return risk_flags


def _build_rule_reasons(
    *,
    features: dict[str, Any],
    field_comparisons: dict[str, dict[str, Any]],
    probability: float,
    final_decision: str,
) -> list[str]:
    reasons: list[str] = []

    if features.get("tc_conflict", 0):
        reasons.append("TC Kimlik No catisiyor; otomatik birlestirme engellendi.")
    elif features.get("tc_exact_match", 0):
        reasons.append("TC Kimlik No tam eslesti.")

    if field_comparisons["fullName"]["comparisonResult"] in {"exact_match", "strong_match"}:
        reasons.append(
            f"Ad soyad karsilastirmasi {field_comparisons['fullName']['comparisonResult']} olarak degerlendirildi."
        )

    if features.get("phone_exact_match", 0):
        reasons.append("Telefon numarasi normalize edilmis sekilde eslesti.")
    if features.get("email_exact_match", 0):
        reasons.append("E-posta normalize edilmis anahtara gore eslesti.")
    if features.get("city_exact_match", 0):
        reasons.append("Sehir bilgisi eslesti.")
    if features.get("muhatap_no_exact_match", 0):
        reasons.append("Muhatap Kodu tam eslesti; guclu eslesme sinyali.")
    if features.get("muhatap_no_conflict", 0):
        reasons.append("Muhatap Kodu catisiyor; farkli kisi olabilir.")
    if features.get("shared_contact_name_conflict", 0):
        reasons.append("Ortak iletisim bilgisi var ancak isim sinyali catismali.")
    if features.get("household_risk_flag", 0):
        reasons.append("Ortak iletisim household riski olusturuyor.")
    if features.get("same_surname_name_conflict", 0):
        reasons.append("Soyad ayni ancak ad sinyali belirgin sekilde farkli.")
    if int(features.get("common_non_empty_fields", 0) or 0) <= 2:
        reasons.append("Bos alanlar nedeniyle guven dusuruldu.")

    reasons.append(f"Splink eslesme olasiligi: {probability:.4f}")

    if final_decision == "pending":
        reasons.append("Nihai karar manuel inceleme olarak birakildi.")
    elif final_decision == "rejected":
        reasons.append("Nihai karar farkli kisi yonunde.")
    elif final_decision == "approved":
        reasons.append("Nihai karar ayni kisi yonunde.")

    return reasons


def _build_payload(
    df_clean: pd.DataFrame,
    row: dict[str, Any],
    *,
    scoring_weights: dict[str, float] | None = None,
    decision_thresholds: DecisionThresholdsProb | None = None,
) -> dict[str, Any]:
    left_index = int(row["unique_id_l"])
    right_index = int(row["unique_id_r"])

    left_record = df_clean.loc[left_index].to_dict()
    right_record = df_clean.loc[right_index].to_dict()

    sw = scoring_weights
    dt = decision_thresholds
    if sw is None or dt is None:
        default_w, default_t = load_scoring_app_settings(None)
        sw = sw or default_w
        dt = dt or default_t

    field_comparisons = _build_field_comparisons(row, left_record, right_record)
    features = _derive_features_from_field_comparisons(
        left_record,
        right_record,
        field_comparisons,
    )
    splink_match_probability = _safe_float(row.get("match_probability"))
    # Splink (EM) ham olasılığı bazı durumlarda çatışma sinyallerine rağmen çok yüksek dönebilir.
    # UI'da yanıltıcı "skor %100" görünümünü engellemek için bazı çatışma tiplerinde tavan kırpılır.
    tc_conflict = int(features.get("tc_conflict", 0) or 0) == 1
    if tc_conflict:
        # TC çatışması = maksimum "pending" bandında kalmalı (0.40-0.79)
        # 0.80+ "approved" bandına girmesin
        adjusted_probability = min(splink_match_probability, 0.75)
    elif features.get("muhatap_no_conflict", 0):
        adjusted_probability = min(splink_match_probability, 0.85)
    else:
        adjusted_probability = splink_match_probability
    splink_match_probability = adjusted_probability
    splink_match_weight = _safe_float(row.get("match_weight"), default=0.0)
    final_decision, safety_overrides = resolve_match_decision_with_trace(
        splink_match_probability,
        features,
        thresholds=dt,
    )
    score_breakdown = compute_weighted_score_breakdown(features, sw)
    risk_flags = _build_risk_flags(features)
    decision_type = "auto"
    review_required = final_decision == "pending"
    if final_decision == "rejected" and "tc_conflict" in risk_flags and splink_match_probability >= 0.80:
        decision_reason = (
            "Benzerlik skoru yuksek ancak TC Kimlik No cakismasi nedeniyle otomatik birlestirme engellendi."
        )
    elif final_decision == "approved":
        decision_reason = "Guclu kimlik sinyalleri nedeniyle otomatik onaylandi."
    elif final_decision == "pending":
        decision_reason = "Skor ve kimlik sinyalleri manuel inceleme gerektiriyor."
    else:
        decision_reason = "Guven skoru ve kimlik sinyalleri yetersiz oldugu icin otomatik reddedildi."
    rule_reasons = _build_rule_reasons(
        features=features,
        field_comparisons=field_comparisons,
        probability=splink_match_probability,
        final_decision=final_decision,
    )
    rule_reasons.insert(0, decision_reason)

    return {
        "pairId": f"{left_index}-{right_index}",
        "left_index": left_index,
        "right_index": right_index,
        "record1": left_record,
        "record2": right_record,
        "features": features,
        "fieldComparisons": field_comparisons,
        "riskFlags": risk_flags,
        "ruleReasons": rule_reasons,
        "reasons": rule_reasons,
        "splinkMatchProbability": splink_match_probability,
        "splinkMatchWeight": splink_match_weight,
        "ml_probability": splink_match_probability,
        "decision": final_decision,
        "decision_type": decision_type,
        "review_required": review_required,
        "reason": decision_reason,
        "finalDecision": final_decision,
        "decisionSource": "splink_plus_rules",
        "final_score": score_breakdown["general_weighted_percent"],
        "score_source": "splink_plus_rules",
        "score_breakdown": score_breakdown,
        "applied_thresholds": dt.as_percent_dict(),
        "safety_overrides": safety_overrides,
    }


def _should_surface_low_probability_pair(
    df_clean: pd.DataFrame,
    row: dict[str, Any],
) -> bool:
    left_record = df_clean.loc[int(row["unique_id_l"])].to_dict()
    right_record = df_clean.loc[int(row["unique_id_r"])].to_dict()

    left_tc = _safe_str(left_record.get("clean_tc"))
    right_tc = _safe_str(right_record.get("clean_tc"))
    left_phone = _safe_str(left_record.get("clean_phone"))
    right_phone = _safe_str(right_record.get("clean_phone"))
    left_email = _safe_str(left_record.get("email_normalized_key"))
    right_email = _safe_str(right_record.get("email_normalized_key"))

    return bool(
        (left_tc and right_tc and left_tc == right_tc)
        or (left_phone and right_phone and left_phone == right_phone)
        or (left_email and right_email and left_email == right_email)
    )


def run_splink_detection(
    df_clean: pd.DataFrame,
    max_pairs: int = MAX_PAIRS,
    *,
    scoring_weights: dict[str, float] | None = None,
    decision_thresholds: DecisionThresholdsProb | None = None,
) -> list[dict]:
    """
    Uses Splink + DuckDB to generate candidate pairs and score probable duplicates.
    """
    if SPLINK_IMPORT_ERROR is not None:
        raise RuntimeError(f"Splink import failed: {SPLINK_IMPORT_ERROR}") from SPLINK_IMPORT_ERROR

    if df_clean.empty or len(df_clean) < 2:
        return DetectionResults([], candidate_pairs=0)

    effective_max_pairs = min(int(max_pairs), _max_pairs_limit())
    candidate_pairs, candidate_meta = generate_candidate_pairs(
        df_clean,
        max_pairs=effective_max_pairs,
        return_metadata=True,
    )
    total_candidate_pairs = len(candidate_pairs)
    bounded_candidate_pairs = min(total_candidate_pairs, effective_max_pairs)
    candidate_pairs_limited = bool(candidate_meta.get("limited", False))

    if total_candidate_pairs == 0:
        return DetectionResults([], candidate_pairs=0)

    if candidate_pairs_limited or total_candidate_pairs > effective_max_pairs:
        logger.warning(
            "Splink candidate pair estimate exceeded cap; total=%s cap=%s. "
            "Predictions will be trimmed after scoring.",
            total_candidate_pairs,
            effective_max_pairs,
        )

    df_input = _prepare_splink_input(df_clean)
    db_api = DuckDBAPI()

    comparisons = [
        ExactMatch("clean_tc").configure(term_frequency_adjustments=False),
        JaroWinklerAtThresholds("clean_name", [0.92, 0.80]),
        _rename_output_column(
            JaroWinklerAtThresholds("clean_first_name", [0.95, 0.85]),
            "first_name",
        ),
        _rename_output_column(
            JaroWinklerAtThresholds("clean_surname", [0.95, 0.85]),
            "surname",
        ),
        # Telefon: exact match yeterli (fuzzy post-processing'de yapılıyor)
        ExactMatch("clean_phone"),
        # Email: JaroWinkler ile fuzzy comparison (exact değil)
        _rename_output_column(
            JaroWinklerAtThresholds("email_normalized_key", [0.90, 0.70]),
            "email",
        ),
        ExactMatch("clean_city"),
        ExactMatch("name_phonetic_key"),
    ]

    settings = SettingsCreator(
        link_type="dedupe_only",
        unique_id_column_name="unique_id",
        blocking_rules_to_generate_predictions=[
            block_on("clean_tc"),
            block_on("clean_phone"),
            block_on("email_normalized_key"),
            block_on("name_phonetic_key"),
        ],
        comparisons=comparisons,
        retain_matching_columns=False,
        retain_intermediate_calculation_columns=True,
    )

    linker = Linker(df_input, settings, db_api=db_api, set_up_basic_logging=False)

    _estimate_u(linker, max_pairs=20_000)
    _estimate_prior(linker)
    _estimate_em(linker, block_on("clean_tc"), max_iterations=5)
    _estimate_em(linker, block_on("name_phonetic_key"), max_iterations=5)

    thresholded_predictions = _predict(
        linker,
        threshold_match_probability=PREDICTION_THRESHOLD,
    )
    predictions_df = thresholded_predictions.as_pandas_dataframe()

    if predictions_df.empty:
        predictions_df = pd.DataFrame()

    all_predictions_df = _predict(
        linker,
        threshold_match_probability=None,
    ).as_pandas_dataframe()
    if not all_predictions_df.empty:
        seen_pairs = {
            (int(row["unique_id_l"]), int(row["unique_id_r"]))
            for row in predictions_df.to_dict(orient="records")
        }
        supplemental_rows = [
            row
            for row in all_predictions_df.to_dict(orient="records")
            if (int(row["unique_id_l"]), int(row["unique_id_r"])) not in seen_pairs
            and _should_surface_low_probability_pair(df_clean, row)
        ]
        if supplemental_rows:
            predictions_df = pd.concat(
                [predictions_df, pd.DataFrame(supplemental_rows)],
                ignore_index=True,
            )

    if predictions_df.empty:
        return DetectionResults(
            [],
            candidate_pairs=bounded_candidate_pairs,
            candidate_pairs_total=total_candidate_pairs,
            candidate_pairs_limited=candidate_pairs_limited,
        )

    predictions_df = predictions_df.sort_values(
        by=["match_probability", "match_weight"],
        ascending=False,
        na_position="last",
    ).reset_index(drop=True)

    if len(predictions_df) > effective_max_pairs:
        predictions_df = predictions_df.head(effective_max_pairs).copy()
        candidate_pairs_limited = True

    payloads = [
        _build_payload(
            df_clean,
            row,
            scoring_weights=scoring_weights,
            decision_thresholds=decision_thresholds,
        )
        for row in predictions_df.to_dict(orient="records")
    ]

    return DetectionResults(
        payloads,
        candidate_pairs=bounded_candidate_pairs,
        candidate_pairs_total=total_candidate_pairs,
        candidate_pairs_limited=candidate_pairs_limited,
    )
