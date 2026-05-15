from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, inspect as sa_inspect, or_, text
from sqlalchemy.orm import Session, joinedload

from backend.models.database import (
    AuditLog,
    AppSettings,
    DetectionRun,
    Entity,
    EntityMembership,
    MatchCandidate,
    NormalizedRecord,
    ReviewAction,
)
from backend.services.advanced_matching_service import (
    hybrid_name_similarity,
    jaro_winkler_similarity,
    same_surname_name_conflict,
    token_name_similarity,
)
from backend.services.feature_service import email_similarity_score, phone_similarity_score
from backend.services.ml_feature_schema import (
    CANONICAL_ML_MODEL_FEATURE_COLUMNS,
    extract_canonical_ml_features,
)
from backend.services.ml_service import get_latest_review_labels_by_match_id, predict_match_probability
from backend.services.resolution_service import resolve_match_decision_with_trace
from backend.services.scoring_app_settings import compute_weighted_score_breakdown, load_scoring_app_settings


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_decision(value: str) -> str:
    normalized = _safe_str(value).lower()
    if normalized in {"approved", "same_person"}:
        return "approved"
    if normalized in {"rejected", "different_person"}:
        return "rejected"
    return "pending"


def _decision_type_for_candidate(decision: str, match_type: str) -> str:
    normalized_decision = _normalize_decision(decision)
    if normalized_decision == "pending":
        return "manual"
    source = _safe_str(match_type).lower()
    if "manual" in source:
        return "manual"
    return "auto"


