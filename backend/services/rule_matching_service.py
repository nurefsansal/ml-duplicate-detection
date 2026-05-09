from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from backend.schemas.requests import RecordIn
from backend.services.blocking_service import generate_candidate_pairs
from backend.services.feature_service import (
    build_pair_features,
    email_similarity_score,
    phone_similarity_score,
)
from backend.services.ml_service import predict_match_probability
from backend.services.normalization_service import (
    canonical_name,
    metaphone_name_key,
    normalize_email_key,
    phonetic_name_key,
    to_dataframe,
)
from backend.services.resolution_service import resolve_match_decision_with_trace
from backend.services.decision_thresholds import DecisionThresholdsProb
from backend.services.scoring_app_settings import (
    compute_weighted_score_breakdown,
    load_scoring_app_settings,
)
from backend.services.database_service import (
    MatchService,
    NormalizedDonorService,
    RawDonorService,
    UploadService,
)
from backend.services.splink_service import DetectionResults, run_splink_detection

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db"

_TR_MAP = str.maketrans(
    {
        "İ": "I",
        "I": "I",
        "Ğ": "G",
        "Ü": "U",
        "Ş": "S",
        "Ö": "O",
        "Ç": "C",
        "ı": "I",
        "ğ": "G",
        "ü": "U",
        "ş": "S",
        "ö": "O",
        "ç": "C",
        "Þ": "S",
        "þ": "S",
    }
)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _normalise_mapping_key(value: str) -> str:
    text = str(value or "")
    for source, target in {
        "Å": "S",
        "ÅŸ": "s",
        "Ã": "S",
        "Ã¾": "s",
        "Ä": "G",
        "ÄŸ": "g",
        "Ãœ": "U",
        "Ã¼": "u",
        "Ã–": "O",
        "Ã¶": "o",
        "Ã‡": "C",
        "Ã§": "c",
        "Ä°": "I",
        "Ä±": "i",
    }.items():
        text = text.replace(source, target)
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _pick_mapping_value(mapping: dict[str, Any], *aliases: str) -> str:
    actual_keys = {_normalise_mapping_key(key): key for key in mapping.keys()}
    for alias in aliases:
        actual_key = actual_keys.get(_normalise_mapping_key(alias))
        if actual_key is None:
            continue
        value = _safe_str(mapping.get(actual_key))
        if value:
            return value
    return ""


def _normalise_column_name(value: str) -> str:
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
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _series_or_blank(df: pd.DataFrame, *aliases: str) -> pd.Series:
    normalised_to_actual = {
        _normalise_column_name(column): column for column in df.columns
    }
    for alias in aliases:
        actual = normalised_to_actual.get(_normalise_column_name(alias))
        if actual is not None:
            return df[actual]
    return pd.Series([""] * len(df), index=df.index, dtype="object")


