from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, inspect as sa_inspect, text
from sqlalchemy.orm import Session, joinedload

from backend.models.database import (
    AuditLog,
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
from backend.services.ml_service import predict_match_probability
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
    shared_contact_flag = int(
        bool(
            (left_phone and right_phone and left_phone == right_phone)
            or (left_email and right_email and left_email == right_email)
        )
    )
    same_surname_name_conflict_flag = int(
        same_surname_name_conflict(left_ordered_name, right_ordered_name)
    )

    return {
        "tc_exact_match": int(field_comparisons["tc"]["exactMatch"]),
        "tc_conflict": int(bool(left_tc and right_tc and left_tc != right_tc)),
        "muhatap_no_exact_match": int(field_comparisons["muhatapNo"]["exactMatch"]),
        "muhatap_no_conflict": int(bool(left_muhatap and right_muhatap and left_muhatap != right_muhatap)),
        "phone_exact_match": int(field_comparisons["phone"]["exactMatch"]),
        "phone_similarity": round(field_comparisons["phone"]["score0To100"] / 100, 4),
        "email_exact_match": int(field_comparisons["email"]["exactMatch"]),
        "email_similarity": round(field_comparisons["email"]["score0To100"] / 100, 4),
        "city_exact_match": int(field_comparisons["city"]["exactMatch"]),
        "first_name_exact_match": int(field_comparisons["firstName"]["exactMatch"]),
        "surname_exact_match": int(field_comparisons["surname"]["exactMatch"]),
        "name_similarity": round(field_comparisons["fullName"]["score0To100"] / 100, 4),
        "name_token_similarity": round(
            token_name_similarity(left_ordered_name, right_ordered_name),
            4,
        ),
        "first_name_similarity": round(
            field_comparisons["firstName"]["score0To100"] / 100,
            4,
        ),
        "surname_similarity": round(
            field_comparisons["surname"]["score0To100"] / 100,
            4,
        ),
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


def get_match_candidates(
    session: Session,
    *,
    upload_id: int | None = None,
    decision: str | None = None,
    limit: int = 50,
    latest_only: bool = True,
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

    return (
        query.order_by(
            func.coalesce(MatchCandidate.confidence, MatchCandidate.score).desc(),
            MatchCandidate.created_at.desc(),
        )
        .limit(limit)
        .all()
    )


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


def get_duplicate_groups(
    session: Session,
    *,
    upload_id: int | None = None,
    decision: str = "approved",
    limit: int = 5000,
    different_muhatap_code: bool = False,
) -> list[dict[str, Any]]:
    candidates = get_match_candidates(
        session,
        upload_id=upload_id,
        decision=decision,
        limit=limit,
        latest_only=False,
    )
    if not candidates:
        return []

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

        component_index += 1
        component_ids = sorted(component)
        match_candidates_in_group = [
            candidate
            for (left_id, right_id), candidate in edge_by_pair.items()
            if left_id in component and right_id in component
        ]
        match_scores = [
            _candidate_confidence(candidate) for candidate in match_candidates_in_group
        ]
        group_score = round(
            (sum(match_scores) / len(match_scores)) if match_scores else 0.0,
            4,
        )
        score_max = round(max(match_scores), 4) if match_scores else 0.0

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
        entity_ids = [
            int(membership["entity_id"])
            for membership in membership_by_record.values()
            if membership.get("entity_id") is not None
        ]
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
                "entity_id": entity_ids[0] if entity_ids else None,
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
    return groups


def _find_duplicate_group(
    session: Session,
    group_id: str,
) -> dict[str, Any] | None:
    for decision in ("approved", "pending", "rejected"):
        for group in get_duplicate_groups(session, decision=decision, limit=50_000):
            if group.get("group_id") == group_id:
                return group
    return None


def _get_or_create_entity_for_group(
    session: Session,
    records: list[NormalizedRecord],
) -> Entity:
    record_ids = [int(record.id) for record in records]
    existing_memberships = (
        session.query(EntityMembership)
        .filter(EntityMembership.normalized_record_id.in_(record_ids))
        .all()
    )
    if existing_memberships:
        entity_id_counts: dict[int, int] = {}
        for membership in existing_memberships:
            entity_id_counts[int(membership.entity_id)] = (
                entity_id_counts.get(int(membership.entity_id), 0) + 1
            )
        entity_id = sorted(
            entity_id_counts,
            key=lambda current_id: entity_id_counts[current_id],
            reverse=True,
        )[0]
        entity = session.query(Entity).filter(Entity.id == entity_id).first()
        if entity is not None:
            return entity

    golden_record = _build_golden_record(records)
    entity = Entity(
        canonical_name=_safe_str(golden_record.get("clean_name")) or f"Entity {record_ids[0]}",
        canonical_phone=_safe_str(golden_record.get("clean_phone")) or None,
        canonical_email=_safe_str(golden_record.get("clean_email")) or None,
        canonical_city=_safe_str(golden_record.get("clean_city")) or None,
        canonical_tc=_safe_str(golden_record.get("clean_tc")) or None,
        canonical_muhatap_no=_safe_str(golden_record.get("clean_muhatap_no")) or None,
        canonical_data=golden_record,
        donor_count=len(records),
        confidence_score=1.0,
        confidence=1.0,
        merged_at=datetime.utcnow(),
    )
    session.add(entity)
    session.flush()
    return entity


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
    if normalized_decision in {"pending", "approved", "rejected"}:
        pair_query = pair_query.filter(MatchCandidate.decision == normalized_decision)

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

    entity = _get_or_create_entity_for_group(session, ordered_records)

    memberships = (
        session.query(EntityMembership)
        .filter(
            EntityMembership.entity_id == entity.id,
            EntityMembership.normalized_record_id.in_(record_ids),
        )
        .all()
    )
    membership_by_record = {
        int(membership.normalized_record_id): membership
        for membership in memberships
    }

    for record in ordered_records:
        record_id = int(record.id)
        membership = membership_by_record.get(record_id)
        if record_id in rejected_set:
            if membership is not None:
                session.delete(membership)
                membership_by_record.pop(record_id, None)
            continue

        if membership is None:
            membership = EntityMembership(
                entity_id=entity.id,
                normalized_record_id=record_id,
                confidence_at_merge=_record_completeness_score(record),
            )
            session.add(membership)
            membership_by_record[record_id] = membership

        if record_id in approved_set:
            membership.status = "confirmed"
        else:
            membership.status = "pending"

    approved_pair_ids: list[int] = []
    rejected_pair_ids: list[int] = []
    pending_pair_ids: list[int] = []
    now = datetime.utcnow()
    for candidate in pair_candidates:
        left_id = int(candidate.left_id)
        right_id = int(candidate.right_id)
        if left_id in approved_set and right_id in approved_set:
            next_decision = "approved"
            approved_pair_ids.append(int(candidate.id))
        elif left_id in rejected_set or right_id in rejected_set:
            next_decision = "rejected"
            rejected_pair_ids.append(int(candidate.id))
        else:
            next_decision = "pending"
            pending_pair_ids.append(int(candidate.id))

        if candidate.decision != next_decision:
            candidate.decision = next_decision
            session.add(
                ReviewAction(
                    match_id=candidate.id,
                    decision=next_decision,
                    decided_by=reviewed_by,
                    decided_at=now,
                    reason=note or f"Partial approval via {group_id}",
                )
            )

    confirmed_records = [
        record
        for record in ordered_records
        if int(record.id) in approved_set
    ]
    golden_source = None
    if confirmed_records:
        golden_source = sorted(
            confirmed_records,
            key=lambda record: (_record_completeness_score(record), int(record.id)),
            reverse=True,
        )[0]
        entity.golden_record_id = int(golden_source.id)
        entity.canonical_data = _build_golden_record(confirmed_records)
    else:
        entity.golden_record_id = None
        entity.canonical_data = {}

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
    entity.donor_count = len(approved_set)
    entity.updated_at = datetime.utcnow()

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
                "golden_record_id": int(golden_source.id) if golden_source else None,
                "note": note,
            },
            created_by=reviewed_by,
        )
    )
    session.flush()

    return {
        "entity_id": entity.id,
        "confirmed_count": len(approved_set),
        "excluded_count": len(rejected_set),
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