def _normalise_mapping_key(value: str) -> str:
    text = str(value or "")
    for source, target in {
        "Ã…Â": "S",
        "Ã…Å¸": "s",
        "Å": "S",
        "ÅŸ": "s",
        "ÃƒÂ": "S",
        "ÃƒÂ¾": "s",
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


def _pick_payload_value(payloads: list[dict[str, Any]], *aliases: str) -> str:
    actual_keys: dict[str, str] = {}
    merged: dict[str, Any] = {}

    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        merged.update(payload)
        for key in payload.keys():
            actual_keys[_normalise_mapping_key(str(key))] = str(key)

    for alias in aliases:
        actual_key = actual_keys.get(_normalise_mapping_key(alias))
        if actual_key is None:
            continue
        value = _safe_str(merged.get(actual_key))
        if value:
            return value

    return ""


def _normalized_payload(record: NormalizedRecord) -> dict[str, Any]:
    return record.normalized_payload if isinstance(record.normalized_payload, dict) else {}


def _raw_payload(record: NormalizedRecord) -> dict[str, Any]:
    if record.raw_record is None:
        return {}
    return record.raw_record.raw_payload if isinstance(record.raw_record.raw_payload, dict) else {}


def _record_raw_name(record: NormalizedRecord) -> str:
    return _pick_payload_value(
        [_raw_payload(record), _normalized_payload(record)],
        "Ad Soyad",
        "adSoyad",
        "name",
        "fullName",
        "full_name",
    )


def _record_raw_phone(record: NormalizedRecord) -> str:
    return _pick_payload_value(
        [_raw_payload(record), _normalized_payload(record)],
        "Telefon",
        "telefon",
        "phone",
        "mobile",
    )


def _record_raw_email(record: NormalizedRecord) -> str:
    return _pick_payload_value(
        [_raw_payload(record), _normalized_payload(record)],
        "E-mail",
        "email",
        "mail",
    )


def _record_raw_tc(record: NormalizedRecord) -> str:
    return _pick_payload_value(
        [_raw_payload(record), _normalized_payload(record)],
        "TC",
        "tcKimlikNo",
        "tc",
        "identity",
        "idNumber",
    )


def _record_raw_city(record: NormalizedRecord) -> str:
    return _pick_payload_value(
        [_raw_payload(record), _normalized_payload(record)],
        "Sehir",
        "Şehir",
        "Åehir",
        "city",
        "sehir",
    )


def _record_raw_muhatap(record: NormalizedRecord) -> str:
    explicit = _safe_str(record.clean_muhatap_no) if hasattr(record, "clean_muhatap_no") else ""
    if explicit:
        return explicit
    return _pick_payload_value(
        [_raw_payload(record), _normalized_payload(record)],
        "Muhatap No",
        "muhatap_no",
        "muhatap kodu",
        "customer_id",
    )


def _record_group_muhatap_code(record: NormalizedRecord) -> str:
    explicit = _safe_str(record.clean_muhatap_no) if hasattr(record, "clean_muhatap_no") else ""
    if explicit:
        return explicit

    normalized_payload = _normalized_payload(record)
    return (
        _safe_str(normalized_payload.get("clean_muhatap_no"))
        or _safe_str(normalized_payload.get("muhatap_no"))
        or _safe_str(normalized_payload.get("Muhatap No"))
    )


def _split_name(name: str) -> tuple[str, str]:
    parts = [part for part in _safe_str(name).split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def _comparison_result_from_similarity(score: float) -> str:
    if score >= 1.0:
        return "exact_match"
    if score >= 0.92:
        return "strong_match"
    if score >= 0.80:
        return "partial_match"
    return "mismatch"


def _build_exact_field_comparison(
    *,
    raw_left: str,
    raw_right: str,
    normalized_left: str,
    normalized_right: str,
    comparison_method: str,
    field_name: str,
    use_conflict_label: bool = False,
) -> dict[str, Any]:
    if not normalized_left and not normalized_right:
        result = "missing"
        score = 0
        exact_match = False
        notes = f"{field_name} her iki kayitta da bos."
    elif not normalized_left or not normalized_right:
        result = "missing"
        score = 0
        exact_match = False
        notes = f"{field_name} alanlarindan biri bos."
    else:
        exact_match = normalized_left == normalized_right
        score = 100 if exact_match else 0
        if exact_match:
            result = "exact_match"
            notes = f"{field_name} normalize edilmis degerlerle birebir eslesti."
        else:
            result = "conflict" if use_conflict_label else "mismatch"
            notes = f"{field_name} normalize edilmis degerleri farkli."

    return {
        "rawLeftValue": raw_left or None,
        "rawRightValue": raw_right or None,
        "normalizedLeftValue": normalized_left or None,
        "normalizedRightValue": normalized_right or None,
        "comparisonMethod": comparison_method,
        "comparisonResult": result,
        "score0To100": score,
        "exactMatch": exact_match,
        "notes": notes,
    }


def _build_similarity_field_comparison(
    *,
    raw_left: str,
    raw_right: str,
    normalized_left: str,
    normalized_right: str,
    comparison_method: str,
    field_name: str,
    use_token_hybrid: bool = False,
) -> dict[str, Any]:
    if not normalized_left and not normalized_right:
        similarity = 0.0
        result = "missing"
        notes = f"{field_name} her iki kayitta da bos."
    elif not normalized_left or not normalized_right:
        similarity = 0.0
        result = "missing"
        notes = f"{field_name} alanlarindan biri bos."
    else:
        similarity = (
            hybrid_name_similarity(normalized_left, normalized_right)
            if use_token_hybrid
            else jaro_winkler_similarity(normalized_left, normalized_right)
        )
        result = _comparison_result_from_similarity(similarity)
        if result == "exact_match":
            notes = f"{field_name} normalize edilmis sekilde birebir eslesti."
        elif result == "strong_match":
            notes = f"{field_name} guclu benzerlik gosteriyor."
        elif result == "partial_match":
            notes = f"{field_name} kismi benzerlik gosteriyor."
        else:
            notes = f"{field_name} alanlari farkli gorunuyor."

    return {
        "rawLeftValue": raw_left or None,
        "rawRightValue": raw_right or None,
        "normalizedLeftValue": normalized_left or None,
        "normalizedRightValue": normalized_right or None,
        "comparisonMethod": comparison_method,
        "comparisonResult": result,
        "score0To100": int(round(similarity * 100)),
        "exactMatch": bool(normalized_left and normalized_left == normalized_right),
        "notes": notes,
    }


def _build_contact_similarity_field_comparison(
    *,
    raw_left: str,
    raw_right: str,
    normalized_left: str,
    normalized_right: str,
    similarity_score: float,
    exact_match: bool,
    comparison_method: str,
    field_name: str,
) -> dict[str, Any]:
    if not normalized_left and not normalized_right:
        result = "missing"
        notes = f"{field_name} her iki kayitta da bos."
        score_percent = 0
        exact = False
    elif not normalized_left or not normalized_right:
        result = "missing"
        notes = f"{field_name} alanlarindan biri bos."
        score_percent = 0
        exact = False
    else:
        exact = bool(exact_match)
        bounded = max(0.0, min(1.0, float(similarity_score or 0.0)))
        score_percent = 100 if exact else int(round(bounded * 100))
        if exact:
            result = "exact_match"
            notes = f"{field_name} birebir eslesti."
        elif bounded >= 0.85:
            result = "strong_match"
            notes = f"{field_name} guclu benzerlik gosteriyor."
        elif bounded >= 0.60:
            result = "partial_match"
            notes = f"{field_name} kismi benzerlik gosteriyor."
        elif bounded >= 0.20:
            result = "weak_match"
            notes = f"{field_name} zayif benzerlik gosteriyor."
        else:
            result = "mismatch"
            notes = f"{field_name} belirgin sekilde farkli."

    return {
        "rawLeftValue": raw_left or None,
        "rawRightValue": raw_right or None,
        "normalizedLeftValue": normalized_left or None,
        "normalizedRightValue": normalized_right or None,
        "comparisonMethod": comparison_method,
        "comparisonResult": result,
        "score0To100": score_percent,
        "exactMatch": exact,
        "notes": notes,
    }


def _build_field_comparisons(
    left_record: NormalizedRecord,
    right_record: NormalizedRecord,
) -> dict[str, dict[str, Any]]:
    left_first, left_surname = _split_name(left_record.first_name or left_record.clean_name or "")
    right_first, right_surname = _split_name(right_record.first_name or right_record.clean_name or "")

    normalized_left_first = _safe_str(left_record.first_name or left_first)
    normalized_right_first = _safe_str(right_record.first_name or right_first)
    normalized_left_surname = _safe_str(left_record.last_name or left_surname)
    normalized_right_surname = _safe_str(right_record.last_name or right_surname)
    normalized_left_phone = _safe_str(left_record.clean_phone)
    normalized_right_phone = _safe_str(right_record.clean_phone)
    normalized_left_email = _safe_str(left_record.clean_email)
    normalized_right_email = _safe_str(right_record.clean_email)

    return {
        "fullName": _build_similarity_field_comparison(
            raw_left=_record_raw_name(left_record),
            raw_right=_record_raw_name(right_record),
            normalized_left=_safe_str(left_record.clean_name),
            normalized_right=_safe_str(right_record.clean_name),
            comparison_method="admin_review_hybrid_jaro_token_similarity(clean_name)",
            field_name="Ad soyad",
            use_token_hybrid=True,
        ),
        "firstName": _build_similarity_field_comparison(
            raw_left=_split_name(_record_raw_name(left_record))[0],
            raw_right=_split_name(_record_raw_name(right_record))[0],
            normalized_left=normalized_left_first,
            normalized_right=normalized_right_first,
            comparison_method="admin_review_jaro_winkler(first_name)",
            field_name="Ad",
        ),
        "surname": _build_similarity_field_comparison(
            raw_left=_split_name(_record_raw_name(left_record))[1],
            raw_right=_split_name(_record_raw_name(right_record))[1],
            normalized_left=normalized_left_surname,
            normalized_right=normalized_right_surname,
            comparison_method="admin_review_jaro_winkler(last_name)",
            field_name="Soyad",
        ),
        "tc": _build_exact_field_comparison(
            raw_left=_record_raw_tc(left_record),
            raw_right=_record_raw_tc(right_record),
            normalized_left=_safe_str(left_record.clean_tc),
            normalized_right=_safe_str(right_record.clean_tc),
            comparison_method="admin_review_exact(clean_tc)",
            field_name="TC Kimlik No",
            use_conflict_label=True,
        ),
        "phone": _build_contact_similarity_field_comparison(
            raw_left=_record_raw_phone(left_record),
            raw_right=_record_raw_phone(right_record),
            normalized_left=normalized_left_phone,
            normalized_right=normalized_right_phone,
            similarity_score=phone_similarity_score(
                normalized_left_phone,
                normalized_right_phone,
            ),
            exact_match=bool(normalized_left_phone and normalized_left_phone == normalized_right_phone),
            comparison_method="admin_review_tiered_phone_similarity(clean_phone)",
            field_name="Telefon",
        ),
        "email": _build_contact_similarity_field_comparison(
            raw_left=_record_raw_email(left_record),
            raw_right=_record_raw_email(right_record),
            normalized_left=normalized_left_email,
            normalized_right=normalized_right_email,
            similarity_score=email_similarity_score(
                normalized_left_email,
                normalized_right_email,
            ),
            exact_match=bool(normalized_left_email and normalized_left_email == normalized_right_email),
            comparison_method="admin_review_hybrid_email_similarity(clean_email)",
            field_name="E-posta",
        ),
        "city": _build_exact_field_comparison(
            raw_left=_record_raw_city(left_record),
            raw_right=_record_raw_city(right_record),
            normalized_left=_safe_str(left_record.clean_city),
            normalized_right=_safe_str(right_record.clean_city),
            comparison_method="admin_review_exact(clean_city)",
            field_name="Sehir",
        ),
        "muhatapNo": _build_exact_field_comparison(
            raw_left=_record_raw_muhatap(left_record),
            raw_right=_record_raw_muhatap(right_record),
            normalized_left=_safe_str(left_record.clean_muhatap_no) if hasattr(left_record, "clean_muhatap_no") else "",
            normalized_right=_safe_str(right_record.clean_muhatap_no) if hasattr(right_record, "clean_muhatap_no") else "",
            comparison_method="admin_review_exact(clean_muhatap_no)",
            field_name="Muhatap Kodu",
            use_conflict_label=True,
        ),
    }


def _derive_features(
    left_record: NormalizedRecord,
    right_record: NormalizedRecord,
    field_comparisons: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    left_phone = _safe_str(left_record.clean_phone)
    right_phone = _safe_str(right_record.clean_phone)
    left_email = _safe_str(left_record.clean_email)
    right_email = _safe_str(right_record.clean_email)
    left_tc = _safe_str(left_record.clean_tc)
    right_tc = _safe_str(right_record.clean_tc)
    left_city = _safe_str(left_record.clean_city)
    right_city = _safe_str(right_record.clean_city)
    left_name = _safe_str(left_record.clean_name)
    right_name = _safe_str(right_record.clean_name)
    left_muhatap = _safe_str(left_record.clean_muhatap_no) if hasattr(left_record, "clean_muhatap_no") else ""
    right_muhatap = _safe_str(right_record.clean_muhatap_no) if hasattr(right_record, "clean_muhatap_no") else ""
    left_ordered_name = _record_raw_name(left_record) or left_name
    right_ordered_name = _record_raw_name(right_record) or right_name
    left_first = _safe_str(field_comparisons["firstName"].get("normalizedLeftValue"))
    right_first = _safe_str(field_comparisons["firstName"].get("normalizedRightValue"))
    left_surname = _safe_str(field_comparisons["surname"].get("normalizedLeftValue"))
    right_surname = _safe_str(field_comparisons["surname"].get("normalizedRightValue"))
    shared_contact_flag = int(
        bool(
            (left_phone and right_phone and left_phone == right_phone)
            or (left_email and right_email and left_email == right_email)
        )
    )
    same_surname_name_conflict_flag = int(
        same_surname_name_conflict(left_ordered_name, right_ordered_name)
    )
    name_similarity = round(hybrid_name_similarity(left_name, right_name), 4)
    first_name_similarity = round(jaro_winkler_similarity(left_first, right_first), 4)
    surname_similarity = round(jaro_winkler_similarity(left_surname, right_surname), 4)
    phone_similarity = round(phone_similarity_score(left_phone, right_phone), 4)
    email_similarity = round(email_similarity_score(left_email, right_email), 4)

    return {
        "tc_exact_match": int(field_comparisons["tc"]["exactMatch"]),
        "tc_conflict": int(bool(left_tc and right_tc and left_tc != right_tc)),
        "tc_present_both": int(bool(left_tc and right_tc)),
        "muhatap_no_exact_match": int(field_comparisons["muhatapNo"]["exactMatch"]),
        "muhatap_no_conflict": int(bool(left_muhatap and right_muhatap and left_muhatap != right_muhatap)),
        "muhatap_present_both": int(bool(left_muhatap and right_muhatap)),
        "phone_exact_match": int(field_comparisons["phone"]["exactMatch"]),
        "phone_similarity": phone_similarity,
        "phone_present_both": int(bool(left_phone and right_phone)),
        "email_exact_match": int(field_comparisons["email"]["exactMatch"]),
        "email_similarity": email_similarity,
        "email_present_both": int(bool(left_email and right_email)),
        "city_exact_match": int(field_comparisons["city"]["exactMatch"]),
        "first_name_exact_match": int(field_comparisons["firstName"]["exactMatch"]),
        "surname_exact_match": int(field_comparisons["surname"]["exactMatch"]),
        "name_similarity": name_similarity,
        "name_present_both": int(bool(left_name and right_name)),
        "name_token_similarity": round(
            token_name_similarity(left_ordered_name, right_ordered_name),
            4,
        ),
        "first_name_similarity": first_name_similarity,
        "surname_similarity": surname_similarity,
        "shared_contact_flag": shared_contact_flag,
        "same_surname_name_conflict": same_surname_name_conflict_flag,
        "common_non_empty_fields": sum(
            [
                int(bool(left_name and right_name)),
                int(bool(left_tc and right_tc)),
                int(bool(left_phone and right_phone)),
                int(bool(left_email and right_email)),
                int(bool(left_city and right_city)),
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
    if int(features.get("common_non_empty_fields", 0) or 0) <= 2:
        risk_flags.append("sparse_data")
    return risk_flags


def _build_rule_reasons(
    match_candidate: MatchCandidate,
    features: dict[str, Any],
    field_comparisons: dict[str, dict[str, Any]],
    *,
    decision: str,
) -> list[str]:
    reasons = [
        f"Eslesme tipi: {_safe_str(match_candidate.match_type) or 'unknown'}",
        f"Guven skoru: {_candidate_confidence(match_candidate):.4f}",
    ]

    if features.get("tc_conflict", 0):
        reasons.append("TC Kimlik No catisiyor.")
    elif features.get("tc_exact_match", 0):
        reasons.append("TC Kimlik No eslesti.")

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
    if features.get("same_surname_name_conflict", 0):
        reasons.append("Soyad ayni ancak ad sinyali belirgin sekilde farkli.")

    full_name_result = field_comparisons["fullName"]["comparisonResult"]
    if full_name_result in {"exact_match", "strong_match", "partial_match"}:
        reasons.append(f"Ad soyad sonucu: {full_name_result}.")

    normalized_decision = _normalize_decision(decision)
    if normalized_decision == "approved":
        reasons.append("Nihai karar otomatik veya manuel onayla ayni kisi yonunde.")
    elif normalized_decision == "rejected":
        if features.get("tc_conflict", 0) and _candidate_confidence(match_candidate) >= 0.80:
            reasons.append(
                "Benzerlik skoru yuksek ancak TC Kimlik No cakismasi nedeniyle otomatik birlestirme engellendi."
            )
        else:
            reasons.append("Nihai karar reddedildi; farkli kisi olasiligi daha yuksek.")
    else:
        reasons.append("Nihai durum manuel inceleme icin beklemede.")
    return reasons


def _candidate_confidence(match_candidate: MatchCandidate) -> float:
    return _safe_float(
        match_candidate.confidence,
        default=_safe_float(match_candidate.score),
    )


def _candidate_display_score(
    match_candidate: MatchCandidate,
    *,
    weights: dict[str, float],
) -> float:
    """Return the UI-facing score as a 0-1 value.

    Stored Splink probability is intentionally capped for some safety rejects
    (for example TC conflicts). For group rows, use the field-weighted score so
    rejected groups do not all display the same threshold cap.
    """
    left_record = match_candidate.left_record
    right_record = match_candidate.right_record
    if left_record is None or right_record is None:
        return _candidate_confidence(match_candidate)

    try:
        field_comparisons = _build_field_comparisons(left_record, right_record)
        features = _derive_features(left_record, right_record, field_comparisons)
        score_breakdown = compute_weighted_score_breakdown(features, weights)
        return _safe_float(score_breakdown.get("general_weighted_percent")) / 100.0
    except Exception:
        return _candidate_confidence(match_candidate)


def _group_display_scores(
    match_candidates: list[MatchCandidate],
    *,
    weights: dict[str, float],
) -> tuple[float, float]:
    scores = [
        _candidate_display_score(candidate, weights=weights)
        for candidate in match_candidates
    ]
    if not scores:
        return 0.0, 0.0
    return round(sum(scores) / len(scores), 4), round(max(scores), 4)


def _decision_to_final_decision(decision: str) -> str:
    return _normalize_decision(decision)


def _score_source_from_match_type(match_type: str) -> str:
    mt = _safe_str(match_type).lower()
    if "splink" in mt:
        return "splink_plus_rules"
    return "fallback_legacy"


def serialize_match_candidate(
    match_candidate: MatchCandidate,
    session: Session | None = None,
) -> dict[str, Any]:
    left_record = match_candidate.left_record
    right_record = match_candidate.right_record

    if left_record is None or right_record is None:
        raise ValueError("Match candidate is missing normalized record joins")

    field_comparisons = _build_field_comparisons(left_record, right_record)
    features = _derive_features(left_record, right_record, field_comparisons)
    normalized_decision = _normalize_decision(match_candidate.decision)
    decision_type = _decision_type_for_candidate(normalized_decision, _safe_str(match_candidate.match_type))
    risk_flags = _build_risk_flags(features)
    rule_reasons = _build_rule_reasons(
        match_candidate,
        features,
        field_comparisons,
        decision=normalized_decision,
    )
    confidence = _candidate_confidence(match_candidate)
    if normalized_decision == "rejected" and "tc_conflict" in risk_flags and confidence >= 0.80:
        reason = "Benzerlik skoru yuksek ancak TC Kimlik No cakismasi nedeniyle otomatik birlestirme engellendi."
    elif normalized_decision == "approved":
        reason = "Guclu kimlik sinyalleri nedeniyle onaylandi."
    else:
        reason = "Kayit manuel inceleme gerektiriyor."

    weights, thresholds = load_scoring_app_settings(session)
    ml_prob = float(predict_match_probability(features))
    _, safety_replay = resolve_match_decision_with_trace(ml_prob, features, thresholds=thresholds)
    score_breakdown = compute_weighted_score_breakdown(features, weights)
    score_source = _score_source_from_match_type(_safe_str(match_candidate.match_type))

    return {
        "id": match_candidate.id,
        "left_id": match_candidate.left_id,
        "right_id": match_candidate.right_id,
        "decision": normalized_decision,
        "decision_type": decision_type,
        "review_required": normalized_decision == "pending",
        "score": _safe_float(match_candidate.score, default=confidence),
        "match_type": _safe_str(match_candidate.match_type) or "unknown",
        "confidence": confidence,
        "donor1_id": match_candidate.left_id,
        "donor2_id": match_candidate.right_id,
        "donor1_name": _safe_str(left_record.clean_name),
        "donor1_email": _safe_str(left_record.clean_email) or None,
        "donor1_phone": _safe_str(left_record.clean_phone) or None,
        "donor1_city": _safe_str(left_record.clean_city) or None,
        "donor1_tc": _safe_str(left_record.clean_tc) or None,
        "donor1_muhatap_no": _safe_str(left_record.clean_muhatap_no) or None,
        "donor2_name": _safe_str(right_record.clean_name),
        "donor2_email": _safe_str(right_record.clean_email) or None,
        "donor2_phone": _safe_str(right_record.clean_phone) or None,
        "donor2_city": _safe_str(right_record.clean_city) or None,
        "donor2_tc": _safe_str(right_record.clean_tc) or None,
        "donor2_muhatap_no": _safe_str(right_record.clean_muhatap_no) or None,
        "ml_score": confidence,
        "decision_reason": reason,
        "reason": reason,
        "features": features,
        "fieldComparisons": field_comparisons,
        "riskFlags": risk_flags,
        "ruleReasons": rule_reasons,
        "decisionSource": _safe_str(match_candidate.match_type) or "match_candidate",
        "finalDecision": _decision_to_final_decision(normalized_decision),
        "splinkMatchProbability": confidence,
        "splinkMatchWeight": None,
        "created_at": match_candidate.created_at.isoformat() if match_candidate.created_at else None,
        "final_score": score_breakdown["general_weighted_percent"],
        "score_source": score_source,
        "score_breakdown": score_breakdown,
        "applied_thresholds": thresholds.as_percent_dict(),
        "safety_overrides": safety_replay,
    }


def derive_canonical_ml_features_for_match_candidate(
    match_candidate: MatchCandidate,
) -> dict[str, float] | None:
    """
    RF train / export / canonical inference alignment: recompute features from live records.

    Same path as review UI (`_build_field_comparisons` → `_derive_features`) → `extract_canonical_ml_features`.
    Does not read persisted JSON on MatchCandidate (if any).
    """
    if match_candidate.left_record is None or match_candidate.right_record is None:
        return None
    field_comparisons = _build_field_comparisons(
        match_candidate.left_record,
        match_candidate.right_record,
    )
    raw_features = _derive_features(
        match_candidate.left_record,
        match_candidate.right_record,
        field_comparisons,
    )
    return extract_canonical_ml_features(raw_features)


def collect_ground_truth_labeled_rows(session: Session) -> list[dict[str, Any]]:
    """
    Export-ready rows: human-approved/rejected pairs with canonical ML features.
    Uses the same `_derive_features` path as review UI and the same 6-column schema as RF train/predict.
    """
    review_labels = get_latest_review_labels_by_match_id(session)
    query = (
        session.query(MatchCandidate)
        .options(
            joinedload(MatchCandidate.detection_run),
            joinedload(MatchCandidate.left_record).joinedload(NormalizedRecord.raw_record),
            joinedload(MatchCandidate.right_record).joinedload(NormalizedRecord.raw_record),
        )
        .order_by(MatchCandidate.id.asc())
    )
    rows: list[dict[str, Any]] = []
    for mc in query:
        label = review_labels.get(int(mc.id))
        if label is None:
            label = _normalize_decision(str(mc.decision or ""))
        if label not in ("approved", "rejected"):
            continue
        canon = derive_canonical_ml_features_for_match_candidate(mc)
        if canon is None:
            continue
        upload_id = None
        if mc.detection_run is not None:
            upload_id = int(mc.detection_run.upload_id)
        base: dict[str, Any] = {
            "match_id": int(mc.id),
            "left_id": int(mc.left_id),
            "right_id": int(mc.right_id),
            "upload_id": upload_id,
            "detection_run_id": int(mc.detection_run_id),
            "label": label,
            "confidence": round(float(_candidate_confidence(mc)), 6),
        }
        for col in CANONICAL_ML_MODEL_FEATURE_COLUMNS:
            base[col] = round(float(canon.get(col, 0.0)), 6)
        rows.append(base)
    return rows


def _match_pair_has_distinct_muhatap_codes(mc: MatchCandidate) -> bool:
    left = mc.left_record
    right = mc.right_record
    if left is None or right is None:
        return False
    a = _record_group_muhatap_code(left) or _safe_str(left.clean_muhatap_no)
    b = _record_group_muhatap_code(right) or _safe_str(right.clean_muhatap_no)
    return bool(a and b and a != b)


def get_match_candidates(
    session: Session,
    *,
    upload_id: int | None = None,
    decision: str | None = None,
    limit: int = 50,
    latest_only: bool = True,
    different_muhatap_pair: bool = False,
) -> list[MatchCandidate]:
    query = (
        session.query(MatchCandidate)
        .options(
            joinedload(MatchCandidate.detection_run),
            joinedload(MatchCandidate.left_record).joinedload(NormalizedRecord.raw_record),
            joinedload(MatchCandidate.right_record).joinedload(NormalizedRecord.raw_record),
        )
    )
    normalized_decision = _safe_str(decision).lower()
    if normalized_decision in {"pending", "approved", "rejected"}:
        query = query.filter(MatchCandidate.decision == normalized_decision)

    if upload_id is not None:
        query = query.join(DetectionRun).filter(DetectionRun.upload_id == upload_id)
        # Aynı upload için birden fazla detection run çalıştırıldığında aynı çiftler tekrar görünebilir.
        # Listeyi son run ile sınırla.
        if latest_only:
            latest_run_id = (
                session.query(func.max(DetectionRun.id))
                .filter(DetectionRun.upload_id == upload_id)
                .scalar()
            )
            if latest_run_id is not None:
                query = query.filter(MatchCandidate.detection_run_id == int(latest_run_id))
    else:
        # upload_id filtresi yoksa: tüm upload'ların *son* detection run'larını göster.
        latest_run_ids_subq = (
            session.query(func.max(DetectionRun.id).label("id"))
            .group_by(DetectionRun.upload_id)
            .subquery()
        )
        query = query.join(DetectionRun).filter(DetectionRun.id.in_(latest_run_ids_subq))

    ordered = query.order_by(
        func.coalesce(MatchCandidate.confidence, MatchCandidate.score).desc(),
        MatchCandidate.created_at.desc(),
    )
    if not different_muhatap_pair:
        return ordered.limit(limit).all()

    scan_cap = max(int(limit) * 50, 5000)
    pool = ordered.limit(min(scan_cap, 50_000)).all()
    filtered = [mc for mc in pool if _match_pair_has_distinct_muhatap_codes(mc)]
    return filtered[: int(limit)]


def get_match_candidates_page(
    session: Session,
    *,
    upload_id: int | None = None,
    decision: str | None = None,
    page: int = 1,
    page_size: int = 50,
    latest_only: bool = True,
    different_muhatap_pair: bool = False,
) -> tuple[int, list[MatchCandidate]]:
    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))
    offset = (page - 1) * page_size

    query = (
        session.query(MatchCandidate)
        .options(
            joinedload(MatchCandidate.detection_run),
            joinedload(MatchCandidate.left_record).joinedload(NormalizedRecord.raw_record),
            joinedload(MatchCandidate.right_record).joinedload(NormalizedRecord.raw_record),
        )
    )

    normalized_decision = _safe_str(decision).lower()
    if normalized_decision in {"pending", "approved", "rejected"}:
        query = query.filter(MatchCandidate.decision == normalized_decision)

    if upload_id is not None:
        query = query.join(DetectionRun).filter(DetectionRun.upload_id == upload_id)
        if latest_only:
            latest_run_id = (
                session.query(func.max(DetectionRun.id))
                .filter(DetectionRun.upload_id == upload_id)
                .scalar()
            )
            if latest_run_id is not None:
                query = query.filter(MatchCandidate.detection_run_id == int(latest_run_id))
    else:
        latest_run_ids_subq = (
            session.query(func.max(DetectionRun.id).label("id"))
            .group_by(DetectionRun.upload_id)
            .subquery()
        )
        query = query.join(DetectionRun).filter(DetectionRun.id.in_(latest_run_ids_subq))

    if not different_muhatap_pair:
        total = int(query.with_entities(func.count(MatchCandidate.id)).scalar() or 0)
        rows = (
            query.order_by(
                func.coalesce(MatchCandidate.confidence, MatchCandidate.score).desc(),
                MatchCandidate.created_at.desc(),
            )
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return total, rows

    MAX_SCAN = 25_000
    pool = (
        query.order_by(
            func.coalesce(MatchCandidate.confidence, MatchCandidate.score).desc(),
            MatchCandidate.created_at.desc(),
        )
        .limit(MAX_SCAN)
        .all()
    )
    filtered = [mc for mc in pool if _match_pair_has_distinct_muhatap_codes(mc)]
    total = len(filtered)
    rows = filtered[offset : offset + page_size]
    return total, rows


def _record_completeness_score(record: NormalizedRecord) -> int:
    return sum(
        [
            int(bool(_safe_str(record.clean_name))),
            int(bool(_safe_str(record.clean_tc))),
            int(bool(_safe_str(record.clean_phone))),
            int(bool(_safe_str(record.clean_email))),
            int(bool(_safe_str(record.clean_city))),
            int(bool(_safe_str(record.clean_address))),
            int(bool(_safe_str(record.clean_muhatap_no))),
        ]
    )


def _best_value(values: list[str], *, preferred_len: int | None = None) -> str:
    non_empty = [_safe_str(value) for value in values if _safe_str(value)]
    if not non_empty:
        return ""
    counts: dict[str, int] = {}
    for value in non_empty:
        counts[value] = counts.get(value, 0) + 1

    def _rank(value: str) -> tuple[int, int, int]:
        preferred = int(preferred_len is not None and len(value) == preferred_len)
        return (counts[value], preferred, len(value))

    return sorted(non_empty, key=_rank, reverse=True)[0]


def _normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in _safe_str(value) if ch.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def _normalize_tc(value: str) -> str:
    digits = "".join(ch for ch in _safe_str(value) if ch.isdigit())
    return digits if len(digits) == 11 else ""


def _normalize_email(value: str) -> tuple[str, bool]:
    email = _safe_str(value).lower().replace(" ", "")
    if "@" not in email:
        return "", False
    username, domain = email.split("@", 1)
    username = username or ""
    domain = domain or ""
    base_username = username.split("+", 1)[0]
    return (f"{base_username}@{domain}" if base_username and domain else ""), ("+" in username)


def _serialize_group_record(record: NormalizedRecord) -> dict[str, Any]:
    payload = _normalized_payload(record)
    raw_record = record.raw_record
    batch_id = _safe_str(getattr(raw_record, "batch_id", "")) if raw_record is not None else ""
    if not batch_id:
        batch_id = f"upload-{record.upload_id or 'unknown'}"
    return {
        "record_id": record.id,
        "raw_id": record.raw_id,
        "upload_id": record.upload_id,
        "batch_id": batch_id,
        "clean_name": _safe_str(record.clean_name),
        "clean_tc": _safe_str(record.clean_tc),
        "clean_phone": _safe_str(record.clean_phone),
        "clean_email": _safe_str(record.clean_email),
        "clean_city": _safe_str(record.clean_city),
        "clean_address": _safe_str(record.clean_address),
        "clean_muhatap_no": _safe_str(record.clean_muhatap_no),
        "normalized_payload": payload,
        "completeness_score": _record_completeness_score(record),
    }


def _build_golden_record(records: list[NormalizedRecord]) -> dict[str, Any]:
    if not records:
        return {}

    ordered_records = sorted(
        records,
        key=lambda record: (_record_completeness_score(record), -int(record.id)),
        reverse=True,
    )
    warnings: list[str] = []
    source_record_ids = [int(record.id) for record in ordered_records]
    field_sources: dict[str, int | None] = {}
    secondary_emails: list[str] = []

    def pick_with_source(field_name: str, values: list[str], *, preferred_len: int | None = None, longest=False) -> str:
        non_empty = [_safe_str(value) for value in values if _safe_str(value)]
        if not non_empty:
            field_sources[field_name] = None
            return ""
        chosen = _best_value(non_empty, preferred_len=preferred_len)
        if longest:
            chosen = sorted(non_empty, key=lambda value: len(value), reverse=True)[0]
        for record in ordered_records:
            if _safe_str(getattr(record, field_name, "")) == chosen:
                field_sources[field_name] = int(record.id)
                break
        if field_name not in field_sources:
            field_sources[field_name] = None
        return chosen

    tc_values = [_normalize_tc(record.clean_tc) for record in ordered_records]
    unique_tcs = {tc for tc in tc_values if tc}
    golden_tc = _best_value([tc for tc in tc_values if tc], preferred_len=11)
    if len(unique_tcs) > 1:
        warnings.append("tc_conflict")
    for record in ordered_records:
        if _normalize_tc(record.clean_tc) == golden_tc and golden_tc:
            field_sources["clean_tc"] = int(record.id)
            break
    if "clean_tc" not in field_sources:
        field_sources["clean_tc"] = None

    phone_values = [_normalize_phone(record.clean_phone) for record in ordered_records]
    golden_phone = _best_value([phone for phone in phone_values if phone], preferred_len=10)
    for record in ordered_records:
        if _normalize_phone(record.clean_phone) == golden_phone and golden_phone:
            field_sources["clean_phone"] = int(record.id)
            break
    if "clean_phone" not in field_sources:
        field_sources["clean_phone"] = None

    normalized_emails: list[str] = []
    for record in ordered_records:
        normalized_email, is_alias = _normalize_email(record.clean_email)
        if normalized_email:
            normalized_emails.append(normalized_email)
            if is_alias:
                secondary_emails.append(_safe_str(record.clean_email).lower())
    golden_email = _best_value(normalized_emails)
    for record in ordered_records:
        normalized_email, _ = _normalize_email(record.clean_email)
        if normalized_email == golden_email and golden_email:
            field_sources["clean_email"] = int(record.id)
            break
    if "clean_email" not in field_sources:
        field_sources["clean_email"] = None

    golden_name = pick_with_source(
        "clean_name",
        [_safe_str(record.clean_name) for record in ordered_records],
    )
    city_values = [_safe_str(record.clean_city) for record in ordered_records]
    golden_city = pick_with_source("clean_city", city_values)
    golden_address = pick_with_source(
        "clean_address",
        [_safe_str(record.clean_address) for record in ordered_records],
        longest=True,
    )
    golden_muhatap = pick_with_source(
        "clean_muhatap_no",
        [_safe_str(record.clean_muhatap_no) for record in ordered_records],
    )

    if not golden_tc and not golden_phone and not golden_email:
        warnings.append("weak_identity_evidence")

    return {
        "clean_name": golden_name,
        "clean_tc": golden_tc,
        "clean_phone": golden_phone,
        "clean_email": golden_email,
        "clean_city": golden_city,
        "clean_address": golden_address,
        "clean_muhatap_no": golden_muhatap,
        "source_record_ids": source_record_ids,
        "field_sources": field_sources,
        "warnings": warnings,
        "risk_flags": warnings,
        "secondary_emails": sorted(set(secondary_emails)),
    }


_GOLDEN_VALUE_KEYS = (
    "clean_name",
    "clean_tc",
    "clean_phone",
    "clean_email",
    "clean_city",
    "clean_address",
    "clean_muhatap_no",
)


class MuhatapConflictError(Exception):
    """Aynı yüklemede başka onaylı entity ile canonical muhatap çakışması."""

    def __init__(self, proposed_muhatap: str, conflicts: list[dict[str, Any]]):
        self.proposed_muhatap = proposed_muhatap
        self.conflicts = conflicts
        super().__init__("MUHATAP_CONFLICT")


def _confirmed_entity_member_ids(session: Session, entity_id: int) -> set[int]:
    rows = (
        session.query(EntityMembership.normalized_record_id)
        .filter(EntityMembership.entity_id == int(entity_id))
        .filter(EntityMembership.status == "confirmed")
        .all()
    )
    return {int(r[0]) for r in rows}


def _proposed_muhatap_for_approval(
    confirmed_records: list[NormalizedRecord],
    golden_record_override: dict[str, Any] | None,
) -> str:
    if golden_record_override and golden_record_override.get("clean_muhatap_no") is not None:
        m = _safe_str(golden_record_override.get("clean_muhatap_no"))
        if m:
            return m
    canonical = _build_golden_record(confirmed_records)
    return _safe_str(canonical.get("clean_muhatap_no"))


def _find_muhatap_conflicts_for_upload(
    session: Session,
    upload_id: int,
    proposed_muhatap: str,
    exclude_entity_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    prop = _safe_str(proposed_muhatap)
    if not prop:
        return []
    exclude_entity_ids = exclude_entity_ids or set()
    norm_target = prop.casefold()
    rows = (
        session.query(Entity.id, Entity.canonical_name, Entity.canonical_muhatap_no)
        .join(EntityMembership, EntityMembership.entity_id == Entity.id)
        .join(NormalizedRecord, NormalizedRecord.id == EntityMembership.normalized_record_id)
        .filter(EntityMembership.status == "confirmed")
        .filter(NormalizedRecord.upload_id == int(upload_id))
        .distinct()
        .all()
    )
    conflicts: list[dict[str, Any]] = []
    seen: set[int] = set()
    for eid, cname, cmu in rows:
        eidi = int(eid)
        if eidi in exclude_entity_ids or eidi in seen:
            continue
        if _safe_str(cmu).casefold() != norm_target:
            continue
        seen.add(eidi)
        conflicts.append(
            {
                "entity_id": eidi,
                "canonical_name": cname,
                "canonical_muhatap_no": cmu,
            }
        )
    return conflicts


def get_merge_min_reviewers(session: Session) -> int:
    """
    AppSettings: mukerrer_merge_min_reviewers (int veya { value: int }).
    >1 ise kısmi onay / var olan gruba ekle isteğinde co_review_acknowledged gerekir.
    """
    row = session.query(AppSettings).filter(AppSettings.key == "mukerrer_merge_min_reviewers").first()
    if row is None or row.value is None:
        return 1
    v: Any = row.value
    if isinstance(v, bool):
        return 1
    if isinstance(v, int):
        return max(1, min(int(v), 20))
    if isinstance(v, float):
        return max(1, min(int(v), 20))
    if isinstance(v, str):
        try:
            return max(1, min(int(v.strip()), 20))
        except ValueError:
            return 1
    if isinstance(v, dict):
        for k in ("min_reviewers", "value", "count"):
            if k in v and v[k] is not None:
                try:
                    return max(1, min(int(v[k]), 20))
                except (TypeError, ValueError):
                    pass
    return 1


def _entity_confirmed_upload_ids(session: Session, entity_id: int) -> list[int]:
    rows = (
        session.query(NormalizedRecord.upload_id)
        .join(EntityMembership, EntityMembership.normalized_record_id == NormalizedRecord.id)
        .filter(
            EntityMembership.entity_id == int(entity_id),
            EntityMembership.status == "confirmed",
        )
        .distinct()
        .all()
    )
    out: list[int] = []
    for t in rows:
        if t[0] is not None:
            out.append(int(t[0]))
    return sorted(set(out))


def check_golden_muhatap_no_conflicts_for_entity(
    session: Session,
    entity_id: int,
    proposed_muhatap: str,
) -> None:
    """Golden muhatap güncellemesi için aynı yüklemedeki diğer onaylı entity ile çakışmayı kontrol eder."""
    prop = _safe_str(proposed_muhatap)
    if not prop:
        return
    upload_ids = _entity_confirmed_upload_ids(session, entity_id)
    if not upload_ids:
        return
    all_conflicts: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for uid in upload_ids:
        for c in _find_muhatap_conflicts_for_upload(
            session,
            uid,
            prop,
            exclude_entity_ids={int(entity_id)},
        ):
            sig = (int(c["entity_id"]), int(uid))
            if sig in seen:
                continue
            seen.add(sig)
            entry = dict(c)
            entry["upload_id"] = int(uid)
            all_conflicts.append(entry)
    if all_conflicts:
        raise MuhatapConflictError(prop, all_conflicts)


def _overlay_entity_canonical_on_golden(
    base_golden: dict[str, Any],
    canonical_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Kaydedilmiş entity.canonical_data ile golden_record görünümünü güncelle."""
    if not canonical_data:
        return base_golden
    merged = dict(base_golden)
    for key in _GOLDEN_VALUE_KEYS:
        if key not in canonical_data:
            continue
        sval = _safe_str(canonical_data.get(key))
        if sval:
            merged[key] = sval
    for meta_key in (
        "merged_muhatap_sources",
        "merged_muhatap_report_line",
        "merged_member_snapshots",
        "excluded_member_snapshots",
    ):
        if meta_key in canonical_data and canonical_data[meta_key] is not None:
            merged[meta_key] = canonical_data[meta_key]
    return merged


def _group_qualifies_for_entity_golden_hydrate(
    group: dict[str, Any],
    membership_by_record: dict[int, dict[str, Any]],
) -> bool:
    """
    Onaylı entity canonical_data yalnızca gruptaki TÜM kayıtlar aynı entity'de
    confirmed ise golden üzerine yazılır. Kısmi birleşim sonrası bekleyen gruplar
    kayıt bazlı _build_golden_record önizlemesini korur.
    """
    record_ids = [int(rid) for rid in (group.get("record_ids") or [])]
    if len(record_ids) < 1:
        return False
    entity_ids: set[int] = set()
    for record_id in record_ids:
        membership = membership_by_record.get(record_id)
        if membership is None:
            return False
        if _safe_str(membership.get("status")).lower() != "confirmed":
            return False
        eid = membership.get("entity_id")
        if eid is None:
            return False
        entity_ids.add(int(eid))
    return len(entity_ids) == 1


def _hydrate_golden_records_from_entities(
    session: Session,
    groups: list[dict[str, Any]],
) -> None:
    """groups üzerinde yerinde: tam onaylı gruplar entity canonical ile hizalanır."""
    all_record_ids = sorted(
        {
            int(rid)
            for group in groups
            for rid in (group.get("record_ids") or [])
        }
    )
    membership_global = _membership_snapshots_by_record(session, all_record_ids)

    eligible: list[tuple[dict[str, Any], int]] = []
    for group in groups:
        record_ids = [int(rid) for rid in (group.get("record_ids") or [])]
        if not record_ids:
            continue
        membership_by_record = {
            int(rid): membership_global[int(rid)]
            for rid in record_ids
            if int(rid) in membership_global
        }
        if not _group_qualifies_for_entity_golden_hydrate(group, membership_by_record):
            group["entity_id"] = None
            continue
        eid = next(iter({int(m["entity_id"]) for m in membership_by_record.values()}))
        group["entity_id"] = eid
        eligible.append((group, eid))

    if not eligible:
        return

    entity_ids = sorted({eid for _, eid in eligible})
    rows = session.query(Entity).filter(Entity.id.in_(entity_ids)).all()
    entity_by_id = {int(e.id): e for e in rows}
    for group, eid in eligible:
        entity = entity_by_id.get(int(eid))
        if entity is None:
            continue
        cd = entity.canonical_data if isinstance(entity.canonical_data, dict) else {}
        group["golden_record"] = _overlay_entity_canonical_on_golden(
            group.get("golden_record") or {},
            cd,
        )


def _get_table_column_names(session: Session, table_name: str) -> set[str]:
    bind = session.get_bind()
    if bind is None:
        return set()
    return {column["name"] for column in sa_inspect(bind).get_columns(table_name)}


def _membership_snapshots_by_record(
    session: Session,
    record_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not record_ids:
        return {}

    columns = _get_table_column_names(session, "entity_memberships")
    if not {"entity_id", "normalized_record_id"}.issubset(columns):
        return {}

    status_expr = "status" if "status" in columns else "'pending' AS status"
    rows = session.execute(
        text(
            f"""
            SELECT entity_id, normalized_record_id, {status_expr}
            FROM entity_memberships
            WHERE normalized_record_id = ANY(:record_ids)
            """
        ),
        {"record_ids": record_ids},
    ).mappings()

    snapshots: dict[int, dict[str, Any]] = {}
    for row in rows:
        record_id = int(row["normalized_record_id"])
        snapshots[record_id] = {
            "entity_id": int(row["entity_id"]) if row["entity_id"] is not None else None,
            "status": _safe_str(row.get("status")) or "pending",
        }
    return snapshots


def _is_confirmed_membership(membership: dict[str, Any] | None) -> bool:
    if membership is None:
        return False
    return _safe_str(membership.get("status")).lower() == "confirmed"


def _record_ids_for_pending_group_display(
    session: Session,
    record_ids: list[int],
    *,
    decision: str,
    membership_by_record: dict[int, dict[str, Any]] | None = None,
) -> list[int] | None:
    """Bekleyen gruplardan entity'ye onaylanmış kayıtları çıkarır; <2 kayıt kalırsa None."""
    if _normalize_decision(decision) != "pending":
        return sorted({int(rid) for rid in record_ids})
    if not record_ids:
        return None
    if membership_by_record is None:
        membership_by_record = _membership_snapshots_by_record(session, record_ids)
    active = [
        int(rid)
        for rid in record_ids
        if not _is_confirmed_membership(membership_by_record.get(int(rid)))
    ]
    if len(active) < 2:
        return None
    return sorted(active)


def _partial_approval_pair_decision(
    left_id: int,
    right_id: int,
    *,
    approved_set: set[int],
    rejected_set: set[int],
) -> str:
    """Kısmi birleştirmede çift kararı: onaylı–bekleyen kenarlar pending'de kalmamalı."""
    if left_id in approved_set and right_id in approved_set:
        return "approved"
    if left_id in rejected_set or right_id in rejected_set:
        return "rejected"
    if left_id in approved_set or right_id in approved_set:
        return "rejected"
    return "pending"


def get_duplicate_groups(
    session: Session,
    *,
    upload_id: int | None = None,
    decision: str = "approved",
    limit: int = 5000,
    different_muhatap_code: bool = True,
) -> list[dict[str, Any]]:
    if _normalize_decision(decision) == "approved" and upload_id is not None:
        return _entity_merge_groups_for_upload(
            session,
            upload_id=upload_id,
            limit=limit,
            different_muhatap_code=different_muhatap_code,
        )

    candidates = get_match_candidates(
        session,
        upload_id=upload_id,
        decision=decision,
        limit=limit,
        latest_only=False,
    )
    if not candidates:
        return []

    weights, _thresholds = load_scoring_app_settings(session)
    adjacency: dict[int, set[int]] = {}
    edge_by_pair: dict[tuple[int, int], MatchCandidate] = {}
    record_by_id: dict[int, NormalizedRecord] = {}

    for candidate in candidates:
        left = candidate.left_record
        right = candidate.right_record
        if left is None or right is None:
            continue
        left_id = int(left.id)
        right_id = int(right.id)
        if left_id == right_id:
            continue

        adjacency.setdefault(left_id, set()).add(right_id)
        adjacency.setdefault(right_id, set()).add(left_id)
        pair_key = (min(left_id, right_id), max(left_id, right_id))
        edge_by_pair[pair_key] = candidate
        record_by_id[left_id] = left
        record_by_id[right_id] = right

    groups: list[dict[str, Any]] = []
    visited: set[int] = set()
    component_index = 0
    for start in sorted(adjacency.keys()):
        if start in visited:
            continue
        stack = [start]
        component: set[int] = set()
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.add(node)
            stack.extend(sorted(adjacency.get(node, set()) - visited))

        if len(component) < 2:
            continue

        component_ids = sorted(component)
        pruned_ids = _record_ids_for_pending_group_display(
            session,
            component_ids,
            decision=decision,
        )
        if pruned_ids is None:
            continue
        component_ids = pruned_ids
        active_component = set(component_ids)

        component_index += 1
        match_candidates_in_group = [
            candidate
            for (left_id, right_id), candidate in edge_by_pair.items()
            if left_id in active_component and right_id in active_component
        ]
        group_score, score_max = _group_display_scores(
            match_candidates_in_group,
            weights=weights,
        )

        group_id = f"group_{component_index}"

        group_records = [record_by_id[record_id] for record_id in component_ids]
        muhatap_codes = sorted(
            {
                code
                for code in (_record_group_muhatap_code(record) for record in group_records)
                if code
            }
        )
        has_different_muhatap_code = len(muhatap_codes) > 1
        if different_muhatap_code and not has_different_muhatap_code:
            continue

        membership_by_record = _membership_snapshots_by_record(session, component_ids)
        serialized_records = []
        for record in group_records:
            serialized_record = _serialize_group_record(record)
            membership = membership_by_record.get(int(record.id))
            serialized_record["membership_status"] = (
                membership.get("status", "pending") if membership is not None else "pending"
            )
            serialized_record["entity_id"] = (
                int(membership["entity_id"])
                if membership is not None and membership.get("entity_id") is not None
                else None
            )
            serialized_records.append(serialized_record)
        groups.append(
            {
                "group_id": group_id,
                "entity_id": None,
                "record_ids": component_ids,
                "pair_count": len(match_candidates_in_group),
                "avg_score": group_score,
                "max_score": score_max,
                "group_score": group_score,
                "group_score_max": score_max,
                "match_count": len(match_candidates_in_group),
                "match_candidate_ids": sorted(
                    {int(c.id) for c in match_candidates_in_group},
                ),
                "muhatap_codes": muhatap_codes,
                "different_muhatap_code": has_different_muhatap_code,
                "records": serialized_records,
                "golden_record": _build_golden_record(group_records),
            }
        )

    groups.sort(
        key=lambda group: (group["group_score"], group["match_count"]),
        reverse=True,
    )
    _hydrate_golden_records_from_entities(session, groups)
    if _normalize_decision(decision) == "approved":
        entity_groups = _entity_merge_groups_for_upload(
            session,
            upload_id=upload_id,
            limit=limit,
            different_muhatap_code=different_muhatap_code,
        )
        groups = _merge_duplicate_group_lists(groups, entity_groups)
    return groups


def _merge_duplicate_group_lists(
    match_groups: list[dict[str, Any]],
    entity_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Entity birleştirmeleri (doğru golden) öncelikli; aynı kayıt kümesinde çift satır olmasın."""
    by_records: dict[frozenset[int], dict[str, Any]] = {}
    for group in match_groups:
        key = frozenset(int(rid) for rid in (group.get("record_ids") or []))
        if len(key) >= 2:
            by_records[key] = group
    for group in entity_groups:
        key = frozenset(int(rid) for rid in (group.get("record_ids") or []))
        if len(key) >= 2:
            by_records[key] = group
    merged = list(by_records.values())
    merged.sort(
        key=lambda group: (group.get("group_score", 0), group.get("match_count", 0)),
        reverse=True,
    )
    return merged


def _entity_merge_groups_for_upload(
    session: Session,
    *,
    upload_id: int | None,
    limit: int = 5000,
    different_muhatap_code: bool = False,
) -> list[dict[str, Any]]:
    """Onaylı entity birleştirmeleri — her Kaydet ayrı satır, entity canonical golden."""
    membership_query = (
        session.query(EntityMembership)
        .join(
            NormalizedRecord,
            EntityMembership.normalized_record_id == NormalizedRecord.id,
        )
        .filter(EntityMembership.status == "confirmed")
    )
    if upload_id is not None:
        membership_query = membership_query.filter(NormalizedRecord.upload_id == upload_id)

    memberships = membership_query.all()
    by_entity: dict[int, list[EntityMembership]] = {}
    for membership in memberships:
        by_entity.setdefault(int(membership.entity_id), []).append(membership)

    if not by_entity:
        return []

    entity_ids = sorted(by_entity.keys())
    entity_rows = session.query(Entity).filter(Entity.id.in_(entity_ids)).all()
    entity_by_id = {int(row.id): row for row in entity_rows}

    all_record_ids = sorted(
        {int(m.normalized_record_id) for ms in by_entity.values() for m in ms}
    )
    record_by_id: dict[int, NormalizedRecord] = {}
    if all_record_ids:
        rows = (
            session.query(NormalizedRecord)
            .options(joinedload(NormalizedRecord.raw_record))
            .filter(NormalizedRecord.id.in_(all_record_ids))
            .all()
        )
        record_by_id = {int(r.id): r for r in rows}

    membership_global = _membership_snapshots_by_record(session, all_record_ids)
    group_candidates_pool: list[MatchCandidate] = []
    if all_record_ids:
        group_candidates_pool = (
            session.query(MatchCandidate)
            .filter(MatchCandidate.decision == "approved")
            .filter(MatchCandidate.left_id.in_(all_record_ids))
            .filter(MatchCandidate.right_id.in_(all_record_ids))
            .all()
        )
    record_to_entity: dict[int, int] = {}
    for entity_id, entity_memberships in by_entity.items():
        for membership in entity_memberships:
            record_to_entity[int(membership.normalized_record_id)] = int(entity_id)

    candidates_by_entity: dict[int, list[MatchCandidate]] = {eid: [] for eid in entity_ids}
    for candidate in group_candidates_pool:
        left_id = int(candidate.left_id)
        right_id = int(candidate.right_id)
        entity_id = record_to_entity.get(left_id)
        if entity_id is None or record_to_entity.get(right_id) != entity_id:
            continue
        candidates_by_entity.setdefault(entity_id, []).append(candidate)

    weights, _thresholds = load_scoring_app_settings(session)
    groups: list[dict[str, Any]] = []

    for entity_id in entity_ids:
        entity = entity_by_id.get(entity_id)
        if entity is None:
            continue
        record_ids = sorted(
            {int(m.normalized_record_id) for m in by_entity[entity_id]},
        )
        canonical = entity.canonical_data if isinstance(entity.canonical_data, dict) else {}
        has_merge_detail = bool(
            canonical.get("merged_muhatap_report_line")
            or canonical.get("merged_member_snapshots")
        )
        if len(record_ids) < 2 and not has_merge_detail:
            if len(record_ids) != 1:
                continue

        group_records = [record_by_id[rid] for rid in record_ids if rid in record_by_id]
        if not group_records:
            continue

        serialized_records = []
        for record in group_records:
            serialized_record = _serialize_group_record(record)
            membership = membership_global.get(int(record.id))
            serialized_record["membership_status"] = (
                membership.get("status", "confirmed") if membership else "confirmed"
            )
            serialized_record["entity_id"] = entity_id
            serialized_records.append(serialized_record)

        muhatap_codes = sorted(
            {
                code
                for code in (_record_group_muhatap_code(record) for record in group_records)
                if code
            }
        )
        has_different_muhatap = len(muhatap_codes) > 1
        if different_muhatap_code and not has_different_muhatap and not has_merge_detail:
            if len(record_ids) != 1:
                continue

        group_candidates = candidates_by_entity.get(entity_id, [])
        group_score, score_max = _group_display_scores(
            group_candidates,
            weights=weights,
        )
        golden_record = _overlay_entity_canonical_on_golden(
            _build_golden_record(group_records),
            canonical,
        )

        groups.append(
            {
                "group_id": f"entity_{entity_id}",
                "entity_id": entity_id,
                "record_ids": record_ids,
                "pair_count": len(group_candidates),
                "avg_score": group_score,
                "max_score": score_max,
                "group_score": group_score,
                "group_score_max": score_max,
                "match_count": len(group_candidates),
                "match_candidate_ids": sorted({int(c.id) for c in group_candidates}),
                "muhatap_codes": muhatap_codes,
                "different_muhatap_code": has_different_muhatap,
                "records": serialized_records,
                "golden_record": golden_record,
            }
        )

    groups.sort(
        key=lambda group: (group.get("group_score", 0), group.get("match_count", 0)),
        reverse=True,
    )
    if limit > 0:
        return groups[: int(limit)]
    return groups


def get_duplicate_groups_page(
    session: Session,
    *,
    upload_id: int | None = None,
    decision: str = "approved",
    limit: int = 5000,
    page: int = 1,
    page_size: int = 50,
    different_muhatap_code: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    """
    DB-level pagination for duplicate groups when materialized tables exist.
    Falls back to legacy runtime grouping otherwise.
    Returns (groups, total).
    """

    # detect whether materialized tables exist
    try:
        bind = session.get_bind()
        inspector = sa_inspect(bind) if bind is not None else None
        has_tables = bool(
            inspector
            and inspector.has_table("materialized_duplicate_groups")
            and inspector.has_table("materialized_duplicate_group_members")
        )
    except Exception:
        has_tables = False

    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))

    if _normalize_decision(decision) == "approved":
        groups_all = _entity_merge_groups_for_upload(
            session,
            upload_id=upload_id,
            limit=limit,
            different_muhatap_code=different_muhatap_code,
        )
        total = len(groups_all)
        offset = (page - 1) * page_size
        return groups_all[offset : offset + page_size], total

    if not has_tables:
        groups_all = get_duplicate_groups(
            session,
            upload_id=upload_id,
            decision=decision,
            limit=limit,
            different_muhatap_code=different_muhatap_code,
        )
        total = len(groups_all)
        offset = (page - 1) * page_size
        return groups_all[offset : offset + page_size], total

    # materialized path
    from backend.models.database import (
        MaterializedDuplicateGroup,
        MaterializedDuplicateGroupMember,
    )

    q = session.query(MaterializedDuplicateGroup).filter(
        MaterializedDuplicateGroup.decision == decision
    )
    if upload_id is not None:
        q = q.filter(MaterializedDuplicateGroup.upload_id == upload_id)
    if different_muhatap_code:
        q = q.filter(MaterializedDuplicateGroup.different_muhatap_code.is_(True))

    total = int(q.count())
    group_rows = (
        q.order_by(
            MaterializedDuplicateGroup.avg_score.desc(),
            MaterializedDuplicateGroup.match_count.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    if not group_rows:
        return [], total

    group_ids = [int(g.id) for g in group_rows]
    member_rows = (
        session.query(
            MaterializedDuplicateGroupMember.group_id,
            MaterializedDuplicateGroupMember.normalized_record_id,
        )
        .filter(MaterializedDuplicateGroupMember.group_id.in_(group_ids))
        .all()
    )

    record_ids = sorted({int(rid) for _gid, rid in member_rows})
    record_by_id: dict[int, NormalizedRecord] = {}
    if record_ids:
        rows = (
            session.query(NormalizedRecord)
            .options(joinedload(NormalizedRecord.raw_record))
            .filter(NormalizedRecord.id.in_(record_ids))
            .all()
        )
        record_by_id = {int(r.id): r for r in rows}

    record_ids_by_group: dict[int, list[int]] = {}
    for gid, rid in member_rows:
        record_ids_by_group.setdefault(int(gid), []).append(int(rid))
    for gid in record_ids_by_group:
        record_ids_by_group[gid] = sorted(record_ids_by_group[gid])

    membership_by_record = _membership_snapshots_by_record(session, record_ids)
    weights, _thresholds = load_scoring_app_settings(session)

    groups: list[dict[str, Any]] = []
    for g in group_rows:
        member_ids = record_ids_by_group.get(int(g.id), [])
        pruned_ids = _record_ids_for_pending_group_display(
            session,
            member_ids,
            decision=decision,
            membership_by_record=membership_by_record,
        )
        if pruned_ids is None:
            continue
        member_ids = pruned_ids
        group_records = [record_by_id[rid] for rid in member_ids if rid in record_by_id]

        serialized_records = []
        for record in group_records:
            serialized_record = _serialize_group_record(record)
            membership = membership_by_record.get(int(record.id))
            serialized_record["membership_status"] = (
                membership.get("status", "pending") if membership is not None else "pending"
            )
            serialized_record["entity_id"] = (
                int(membership["entity_id"])
                if membership is not None and membership.get("entity_id") is not None
                else None
            )
            serialized_records.append(serialized_record)

        group_candidates = (
            session.query(MatchCandidate)
            .options(
                joinedload(MatchCandidate.left_record),
                joinedload(MatchCandidate.right_record),
            )
            .filter(MatchCandidate.detection_run_id == int(g.detection_run_id))
            .filter(MatchCandidate.decision == decision)
            .filter(MatchCandidate.left_id.in_(member_ids))
            .filter(MatchCandidate.right_id.in_(member_ids))
            .all()
            if member_ids
            else []
        )
        display_score, display_score_max = _group_display_scores(
            group_candidates,
            weights=weights,
        )
        if not group_candidates:
            display_score = round(float(g.avg_score or 0.0), 4)
            display_score_max = round(float(g.max_score or 0.0), 4)

        groups.append(
            {
                "group_id": f"dg_{int(g.id)}",
                "entity_id": None,
                "record_ids": member_ids,
                "pair_count": int(g.match_count or 0),
                "avg_score": display_score,
                "max_score": display_score_max,
                "group_score": display_score,
                "group_score_max": display_score_max,
                "match_count": int(g.match_count or 0),
                "match_candidate_ids": [],
                "muhatap_codes": list(g.muhatap_codes or []),
                "different_muhatap_code": bool(g.different_muhatap_code),
                "records": serialized_records,
                "golden_record": _build_golden_record(group_records),
            }
        )

    _hydrate_golden_records_from_entities(session, groups)
    return groups, total


def _find_duplicate_group(
    session: Session,
    group_id: str,
) -> dict[str, Any] | None:
    for decision in ("approved", "pending", "rejected"):
        for group in get_duplicate_groups(session, decision=decision, limit=50_000):
            if group.get("group_id") == group_id:
                return group
    return None


def _resolve_entity_for_partial_approval(
    session: Session,
    confirmed_records: list[NormalizedRecord],
) -> Entity:
    """
    Her kısmi Kaydet için yeni entity (ikinci/üçüncü birleştirme ayrı görünsün).
    Yalnızca aynı entity'deki tam onaylı kayıtlar yeniden kaydediliyorsa entity güncellenir.
    """
    approved_ids = sorted(int(record.id) for record in confirmed_records)
    memberships = (
        session.query(EntityMembership)
        .filter(EntityMembership.normalized_record_id.in_(approved_ids))
        .all()
    )
    confirmed_memberships = [
        membership
        for membership in memberships
        if _safe_str(membership.status).lower() == "confirmed"
    ]
    entity_ids = {int(membership.entity_id) for membership in confirmed_memberships}

    if (
        len(entity_ids) == 1
        and len(confirmed_memberships) == len(approved_ids)
        and len(memberships) == len(approved_ids)
    ):
        entity = (
            session.query(Entity)
            .filter(Entity.id == next(iter(entity_ids)))
            .first()
        )
        if entity is not None:
            return entity

    for membership in memberships:
        session.delete(membership)
    session.flush()

    golden_record = _build_golden_record(confirmed_records)
    entity = Entity(
        canonical_name=_safe_str(golden_record.get("clean_name")) or f"Entity {approved_ids[0]}",
        canonical_phone=_safe_str(golden_record.get("clean_phone")) or None,
        canonical_email=_safe_str(golden_record.get("clean_email")) or None,
        canonical_city=_safe_str(golden_record.get("clean_city")) or None,
        canonical_tc=_safe_str(golden_record.get("clean_tc")) or None,
        canonical_muhatap_no=_safe_str(golden_record.get("clean_muhatap_no")) or None,
        canonical_data=golden_record,
        donor_count=len(confirmed_records),
        confidence_score=1.0,
        confidence=1.0,
        merged_at=datetime.utcnow(),
    )
    session.add(entity)
    session.flush()
    return entity


def _sync_entity_donor_count(session: Session, entity_id: int) -> None:
    entity = session.query(Entity).filter(Entity.id == entity_id).first()
    if entity is None:
        return
    entity.donor_count = int(
        session.query(EntityMembership)
        .filter(
            EntityMembership.entity_id == entity_id,
            EntityMembership.status == "confirmed",
        )
        .count()
    )
    entity.updated_at = datetime.utcnow()


def _refresh_materialized_duplicate_groups_for_runs(
    session: Session,
    detection_run_ids: set[int],
) -> None:
    """Rebuild cached duplicate-group rows after manual review decisions."""
    if not detection_run_ids:
        return

    try:
        bind = session.get_bind()
        inspector = sa_inspect(bind) if bind is not None else None
        has_tables = bool(
            inspector
            and inspector.has_table("materialized_duplicate_groups")
            and inspector.has_table("materialized_duplicate_group_members")
        )
        if not has_tables:
            return

        from backend.models.database import MaterializedDuplicateGroup
        from backend.services.detection_service import (
            _materialize_duplicate_groups_from_match_candidates,
        )

        session.flush()
        runs = (
            session.query(DetectionRun)
            .filter(DetectionRun.id.in_(sorted(detection_run_ids)))
            .all()
        )
        run_by_id = {int(run.id): run for run in runs}

        (
            session.query(MaterializedDuplicateGroup)
            .filter(MaterializedDuplicateGroup.detection_run_id.in_(sorted(detection_run_ids)))
            .delete(synchronize_session=False)
        )
        session.flush()

        for run_id in sorted(detection_run_ids):
            run = run_by_id.get(run_id)
            if run is None or run.upload_id is None:
                continue
            _materialize_duplicate_groups_from_match_candidates(
                session=session,
                detection_run_id=run_id,
                upload_id=int(run.upload_id),
                normalization_run_id=(
                    int(run.normalization_run_id)
                    if run.normalization_run_id is not None
                    else None
                ),
            )
    except Exception:
        # Review decisions are the source of truth. If cache rebuild fails,
        # keep the decision save path working and let the legacy fallback or
        # a later detection run refresh the materialized view.
        return


def _finalize_entity_canonical_fields(
    session: Session,
    entity: Entity,
    confirmed_records: list[NormalizedRecord],
    golden_record_override: dict[str, Any] | None,
    *,
    excluded_records: list[NormalizedRecord] | None = None,
) -> NormalizedRecord | None:
    """Entity golden_record_id, canonical_data ve özet kolonlarını yazar."""
    if not confirmed_records:
        entity.golden_record_id = None
        entity.canonical_data = {}
        entity.canonical_name = f"Entity {entity.id}" if entity.id is not None else "Entity"
        entity.canonical_phone = None
        entity.canonical_email = None
        entity.canonical_city = None
        entity.canonical_tc = None
        entity.canonical_muhatap_no = None
        if entity.id is not None:
            _sync_entity_donor_count(session, int(entity.id))
        return None

    golden_source = sorted(
        confirmed_records,
        key=lambda record: (_record_completeness_score(record), int(record.id)),
        reverse=True,
    )[0]
    entity.golden_record_id = int(golden_source.id)
    canonical = _build_golden_record(confirmed_records)
    if golden_record_override:
        for key, value in golden_record_override.items():
            if key in _GOLDEN_VALUE_KEYS and value is not None:
                canonical[key] = _safe_str(value)
    if len(confirmed_records) >= 2:
        sources: list[dict[str, Any]] = []
        for record in sorted(confirmed_records, key=lambda r: int(r.id)):
            sources.append(
                {
                    "record_id": int(record.id),
                    "clean_name": _safe_str(record.clean_name),
                    "clean_muhatap_no": _record_group_muhatap_code(record)
                    or _safe_str(record.clean_muhatap_no),
                }
            )
        canonical["merged_muhatap_sources"] = sources
        snapshots: list[dict[str, Any]] = []
        for record in sorted(confirmed_records, key=lambda r: int(r.id)):
            snap = _serialize_group_record(record)
            snap["muhatap_no_effective"] = (
                _record_group_muhatap_code(record) or _safe_str(record.clean_muhatap_no)
            )
            raw_pl = _raw_payload(record)
            if raw_pl:
                snap["raw_payload"] = raw_pl
            snapshots.append(snap)
        canonical["merged_member_snapshots"] = snapshots

    if excluded_records:
        excluded_snapshots: list[dict[str, Any]] = []
        for record in sorted(excluded_records, key=lambda r: int(r.id)):
            snap = _serialize_group_record(record)
            snap["muhatap_no_effective"] = (
                _record_group_muhatap_code(record) or _safe_str(record.clean_muhatap_no)
            )
            raw_pl = _raw_payload(record)
            if raw_pl:
                snap["raw_payload"] = raw_pl
            excluded_snapshots.append(snap)
        canonical["excluded_member_snapshots"] = excluded_snapshots

    if len(confirmed_records) >= 2:
        from backend.services.muhatap_merge_report import build_merge_summary

        merge_summary = build_merge_summary(canonical)
        canonical["target_muhatap_code"] = merge_summary["target_muhatap_code"]
        canonical["prior_muhatap_codes"] = merge_summary["prior_muhatap_codes"]
        canonical["merged_muhatap_report_line"] = merge_summary["merged_muhatap_report_line"]
    else:
        for drop_key in (
            "merged_muhatap_sources",
            "merged_member_snapshots",
            "merged_muhatap_report_line",
            "target_muhatap_code",
            "prior_muhatap_codes",
        ):
            canonical.pop(drop_key, None)

    entity.canonical_data = canonical
    canonical_data = entity.canonical_data or {}
    entity.canonical_name = (
        _safe_str(canonical_data.get("clean_name"))
        or (f"Entity {entity.id}" if entity.id is not None else "Entity")
    )
    entity.canonical_phone = _safe_str(canonical_data.get("clean_phone")) or None
    entity.canonical_email = _safe_str(canonical_data.get("clean_email")) or None
    entity.canonical_city = _safe_str(canonical_data.get("clean_city")) or None
    entity.canonical_tc = _safe_str(canonical_data.get("clean_tc")) or None
    entity.canonical_muhatap_no = _safe_str(canonical_data.get("clean_muhatap_no")) or None
    _sync_entity_donor_count(session, int(entity.id))
    return golden_source


def _pair_decision_merge_into_entity(
    left_id: int,
    right_id: int,
    *,
    approved_union: set[int],
    pending_group_unselected: set[int],
) -> str:
    if left_id in approved_union and right_id in approved_union:
        return "approved"
    if left_id in pending_group_unselected or right_id in pending_group_unselected:
        if left_id in approved_union or right_id in approved_union:
            return "rejected"
        return "pending"
    return "pending"


def merge_pending_into_entity(
    session: Session,
    *,
    entity_id: int,
    group_id: str,
    record_ids: list[int],
    approved_record_ids: list[int],
    upload_id: int,
    golden_record_override: dict[str, Any] | None = None,
    note: str | None = None,
    reviewed_by: str | None = None,
    co_review_acknowledged: bool = False,
) -> dict[str, Any] | None:
    """Bekleyen gruptan seçilen kayıtları mevcut onaylı entity ile birleştirir."""
    record_id_set = sorted({int(r) for r in record_ids})
    approved_set = {int(r) for r in approved_record_ids}
    ids_set = set(record_id_set)
    if not approved_set.issubset(ids_set):
        raise ValueError("Seçilen kayıtlar grup listesine ait olmalıdır.")
    if len(approved_set) < 1:
        raise ValueError("En az bir kayıt seçmelisiniz.")

    entity = session.query(Entity).filter(Entity.id == int(entity_id)).first()
    if entity is None:
        return None

    min_rev = get_merge_min_reviewers(session)
    if min_rev > 1 and not co_review_acknowledged:
        raise ValueError(
            f"Ayarlar en az {min_rev} inceleme onayı gerektiriyor. İkinci incelemeyi tamamladıysanız "
            "istek gövdesinde co_review_acknowledged=true gönderin; yoksa Ayarlar'dan "
            "mukerrer_merge_min_reviewers değerini 1 yapın."
        )

    e_members = _confirmed_entity_member_ids(session, int(entity_id))
    if len(e_members | approved_set) < 2:
        raise ValueError("Birleşik grupta en az iki kayıt olmalıdır.")

    all_ids = ids_set | set(e_members)
    records = (
        session.query(NormalizedRecord)
        .options(joinedload(NormalizedRecord.raw_record))
        .filter(NormalizedRecord.id.in_(sorted(all_ids)))
        .all()
    )
    record_by_id = {int(r.id): r for r in records}
    missing = sorted(all_ids - set(record_by_id))
    if missing:
        raise ValueError(f"Normalized kayıt bulunamadı: {missing}")

    for rid in record_id_set:
        if int(record_by_id[rid].upload_id) != int(upload_id):
            raise ValueError(f"Kayıt {rid} bu yüklemeye ait değil.")

    for rid in e_members:
        if int(record_by_id[rid].upload_id) != int(upload_id):
            raise ValueError("Entity üyeleri seçili yüklemeye ait değil.")

    for rid in approved_set:
        foreign = (
            session.query(EntityMembership)
            .filter(
                EntityMembership.normalized_record_id == rid,
                EntityMembership.status == "confirmed",
                EntityMembership.entity_id != int(entity_id),
            )
            .first()
        )
        if foreign is not None:
            raise ValueError(
                f"Kayıt {rid} başka bir onaylı grupta (entity {foreign.entity_id}).",
            )

    confirmed_preview = [record_by_id[i] for i in sorted(e_members | approved_set)]
    proposed_muhatap = _proposed_muhatap_for_approval(confirmed_preview, golden_record_override)
    if proposed_muhatap:
        conflicts = _find_muhatap_conflicts_for_upload(
            session,
            int(upload_id),
            proposed_muhatap,
            exclude_entity_ids={int(entity_id)},
        )
        if conflicts:
            raise MuhatapConflictError(proposed_muhatap, conflicts)

    unselected_ids = sorted(ids_set - approved_set)
    if unselected_ids:
        session.query(EntityMembership).filter(
            EntityMembership.normalized_record_id.in_(unselected_ids),
        ).delete(synchronize_session=False)

    session.query(EntityMembership).filter(
        EntityMembership.normalized_record_id.in_(list(approved_set)),
        EntityMembership.entity_id != int(entity_id),
        EntityMembership.status == "confirmed",
    ).delete(synchronize_session=False)

    for rid in sorted(approved_set):
        row = (
            session.query(EntityMembership)
            .filter(
                EntityMembership.entity_id == int(entity_id),
                EntityMembership.normalized_record_id == rid,
            )
            .first()
        )
        if row is None:
            rec = record_by_id[rid]
            row = EntityMembership(
                entity_id=int(entity_id),
                normalized_record_id=rid,
                confidence_at_merge=float(_record_completeness_score(rec)),
                status="confirmed",
            )
            session.add(row)
        else:
            row.status = "confirmed"

    approved_union = e_members | approved_set
    pending_group_unselected = ids_set - approved_set
    universe = ids_set | set(e_members)

    run_id_rows = session.query(DetectionRun.id).filter(DetectionRun.upload_id == int(upload_id)).all()
    run_ids = [int(r[0]) for r in run_id_rows]
    if not run_ids:
        raise ValueError("Bu yükleme için detection run bulunamadı.")

    pair_candidates = (
        session.query(MatchCandidate)
        .filter(MatchCandidate.detection_run_id.in_(run_ids))
        .filter(MatchCandidate.left_id.in_(universe))
        .filter(MatchCandidate.right_id.in_(universe))
        .all()
    )
    if not pair_candidates:
        raise ValueError("Güncellenecek eşleşme çifti bulunamadı.")

    approved_pair_ids: list[int] = []
    rejected_pair_ids: list[int] = []
    pending_pair_ids: list[int] = []
    affected_detection_run_ids: set[int] = set()
    now = datetime.utcnow()
    for candidate in pair_candidates:
        if candidate.detection_run_id is not None:
            affected_detection_run_ids.add(int(candidate.detection_run_id))
        left_id = int(candidate.left_id)
        right_id = int(candidate.right_id)
        next_decision = _pair_decision_merge_into_entity(
            left_id,
            right_id,
            approved_union=approved_union,
            pending_group_unselected=pending_group_unselected,
        )
        if next_decision == "approved":
            approved_pair_ids.append(int(candidate.id))
        elif next_decision == "rejected":
            rejected_pair_ids.append(int(candidate.id))
        else:
            pending_pair_ids.append(int(candidate.id))

        if candidate.decision != next_decision:
            candidate.decision = next_decision
            reason = note or f"Merge into entity {entity_id} via {group_id}"
            session.add(
                ReviewAction(
                    match_id=candidate.id,
                    decision=next_decision,
                    decided_by=reviewed_by,
                    decided_at=now,
                    reason=reason,
                )
            )

    merged_member_ids = sorted(approved_union)
    confirmed_records = [record_by_id[i] for i in merged_member_ids if i in record_by_id]
    excluded_records_list: list[NormalizedRecord] | None = None
    if unselected_ids:
        excluded_records_list = [
            record_by_id[i] for i in unselected_ids if i in record_by_id
        ]

    golden_source = _finalize_entity_canonical_fields(
        session,
        entity,
        confirmed_records,
        golden_record_override,
        excluded_records=excluded_records_list,
    )

    session.add(
        AuditLog(
            action_type="merge_into_entity",
            entity_type="entity",
            entity_id=int(entity_id),
            payload={
                "group_id": group_id,
                "record_ids": record_id_set,
                "approved_record_ids": sorted(approved_set),
                "upload_id": upload_id,
                "unselected_record_ids": unselected_ids,
                "approved_pair_ids": approved_pair_ids,
                "note": note,
                "golden_record_id": int(golden_source.id) if golden_source else None,
            },
            created_by=reviewed_by,
        )
    )
    session.flush()
    _refresh_materialized_duplicate_groups_for_runs(session, affected_detection_run_ids)
    return {
        "entity_id": int(entity_id),
        "confirmed_count": len(approved_union),
        "excluded_count": len(unselected_ids),
        "golden_record_id": entity.golden_record_id,
        "approved_pair_count": len(approved_pair_ids),
        "rejected_pair_count": len(rejected_pair_ids),
        "pending_pair_count": len(pending_pair_ids),
    }


def remove_confirmed_member_from_entity(
    session: Session,
    *,
    entity_id: int,
    normalized_record_id: int,
    upload_id: int,
    reviewed_by: str | None = None,
) -> dict[str, Any] | None:
    """Onaylı birleşik entity üyeliğini kaldırır; eşleşme çiftlerini uygun biçimde günceller."""
    entity = session.query(Entity).filter(Entity.id == int(entity_id)).first()
    if entity is None:
        return None
    rid = int(normalized_record_id)
    rec = session.query(NormalizedRecord).filter(NormalizedRecord.id == rid).first()
    if rec is None:
        raise ValueError("Kayıt bulunamadı.")
    if int(rec.upload_id) != int(upload_id):
        raise ValueError("Kayıt bu yüklemeye ait değil.")

    e_members = _confirmed_entity_member_ids(session, int(entity_id))
    if rid not in e_members:
        raise ValueError("Kayıt bu onaylı grupta değil.")
    if len(e_members) < 2:
        raise ValueError("Grupta tek kayıt var; kaldırma bu ekrandan yapılamaz.")

    remaining = set(e_members) - {rid}
    removed_ok = remove_entity_membership(
        session,
        entity_id=int(entity_id),
        normalized_record_id=rid,
    )
    if not removed_ok:
        raise ValueError("Üyelik kaldırılamadı.")

    run_id_rows = session.query(DetectionRun.id).filter(DetectionRun.upload_id == int(upload_id)).all()
    run_ids = [int(r[0]) for r in run_id_rows]
    affected_detection_run_ids: set[int] = set()
    now = datetime.utcnow()
    if run_ids:
        candidates = (
            session.query(MatchCandidate)
            .filter(MatchCandidate.detection_run_id.in_(run_ids))
            .filter(or_(MatchCandidate.left_id == rid, MatchCandidate.right_id == rid))
            .all()
        )
        for candidate in candidates:
            if candidate.detection_run_id is not None:
                affected_detection_run_ids.add(int(candidate.detection_run_id))
            left_id = int(candidate.left_id)
            other = int(candidate.right_id) if left_id == rid else left_id
            if other in remaining:
                next_decision = "rejected"
            else:
                next_decision = "pending"
            if candidate.decision != next_decision:
                candidate.decision = next_decision
                session.add(
                    ReviewAction(
                        match_id=candidate.id,
                        decision=next_decision,
                        decided_by=reviewed_by,
                        decided_at=now,
                        reason=f"Removed record {rid} from entity {entity_id}",
                    )
                )

    pending_edge_count = 0
    pending_neighbor_record_ids: list[int] = []
    if run_ids:
        pend_rows = (
            session.query(MatchCandidate)
            .filter(MatchCandidate.detection_run_id.in_(run_ids))
            .filter(MatchCandidate.decision == "pending")
            .filter(or_(MatchCandidate.left_id == rid, MatchCandidate.right_id == rid))
            .all()
        )
        pending_edge_count = len(pend_rows)
        seen_neighbors: set[int] = set()
        for c in pend_rows:
            oid = int(c.right_id) if int(c.left_id) == rid else int(c.left_id)
            if oid not in seen_neighbors:
                seen_neighbors.add(oid)
                pending_neighbor_record_ids.append(oid)
        pending_neighbor_record_ids.sort()

    remaining_list = sorted(remaining)
    remaining_records = (
        session.query(NormalizedRecord)
        .options(joinedload(NormalizedRecord.raw_record))
        .filter(NormalizedRecord.id.in_(remaining_list))
        .all()
    )
    rem_by_id = {int(r.id): r for r in remaining_records}
    ordered_remaining = [rem_by_id[i] for i in remaining_list if i in rem_by_id]
    _finalize_entity_canonical_fields(session, entity, ordered_remaining, None, excluded_records=None)

    session.add(
        AuditLog(
            action_type="remove_entity_member",
            entity_type="entity",
            entity_id=int(entity_id),
            payload={
                "removed_record_id": rid,
                "upload_id": upload_id,
                "remaining_record_ids": remaining_list,
                "pending_edge_count": pending_edge_count,
                "pending_neighbor_record_ids": pending_neighbor_record_ids,
                "likely_visible_in_pending_heuristic": pending_edge_count > 0,
            },
            created_by=reviewed_by,
        )
    )
    session.flush()
    _refresh_materialized_duplicate_groups_for_runs(session, affected_detection_run_ids)
    return {
        "entity_id": int(entity_id),
        "removed_record_id": rid,
        "remaining_confirmed_count": len(remaining_list),
        "pending_edge_count": pending_edge_count,
        "pending_neighbor_record_ids": pending_neighbor_record_ids,
        "likely_visible_in_pending_heuristic": pending_edge_count > 0,
    }


def approve_group_partial(
    session: Session,
    group_id: str,
    approved_record_ids: list[int],
    rejected_record_ids: list[int],
    *,
    record_ids: list[int] | None = None,
    upload_id: int | None = None,
    decision: str | None = None,
    note: str | None = None,
    reviewed_by: str | None = None,
    golden_record_override: dict[str, Any] | None = None,
    co_review_acknowledged: bool = False,
) -> dict[str, Any] | None:
    requested_record_ids = [int(record_id) for record_id in (record_ids or [])]
    if requested_record_ids:
        record_ids = sorted(set(requested_record_ids))
    else:
        group = _find_duplicate_group(session, group_id)
        if group is None:
            return None
        record_ids = [int(record_id) for record_id in group.get("record_ids", [])]

    if len(record_ids) < 2:
        raise ValueError("Kısmi onay için aynı gruptan en az iki kayıt bilgisi gönderilmelidir.")

    approved_set = {int(record_id) for record_id in approved_record_ids}
    rejected_set = {int(record_id) for record_id in rejected_record_ids}
    unknown_ids = (approved_set | rejected_set) - set(record_ids)
    if unknown_ids:
        raise ValueError(f"Bu karar listesindeki kayıtlar gruba ait değil: {sorted(unknown_ids)}")
    overlap = approved_set & rejected_set
    if overlap:
        raise ValueError(f"Aynı kayıt hem onaylanıp hem reddedilemez: {sorted(overlap)}")
    if not approved_set and not rejected_set:
        raise ValueError("Kaydetmek için en az bir kayıt onaylanmalı veya reddedilmelidir.")

    pair_query = session.query(MatchCandidate).filter(
        MatchCandidate.left_id.in_(record_ids),
        MatchCandidate.right_id.in_(record_ids),
    )
    if upload_id is not None:
        pair_query = pair_query.join(DetectionRun).filter(DetectionRun.upload_id == upload_id)
    normalized_decision = _safe_str(decision).lower()

    pair_candidates = pair_query.all()
    if not pair_candidates:
        raise ValueError(
            "Bu grup için güncellenecek eşleşme çifti bulunamadı. "
            "Seçili yükleme, filtre veya kayıt listesi güncel olmayabilir."
        )

    records = (
        session.query(NormalizedRecord)
        .filter(NormalizedRecord.id.in_(record_ids))
        .all()
    )
    record_by_id = {int(record.id): record for record in records}
    ordered_records = [record_by_id[record_id] for record_id in record_ids if record_id in record_by_id]
    if len(ordered_records) != len(record_ids):
        missing_ids = sorted(set(record_ids) - set(record_by_id))
        raise ValueError(f"Normalized kayıt bulunamadı: {missing_ids}")

    confirmed_records = [
        record_by_id[record_id]
        for record_id in sorted(approved_set)
        if record_id in record_by_id
    ]
    if not confirmed_records:
        raise ValueError("Kaydetmek için en az bir kayıt onaylanmalıdır.")

    if len(approved_set) < 2:
        raise ValueError("Kaydetmek için en az iki kayıt seçmelisiniz.")

    min_rev = get_merge_min_reviewers(session)
    if min_rev > 1 and not co_review_acknowledged:
        raise ValueError(
            f"Ayarlar en az {min_rev} inceleme onayı gerektiriyor. İkinci incelemeyi tamamladıysanız "
            "istek gövdesinde co_review_acknowledged=true gönderin; yoksa Ayarlar'dan "
            "mukerrer_merge_min_reviewers değerini 1 yapın."
        )

    proposed_muhatap = _proposed_muhatap_for_approval(confirmed_records, golden_record_override)
    if upload_id is not None and proposed_muhatap:
        conflicts = _find_muhatap_conflicts_for_upload(
            session,
            int(upload_id),
            proposed_muhatap,
            exclude_entity_ids=set(),
        )
        if conflicts:
            raise MuhatapConflictError(proposed_muhatap, conflicts)

    unselected_ids = sorted(set(record_ids) - approved_set - rejected_set)
    if unselected_ids:
        session.query(EntityMembership).filter(
            EntityMembership.normalized_record_id.in_(unselected_ids),
        ).delete(synchronize_session=False)

    entity = _resolve_entity_for_partial_approval(session, confirmed_records)

    memberships = (
        session.query(EntityMembership)
        .filter(
            EntityMembership.entity_id == entity.id,
            EntityMembership.normalized_record_id.in_(list(approved_set)),
        )
        .all()
    )
    membership_by_record = {
        int(membership.normalized_record_id): membership
        for membership in memberships
    }

    for record in confirmed_records:
        record_id = int(record.id)
        membership = membership_by_record.get(record_id)
        if record_id in rejected_set:
            continue

        if membership is None:
            membership = EntityMembership(
                entity_id=entity.id,
                normalized_record_id=record_id,
                confidence_at_merge=_record_completeness_score(record),
            )
            session.add(membership)
            membership_by_record[record_id] = membership

        membership.status = "confirmed"

    for record_id in rejected_set:
        rejected_memberships = (
            session.query(EntityMembership)
            .filter(EntityMembership.normalized_record_id == int(record_id))
            .all()
        )
        for membership in rejected_memberships:
            session.delete(membership)

    approved_pair_ids: list[int] = []
    rejected_pair_ids: list[int] = []
    pending_pair_ids: list[int] = []
    split_pair_ids: list[int] = []
    affected_detection_run_ids: set[int] = set()
    now = datetime.utcnow()
    for candidate in pair_candidates:
        if candidate.detection_run_id is not None:
            affected_detection_run_ids.add(int(candidate.detection_run_id))
        left_id = int(candidate.left_id)
        right_id = int(candidate.right_id)
        next_decision = _partial_approval_pair_decision(
            left_id,
            right_id,
            approved_set=approved_set,
            rejected_set=rejected_set,
        )
        if next_decision == "approved":
            approved_pair_ids.append(int(candidate.id))
        elif next_decision == "rejected":
            rejected_pair_ids.append(int(candidate.id))
            if left_id in approved_set or right_id in approved_set:
                split_pair_ids.append(int(candidate.id))
        else:
            pending_pair_ids.append(int(candidate.id))

        if candidate.decision != next_decision:
            candidate.decision = next_decision
            reason = note or f"Partial approval via {group_id}"
            if int(candidate.id) in split_pair_ids and not note:
                reason = f"Partial split boundary via {group_id}"
            session.add(
                ReviewAction(
                    match_id=candidate.id,
                    decision=next_decision,
                    decided_by=reviewed_by,
                    decided_at=now,
                    reason=reason,
                )
            )

    excluded_records_list: list[NormalizedRecord] | None = None
    if unselected_ids:
        excluded_records_list = [
            record_by_id[record_id]
            for record_id in unselected_ids
            if record_id in record_by_id
        ]
    golden_source = _finalize_entity_canonical_fields(
        session,
        entity,
        confirmed_records,
        golden_record_override,
        excluded_records=excluded_records_list,
    )

    session.add(
        AuditLog(
            action_type="partial_approval",
            entity_type="entity",
            entity_id=entity.id,
            payload={
                "group_id": group_id,
                "record_ids": sorted(record_ids),
                "upload_id": upload_id,
                "decision_filter": normalized_decision or None,
                "approved_record_ids": sorted(approved_set),
                "rejected_record_ids": sorted(rejected_set),
                "pending_record_ids": sorted(set(record_ids) - approved_set - rejected_set),
                "approved_pair_ids": approved_pair_ids,
                "rejected_pair_ids": rejected_pair_ids,
                "pending_pair_ids": pending_pair_ids,
                "split_pair_ids": split_pair_ids,
                "golden_record_id": int(golden_source.id) if golden_source else None,
                "note": note,
            },
            created_by=reviewed_by,
        )
    )
    session.flush()
    _refresh_materialized_duplicate_groups_for_runs(session, affected_detection_run_ids)

    return {
        "entity_id": entity.id,
        "confirmed_count": len(approved_set),
        "excluded_count": len(set(record_ids) - approved_set - rejected_set),
        "excluded_record_ids": sorted(set(record_ids) - approved_set - rejected_set),
        "golden_record_id": entity.golden_record_id,
        "approved_pair_count": len(approved_pair_ids),
        "rejected_pair_count": len(rejected_pair_ids),
        "pending_pair_count": len(pending_pair_ids),
    }


def get_pending_match_candidates(
    session: Session,
    *,
    upload_id: int | None = None,
    limit: int = 50,
) -> list[MatchCandidate]:
    return get_match_candidates(
        session,
        upload_id=upload_id,
        decision="pending",
        limit=limit,
    )


def _pick_canonical_value(*values: str) -> str | None:
    for value in values:
        cleaned = _safe_str(value)
        if cleaned:
            return cleaned
    return None


def get_match_candidate(
    session: Session,
    match_id: int,
) -> MatchCandidate | None:
    return (
        session.query(MatchCandidate)
        .options(
            joinedload(MatchCandidate.left_record).joinedload(NormalizedRecord.raw_record),
            joinedload(MatchCandidate.right_record).joinedload(NormalizedRecord.raw_record),
        )
        .filter(MatchCandidate.id == match_id)
        .first()
    )


def approve_match_candidate(
    session: Session,
    *,
    match_id: int,
    approved_by: str,
    merge_into_entity: bool,
    canonical_name: str | None,
) -> tuple[MatchCandidate | None, Entity | None]:
    match_candidate = get_match_candidate(session, match_id)
    if match_candidate is None:
        return None, None
    if match_candidate.decision != "pending":
        raise ValueError(f"Match candidate is already {match_candidate.decision}")

    match_candidate.decision = "approved"
    confidence = _candidate_confidence(match_candidate)

    session.add(
        ReviewAction(
            match_id=match_candidate.id,
            decision="approved",
            decided_by=approved_by,
        )
    )

    entity: Entity | None = None
    if merge_into_entity and match_candidate.left_record and match_candidate.right_record:
        left_record = match_candidate.left_record
        right_record = match_candidate.right_record
        golden = _build_golden_record([left_record, right_record])
        ordered_for_golden = sorted(
            [left_record, right_record],
            key=lambda record: (_record_completeness_score(record), -int(record.id)),
            reverse=True,
        )
        golden_record_id = int(ordered_for_golden[0].id)
        entity = Entity(
            canonical_name=(
                _safe_str(canonical_name)
                or _pick_canonical_value(left_record.clean_name, right_record.clean_name)
                or _safe_str(golden.get("clean_name"))
                or f"Entity {match_candidate.id}"
            ),
            canonical_phone=_pick_canonical_value(
                left_record.clean_phone,
                right_record.clean_phone,
            )
            or _safe_str(golden.get("clean_phone"))
            or None,
            canonical_email=_pick_canonical_value(
                left_record.clean_email,
                right_record.clean_email,
            )
            or _safe_str(golden.get("clean_email"))
            or None,
            canonical_city=_pick_canonical_value(
                left_record.clean_city,
                right_record.clean_city,
            )
            or _safe_str(golden.get("clean_city"))
            or None,
            canonical_tc=_pick_canonical_value(
                left_record.clean_tc,
                right_record.clean_tc,
            )
            or _safe_str(golden.get("clean_tc"))
            or None,
            canonical_muhatap_no=_safe_str(golden.get("clean_muhatap_no")) or None,
            canonical_data=golden,
            golden_record_id=golden_record_id,
            confidence=confidence,
            donor_count=2,
            merged_count=1,
            confidence_score=confidence,
            merged_by=approved_by,
            merged_at=datetime.utcnow(),
        )
        session.add(entity)
        session.flush()

        seen_record_ids: set[int] = set()
        for normalized_record in (left_record, right_record):
            if normalized_record.id in seen_record_ids:
                continue
            seen_record_ids.add(normalized_record.id)
            session.add(
                EntityMembership(
                    entity_id=entity.id,
                    normalized_record_id=normalized_record.id,
                    confidence_at_merge=confidence,
                    status="confirmed",
                )
            )

    session.add(
        AuditLog(
            action_type="approve",
            entity_type="match",
            entity_id=match_candidate.id,
            payload={
                "match_id": match_candidate.id,
                "left_id": match_candidate.left_id,
                "right_id": match_candidate.right_id,
                "entity_id": entity.id if entity is not None else None,
                "decision": "approved",
                "confidence": confidence,
                "match_type": match_candidate.match_type,
            },
            created_by=approved_by,
        )
    )
    session.flush()
    return match_candidate, entity


def reject_match_candidate(
    session: Session,
    *,
    match_id: int,
    rejected_by: str,
    reason: str | None,
) -> MatchCandidate | None:
    match_candidate = get_match_candidate(session, match_id)
    if match_candidate is None:
        return None
    if match_candidate.decision != "pending":
        raise ValueError(f"Match candidate is already {match_candidate.decision}")

    match_candidate.decision = "rejected"

    session.add(
        ReviewAction(
            match_id=match_candidate.id,
            decision="rejected",
            decided_by=rejected_by,
            reason=reason,
        )
    )
    session.add(
        AuditLog(
            action_type="reject",
            entity_type="match",
            entity_id=match_candidate.id,
            payload={
                "match_id": match_candidate.id,
                "left_id": match_candidate.left_id,
                "right_id": match_candidate.right_id,
                "decision": "rejected",
                "reason": reason,
                "confidence": _candidate_confidence(match_candidate),
                "match_type": match_candidate.match_type,
            },
            created_by=rejected_by,
        )
    )
    session.flush()
    return match_candidate


def reset_match_candidate(
    session: Session,
    *,
    match_id: int,
    reason: str | None,
    reset_by: str | None,
) -> MatchCandidate | None:
    """
    Onay/red kararını geri alır: match pending olur; ilgili üyelikler pending'e çekilir.
    Ham/normalize kayıtlar silinmez.
    """
    match_candidate = get_match_candidate(session, match_id)
    if match_candidate is None:
        return None
    if match_candidate.decision not in {"approved", "rejected"}:
        raise ValueError("Yalnızca onaylanmış veya reddedilmiş eşleşmeler sıfırlanabilir.")

    target_records = {int(match_candidate.left_id), int(match_candidate.right_id)}
    memberships = (
        session.query(EntityMembership)
        .filter(EntityMembership.normalized_record_id.in_(target_records))
        .all()
    )
    entity_ids: set[int] = set()
    for membership in memberships:
        if int(membership.normalized_record_id) not in target_records:
            continue
        entity_ids.add(int(membership.entity_id))
        membership.status = "pending"

    now = datetime.utcnow()
    for entity_id in entity_ids:
        entity = session.query(Entity).filter(Entity.id == entity_id).first()
        if entity is None:
            continue
        confirmed = (
            session.query(EntityMembership)
            .filter(
                EntityMembership.entity_id == entity_id,
                EntityMembership.status == "confirmed",
            )
            .count()
        )
        entity.donor_count = int(confirmed)
        if confirmed == 0:
            entity.golden_record_id = None
        entity.updated_at = now

    match_candidate.decision = "pending"
    session.add(
        ReviewAction(
            match_id=match_candidate.id,
            decision="pending",
            decided_by=reset_by,
            decided_at=now,
            reason=reason or "Karar geri alındı",
        )
    )
    session.add(
        AuditLog(
            action_type="match_reset",
            entity_type="match",
            entity_id=match_candidate.id,
            payload={
                "match_id": match_candidate.id,
                "left_id": match_candidate.left_id,
                "right_id": match_candidate.right_id,
                "reason": reason,
                "entity_ids_touched": sorted(entity_ids),
            },
            created_by=reset_by,
        )
    )
    session.flush()
    return match_candidate


def get_match_candidate_statistics(session: Session, upload_id: int) -> dict[str, Any]:
    candidates = (
        session.query(MatchCandidate)
        .join(DetectionRun)
        .filter(DetectionRun.upload_id == upload_id)
        .all()
    )

    total = len(candidates)
    pending = sum(1 for candidate in candidates if candidate.decision == "pending")
    approved = sum(1 for candidate in candidates if candidate.decision == "approved")
    rejected = sum(1 for candidate in candidates if candidate.decision == "rejected")
    avg_score = (
        sum(_candidate_confidence(candidate) for candidate in candidates) / total
        if total > 0
        else 0.0
    )

    return {
        "total": total,
        "pending": pending,
        "confirmed": approved,
        "approved": approved,
        "rejected": rejected,
        "merged": approved,
        "avg_ml_score": round(avg_score, 4),
    }


def get_entity_memberships(
    session: Session,
    entity_id: int,
) -> list[EntityMembership]:
    return (
        session.query(EntityMembership)
        .options(
            joinedload(EntityMembership.normalized_record).joinedload(
                NormalizedRecord.raw_record
            )
        )
        .filter(EntityMembership.entity_id == entity_id)
        .order_by(EntityMembership.created_at.asc(), EntityMembership.id.asc())
        .all()
    )


def remove_entity_membership(
    session: Session,
    *,
    entity_id: int,
    normalized_record_id: int,
) -> bool:
    membership = (
        session.query(EntityMembership)
        .filter(
            EntityMembership.entity_id == entity_id,
            EntityMembership.normalized_record_id == normalized_record_id,
        )
        .first()
    )
    if membership is None:
        return False

    session.delete(membership)

    entity = session.query(Entity).filter(Entity.id == entity_id).first()
    if entity is not None:
        remaining = (
            session.query(EntityMembership)
            .filter(EntityMembership.entity_id == entity_id)
            .count()
        )
        entity.donor_count = max(0, remaining)
        entity.updated_at = datetime.utcnow()

    return True