def _pick_row_value(row: pd.Series, *aliases: str) -> str:
    normalised_to_actual = {
        _normalise_column_name(column): column for column in row.index
    }
    for alias in aliases:
        actual = normalised_to_actual.get(_normalise_column_name(alias))
        if actual is None:
            continue
        value = row.get(actual)
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _normalise_tr_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return ""

    text = str(value).strip().upper().translate(_TR_MAP)
    text = re.sub(r"[^A-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_phone(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return ""

    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return ""
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def _clean_tc(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return ""
    return re.sub(r"\D", "", str(value))


def _clean_email(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return ""
    return re.sub(r"\s+", "", str(value)).lower()


def _prepare_clean_dataframe(records: list[RecordIn]) -> pd.DataFrame:
    df_raw = to_dataframe(records)
    df_clean = df_raw.copy()

    name_series = _series_or_blank(df_raw, "Ad Soyad", "adSoyad", "name", "full_name")
    tc_series = _series_or_blank(df_raw, "TC", "tcKimlikNo", "tc")
    phone_series = _series_or_blank(df_raw, "Telefon", "telefon", "phone", "mobile")
    email_series = _series_or_blank(df_raw, "E-mail", "email", "mail")
    city_series = _series_or_blank(df_raw, "Sehir", "Şehir", "city")

    ordered_names = name_series.apply(_normalise_tr_text)

    df_clean["clean_name_ordered"] = ordered_names
    df_clean["clean_name"] = ordered_names.apply(canonical_name)
    df_clean["clean_first_name"] = ordered_names.apply(
        lambda value: _split_name_parts(value)[0]
    )
    df_clean["clean_surname"] = ordered_names.apply(
        lambda value: _split_name_parts(value)[1]
    )
    df_clean["clean_city"] = city_series.apply(_normalise_tr_text)
    df_clean["clean_phone"] = phone_series.apply(_clean_phone)
    df_clean["clean_tc"] = tc_series.apply(_clean_tc)
    df_clean["clean_email"] = email_series.apply(_clean_email)
    df_clean["name_phonetic_key"] = df_clean["clean_name"].apply(phonetic_name_key)
    df_clean["name_metaphone_key"] = df_clean["clean_name"].apply(metaphone_name_key)
    df_clean["email_normalized_key"] = df_clean["clean_email"].apply(normalize_email_key)

    return df_clean


# def _build_record_pair_payload(df_clean, row):
#     Legacy matcher payload builder intentionally kept commented during the
#     Splink migration. The active pipeline now builds payloads either inside
#     `run_splink_detection()` or via `_build_legacy_payload()` below.


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
    if int(features.get("common_non_empty_fields", 0) or 0) <= 2:
        risk_flags.append("sparse_data")

    return risk_flags


def _comparison_result_from_score(score: float, exact_match: bool) -> str:
    if exact_match:
        return "exact_match"
    if score >= 0.9:
        return "strong_match"
    if score >= 0.7:
        return "partial_match"
    if score > 0:
        return "mismatch"
    return "missing"


def _build_fallback_exact_comparison(
    *,
    raw_left_value: str,
    raw_right_value: str,
    normalized_left_value: str,
    normalized_right_value: str,
    exact_match: bool,
    comparison_method: str,
    field_name: str,
    notes: str,
    use_conflict_label: bool = False,
) -> dict[str, Any]:
    if not normalized_left_value and not normalized_right_value:
        result = "missing"
        final_notes = f"{field_name} her iki kayitta da bos."
        score = 0
        exact = False
    elif not normalized_left_value or not normalized_right_value:
        result = "missing"
        final_notes = f"{field_name} alanlarindan biri bos."
        score = 0
        exact = False
    else:
        exact = bool(exact_match)
        score = 100 if exact else 0
        if exact:
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
        "exactMatch": exact,
        "notes": final_notes,
    }


def _build_fallback_similarity_comparison(
    *,
    raw_left_value: str,
    raw_right_value: str,
    normalized_left_value: str,
    normalized_right_value: str,
    score: float,
    exact_match: bool,
    comparison_method: str,
    field_name: str,
) -> dict[str, Any]:
    if not normalized_left_value and not normalized_right_value:
        result = "missing"
        score_percent = 0
        notes = f"{field_name} her iki kayitta da bos."
        exact = False
    elif not normalized_left_value or not normalized_right_value:
        result = "missing"
        score_percent = 0
        notes = f"{field_name} alanlarindan biri bos."
        exact = False
    else:
        exact = bool(exact_match)
        score_percent = int(round(max(0.0, min(1.0, float(score or 0.0))) * 100))
        result = _comparison_result_from_score(float(score or 0.0), exact)
        if result == "exact_match":
            notes = f"{field_name} fallback karsilastirmasinda birebir eslesti."
        elif result == "strong_match":
            notes = f"{field_name} fallback karsilastirmasinda guclu benzerlik gosteriyor."
        elif result == "partial_match":
            notes = f"{field_name} fallback karsilastirmasinda kismi benzerlik gosteriyor."
        else:
            notes = f"{field_name} fallback karsilastirmasinda farkli gorunuyor."

    return {
        "rawLeftValue": raw_left_value or None,
        "rawRightValue": raw_right_value or None,
        "normalizedLeftValue": normalized_left_value or None,
        "normalizedRightValue": normalized_right_value or None,
        "comparisonMethod": comparison_method,
        "comparisonResult": result,
        "score0To100": score_percent,
        "exactMatch": exact,
        "notes": notes,
    }


def _build_fallback_contact_similarity_comparison(
    *,
    raw_left_value: str,
    raw_right_value: str,
    normalized_left_value: str,
    normalized_right_value: str,
    similarity_score: float,
    exact_match: bool,
    comparison_method: str,
    field_name: str,
) -> dict[str, Any]:
    if not normalized_left_value and not normalized_right_value:
        result = "missing"
        score_percent = 0
        notes = f"{field_name} her iki kayitta da bos."
        exact = False
    elif not normalized_left_value or not normalized_right_value:
        result = "missing"
        score_percent = 0
        notes = f"{field_name} alanlarindan biri bos."
        exact = False
    else:
        exact = bool(exact_match)
        bounded_score = max(0.0, min(1.0, float(similarity_score or 0.0)))
        score_percent = 100 if exact else int(round(bounded_score * 100))
        if exact:
            result = "exact_match"
            notes = f"{field_name} fallback karsilastirmasinda birebir eslesti."
        elif bounded_score >= 0.85:
            result = "strong_match"
            notes = f"{field_name} fallback karsilastirmasinda guclu benzerlik gosteriyor."
        elif bounded_score >= 0.60:
            result = "partial_match"
            notes = f"{field_name} fallback karsilastirmasinda kismi benzerlik gosteriyor."
        elif bounded_score >= 0.20:
            result = "weak_match"
            notes = f"{field_name} fallback karsilastirmasinda zayif benzerlik gosteriyor."
        else:
            result = "mismatch"
            notes = f"{field_name} fallback karsilastirmasinda farkli gorunuyor."

    return {
        "rawLeftValue": raw_left_value or None,
        "rawRightValue": raw_right_value or None,
        "normalizedLeftValue": normalized_left_value or None,
        "normalizedRightValue": normalized_right_value or None,
        "comparisonMethod": comparison_method,
        "comparisonResult": result,
        "score0To100": score_percent,
        "exactMatch": exact,
        "notes": notes,
    }


def _build_legacy_field_comparisons(
    left_record: dict[str, Any],
    right_record: dict[str, Any],
    features: dict[str, Any],
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

    left_full_name = _safe_str(left_record.get("clean_name"))
    right_full_name = _safe_str(right_record.get("clean_name"))
    left_first_name = _safe_str(left_record.get("clean_first_name"))
    right_first_name = _safe_str(right_record.get("clean_first_name"))
    left_surname = _safe_str(left_record.get("clean_surname"))
    right_surname = _safe_str(right_record.get("clean_surname"))
    left_clean_phone = _safe_str(left_record.get("clean_phone"))
    right_clean_phone = _safe_str(right_record.get("clean_phone"))
    left_clean_email = _safe_str(left_record.get("clean_email"))
    right_clean_email = _safe_str(right_record.get("clean_email"))
    left_email_key = _safe_str(left_record.get("email_normalized_key"))
    right_email_key = _safe_str(right_record.get("email_normalized_key"))
    left_clean_address = _safe_str(left_record.get("clean_address"))
    right_clean_address = _safe_str(right_record.get("clean_address"))

    phone_similarity = phone_similarity_score(left_clean_phone, right_clean_phone)
    email_similarity_clean = email_similarity_score(left_clean_email, right_clean_email)
    email_similarity_key = email_similarity_score(left_email_key, right_email_key)
    email_similarity = max(email_similarity_clean, email_similarity_key)

    return {
        "fullName": _build_fallback_similarity_comparison(
            raw_left_value=raw_left_name,
            raw_right_value=raw_right_name,
            normalized_left_value=left_full_name,
            normalized_right_value=right_full_name,
            score=float(features.get("name_jaro_winkler", 0.0) or 0.0),
            exact_match=left_full_name == right_full_name and bool(left_full_name),
            comparison_method="legacy_hybrid_jaro_token_similarity(clean_name)",
            field_name="Ad soyad",
        ),
        "firstName": _build_fallback_similarity_comparison(
            raw_left_value=_split_name_parts(raw_left_name)[0],
            raw_right_value=_split_name_parts(raw_right_name)[0],
            normalized_left_value=left_first_name,
            normalized_right_value=right_first_name,
            score=float(features.get("first_name_jaro_winkler", 0.0) or 0.0),
            exact_match=bool(features.get("first_name_exact_match", 0)),
            comparison_method="legacy_jaro_winkler(clean_first_name)",
            field_name="Ad",
        ),
        "surname": _build_fallback_similarity_comparison(
            raw_left_value=_split_name_parts(raw_left_name)[1],
            raw_right_value=_split_name_parts(raw_right_name)[1],
            normalized_left_value=left_surname,
            normalized_right_value=right_surname,
            score=float(features.get("surname_jaro_winkler", 0.0) or 0.0),
            exact_match=bool(features.get("surname_exact_match", 0)),
            comparison_method="legacy_jaro_winkler(clean_surname)",
            field_name="Soyad",
        ),
        "tc": _build_fallback_exact_comparison(
            raw_left_value=raw_left_tc,
            raw_right_value=raw_right_tc,
            normalized_left_value=_safe_str(left_record.get("clean_tc")),
            normalized_right_value=_safe_str(right_record.get("clean_tc")),
            exact_match=bool(features.get("tc_exact_match", 0)),
            comparison_method="legacy_exact_match(clean_tc)",
            field_name="TC Kimlik No",
            notes="TC Kimlik No fallback karsilastirmasinda eslesti.",
            use_conflict_label=True,
        ),
        "phone": _build_fallback_contact_similarity_comparison(
            raw_left_value=raw_left_phone,
            raw_right_value=raw_right_phone,
            normalized_left_value=left_clean_phone,
            normalized_right_value=right_clean_phone,
            similarity_score=phone_similarity,
            exact_match=bool(features.get("phone_exact_match", 0)),
            comparison_method="legacy_tiered_phone_similarity(clean_phone)",
            field_name="Telefon",
        ),
        "email": _build_fallback_contact_similarity_comparison(
            raw_left_value=raw_left_email,
            raw_right_value=raw_right_email,
            normalized_left_value=left_email_key or left_clean_email,
            normalized_right_value=right_email_key or right_clean_email,
            similarity_score=email_similarity,
            exact_match=bool(features.get("email_exact_match", 0)),
            comparison_method="legacy_hybrid_email_similarity(clean_email+email_normalized_key)",
            field_name="E-posta",
        ),
        "city": _build_fallback_exact_comparison(
            raw_left_value=raw_left_city,
            raw_right_value=raw_right_city,
            normalized_left_value=_safe_str(left_record.get("clean_city")),
            normalized_right_value=_safe_str(right_record.get("clean_city")),
            exact_match=bool(features.get("city_exact_match", 0)),
            comparison_method="legacy_exact_match(clean_city)",
            field_name="Sehir",
            notes="Sehir fallback karsilastirmasinda eslesti.",
        ),
        "address": _build_fallback_similarity_comparison(
            raw_left_value=_pick_mapping_value(left_record, "Adres", "adres", "address"),
            raw_right_value=_pick_mapping_value(right_record, "Adres", "adres", "address"),
            normalized_left_value=left_clean_address,
            normalized_right_value=right_clean_address,
            score=float(features.get("address_similarity", 0.0) or 0.0),
            exact_match=bool(left_clean_address and left_clean_address == right_clean_address),
            comparison_method="legacy_jaro_winkler(clean_address)",
            field_name="Adres",
        ),
        "muhatapNo": _build_fallback_exact_comparison(
            raw_left_value=_pick_mapping_value(left_record, "Muhatap No", "muhatap_no", "muhatap kodu", "customer_id"),
            raw_right_value=_pick_mapping_value(right_record, "Muhatap No", "muhatap_no", "muhatap kodu", "customer_id"),
            normalized_left_value=_safe_str(left_record.get("clean_muhatap_no")),
            normalized_right_value=_safe_str(right_record.get("clean_muhatap_no")),
            exact_match=bool(features.get("muhatap_no_exact_match", 0)),
            comparison_method="legacy_exact_match(clean_muhatap_no)",
            field_name="Muhatap Kodu",
            notes="Muhatap Kodu fallback karsilastirmasinda eslesti.",
            use_conflict_label=True,
        ),
    }


def _build_rule_reasons(
    *,
    features: dict[str, Any],
    field_comparisons: dict[str, dict[str, Any]],
    probability: float,
    final_decision: str,
    source: str,
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
        reasons.append("Telefon eslesti.")
    if features.get("email_exact_match", 0):
        reasons.append("E-posta eslesti.")
    if features.get("city_exact_match", 0):
        reasons.append("Sehir eslesti.")
    if features.get("muhatap_no_exact_match", 0):
        reasons.append("Muhatap Kodu tam eslesti; guclu eslesme sinyali.")
    if features.get("muhatap_no_conflict", 0):
        reasons.append("Muhatap Kodu catisiyor; farkli kisi olabilir.")
    if features.get("shared_contact_name_conflict", 0):
        reasons.append("Ortak iletisim var ancak isim sinyali catismali.")
    if features.get("household_risk_flag", 0):
        reasons.append("Household riski tespit edildi.")
    if features.get("same_surname_name_conflict", 0):
        reasons.append("Soyad ayni ancak ad sinyali belirgin sekilde farkli.")
    if int(features.get("common_non_empty_fields", 0) or 0) <= 2:
        reasons.append("Bos alanlar nedeniyle guven dusuruldu.")

    reasons.append(f"Eslesme olasiligi: {probability:.4f}")

    if source == "fallback_legacy":
        reasons.append("Splink kullanilamadi; legacy fallback devrede.")

    if final_decision == "pending":
        reasons.append("Nihai karar manuel inceleme olarak birakildi.")
    elif final_decision == "rejected":
        reasons.append("Nihai karar farkli kisi yonunde.")
    elif final_decision == "approved":
        reasons.append("Nihai karar ayni kisi yonunde.")

    return reasons


def _build_legacy_payload(
    df_clean: pd.DataFrame,
    left_idx: int,
    right_idx: int,
    *,
    scoring_weights: dict[str, float] | None = None,
    decision_thresholds: DecisionThresholdsProb | None = None,
) -> dict:
    left_record = df_clean.loc[left_idx].to_dict()
    right_record = df_clean.loc[right_idx].to_dict()

    sw = scoring_weights
    dt = decision_thresholds
    if sw is None or dt is None:
        default_w, default_t = load_scoring_app_settings(None)
        sw = sw or default_w
        dt = dt or default_t

    features = build_pair_features(left_record, right_record)
    ml_probability = predict_match_probability(features)
    final_decision, safety_overrides = resolve_match_decision_with_trace(
        ml_probability,
        features,
        thresholds=dt,
    )
    score_breakdown = compute_weighted_score_breakdown(features, sw)
    if final_decision == "rejected" and features.get("tc_conflict", 0) and ml_probability >= 0.80:
        decision_reason = (
            "Benzerlik skoru yuksek ancak TC Kimlik No cakismasi nedeniyle otomatik birlestirme engellendi."
        )
    elif final_decision == "approved":
        decision_reason = "Guclu kimlik sinyalleri nedeniyle otomatik onaylandi."
    elif final_decision == "pending":
        decision_reason = "Skor ve kimlik sinyalleri manuel inceleme gerektiriyor."
    else:
        decision_reason = "Guven skoru ve kimlik sinyalleri yetersiz oldugu icin otomatik reddedildi."
    field_comparisons = _build_legacy_field_comparisons(
        left_record,
        right_record,
        features,
    )
    risk_flags = _build_risk_flags(features)
    rule_reasons = _build_rule_reasons(
        features=features,
        field_comparisons=field_comparisons,
        probability=ml_probability,
        final_decision=final_decision,
        source="fallback_legacy",
    )
    rule_reasons.insert(0, decision_reason)

    return {
        "pairId": f"{int(left_idx)}-{int(right_idx)}",
        "left_index": int(left_idx),
        "right_index": int(right_idx),
        "record1": left_record,
        "record2": right_record,
        "features": features,
        "fieldComparisons": field_comparisons,
        "riskFlags": risk_flags,
        "ruleReasons": rule_reasons,
        "reasons": rule_reasons,
        "splinkMatchProbability": ml_probability,
        "splinkMatchWeight": None,
        "ml_probability": ml_probability,
        "decision": final_decision,
        "decision_type": "auto",
        "review_required": final_decision == "pending",
        "reason": decision_reason,
        "finalDecision": final_decision,
        "decisionSource": "fallback_legacy",
        "final_score": score_breakdown["general_weighted_percent"],
        "score_source": "fallback_legacy",
        "score_breakdown": score_breakdown,
        "applied_thresholds": dt.as_percent_dict(),
        "safety_overrides": safety_overrides,
    }


def _legacy_rules_matched(features: dict) -> int:
    return sum(
        [
            int(float(features.get("name_jaro_winkler", 0.0) or 0.0) >= 0.85),
            int(features.get("tc_exact_match", 0) or 0),
            int(features.get("phone_exact_match", 0) or 0),
            int(features.get("email_exact_match", 0) or 0),
        ]
    )


def _legacy_detection(
    df_clean: pd.DataFrame,
    min_rules_to_match: int,
    *,
    scoring_weights: dict[str, float] | None = None,
    decision_thresholds: DecisionThresholdsProb | None = None,
) -> DetectionResults:
    candidate_pairs, candidate_meta = generate_candidate_pairs(
        df_clean,
        return_metadata=True,
    )
    duplicates: list[dict] = []

    for left_idx, right_idx in candidate_pairs:
        payload = _build_legacy_payload(
            df_clean,
            int(left_idx),
            int(right_idx),
            scoring_weights=scoring_weights,
            decision_thresholds=decision_thresholds,
        )
        rules_matched = _legacy_rules_matched(payload["features"])

        if rules_matched >= min_rules_to_match or float(payload["ml_probability"]) >= 0.30:
            duplicates.append(payload)

    duplicates.sort(
        key=lambda item: (
            float(item.get("ml_probability", 0.0) or 0.0),
            float(item.get("features", {}).get("name_similarity", 0.0) or 0.0),
        ),
        reverse=True,
    )

    return DetectionResults(
        duplicates,
        candidate_pairs=len(candidate_pairs),
        candidate_pairs_total=len(candidate_pairs),
        candidate_pairs_limited=bool(candidate_meta.get("limited", False)),
    )


def _get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def _create_db_engine() -> Engine:
    return create_engine(_get_database_url(), pool_pre_ping=True)


def _split_name_parts(name: str) -> tuple[str, str]:
    value = str(name or "").strip()
    if not value:
        return "", ""

    parts = [part for part in value.split(" ") if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def _persist_detection_flow(
    *,
    records: list[RecordIn],
    df_clean: pd.DataFrame,
    enriched_duplicates: list[dict],
    session_id: str,
) -> tuple[int, int]:
    """
    Persists detection workflow to normalized schema:
    uploads -> raw_donors -> normalized_donors -> matches
    """
    engine = _create_db_engine()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        upload = UploadService.create_upload(
            db,
            file_name=f"detect_{session_id}.json",
            file_size_bytes=0,
            created_by="api_detect",
        )
        UploadService.update_upload_status(db, upload.id, "processing")

        index_to_norm_id: dict[int, int] = {}

        for row_number, (idx, row) in enumerate(df_clean.iterrows(), start=1):
            normalized_full_name = str(
                row.get("clean_name_ordered", row.get("clean_name", "")) or ""
            )
            first_name, last_name = _split_name_parts(normalized_full_name)

            raw = RawDonorService.create_raw_donor(
                db,
                upload_id=upload.id,
                row_number=row_number,
                full_name=_pick_row_value(row, "Ad Soyad", "adSoyad", "name", "full_name"),
                email=_pick_row_value(row, "E-mail", "email", "mail"),
                phone=_pick_row_value(row, "Telefon", "telefon", "phone", "mobile"),
                city=_pick_row_value(row, "Sehir", "Şehir", "city"),
            )

            norm = NormalizedDonorService.create_normalized_donor(
                db,
                upload_id=upload.id,
                raw_id=raw.id,
                full_name=normalized_full_name,
                first_name=first_name,
                last_name=last_name,
                email=str(row.get("clean_email", "") or ""),
                phone=str(row.get("clean_phone", "") or ""),
                city=str(row.get("clean_city", "") or ""),
                clean_tc=str(row.get("clean_tc", "") or ""),
                clean_phone=str(row.get("clean_phone", "") or ""),
                clean_email=str(row.get("clean_email", "") or ""),
                clean_city=str(row.get("clean_city", "") or ""),
                email_normalized_key=str(row.get("email_normalized_key", "") or ""),
                name_phonetic_key=str(row.get("name_phonetic_key", "") or ""),
            )

            index_to_norm_id[int(idx)] = int(norm.id)

        matches_data: list[dict] = []
        for payload in enriched_duplicates:
            left_idx = int(payload.get("left_index", -1))
            right_idx = int(payload.get("right_index", -1))

            left_norm_id = index_to_norm_id.get(left_idx)
            right_norm_id = index_to_norm_id.get(right_idx)
            if left_norm_id is None or right_norm_id is None:
                continue

            features = payload.get("features", {}) or {}
            ml_prob = float(payload.get("ml_probability", 0.0) or 0.0)
            persisted_feature_payload = {
                "features": features,
                "fieldComparisons": payload.get("fieldComparisons", {}) or {},
                "riskFlags": payload.get("riskFlags", []) or [],
                "ruleReasons": payload.get("ruleReasons", payload.get("reasons", [])) or [],
                "decisionSource": str(payload.get("decisionSource", "fallback_legacy")),
                "finalDecision": str(payload.get("finalDecision", payload.get("decision", "review"))),
                "splinkMatchProbability": float(
                    payload.get("splinkMatchProbability", ml_prob) or ml_prob
                ),
                "splinkMatchWeight": payload.get("splinkMatchWeight"),
                "pairId": str(payload.get("pairId", f"{left_idx}-{right_idx}")),
                "leftIndex": left_idx,
                "rightIndex": right_idx,
            }
            similarity_value = float(features.get("name_similarity", 0.0) or 0.0)
            if payload.get("fieldComparisons"):
                similarity_value = float(
                    (
                        (payload.get("fieldComparisons", {}) or {})
                        .get("fullName", {})
                        .get("score0To100", 0)
                    )
                    or 0
                ) / 100

            matches_data.append(
                {
                    "donor1_id": left_norm_id,
                    "donor2_id": right_norm_id,
                    "similarity": similarity_value,
                    "ml_score": ml_prob,
                    "confidence": ml_prob,
                    "features": persisted_feature_payload,
                    "decision_reason": str(payload.get("decision", "review")),
                }
            )

        if matches_data:
            MatchService.create_matches_batch(db, upload.id, matches_data)

        UploadService.update_total_records(db, upload.id, len(records))
        UploadService.update_upload_status(db, upload.id, "completed")
        db.commit()

        return int(upload.id), len(matches_data)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def detect_core(
    records: list[RecordIn],
    min_rules_to_match: int,
    save_to_db: bool,
    session_id: str | None,
):
    from backend.services.detection_service import detect_core as detect_via_database

    return detect_via_database(
        records=records,
        min_rules_to_match=min_rules_to_match,
        save_to_db=save_to_db,
        session_id=session_id,
    )
