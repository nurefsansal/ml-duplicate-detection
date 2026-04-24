from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func
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
from backend.services.advanced_matching_service import jaro_winkler_similarity


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def _record_raw_address(record: NormalizedRecord) -> str:
    return _pick_payload_value(
        [_raw_payload(record), _normalized_payload(record)],
        "Adres",
        "address",
        "adres",
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
        similarity = jaro_winkler_similarity(normalized_left, normalized_right)
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

    return {
        "fullName": _build_similarity_field_comparison(
            raw_left=_record_raw_name(left_record),
            raw_right=_record_raw_name(right_record),
            normalized_left=_safe_str(left_record.clean_name),
            normalized_right=_safe_str(right_record.clean_name),
            comparison_method="admin_review_jaro_winkler(clean_name)",
            field_name="Ad soyad",
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
        "phone": _build_exact_field_comparison(
            raw_left=_record_raw_phone(left_record),
            raw_right=_record_raw_phone(right_record),
            normalized_left=_safe_str(left_record.clean_phone),
            normalized_right=_safe_str(right_record.clean_phone),
            comparison_method="admin_review_exact(clean_phone)",
            field_name="Telefon",
        ),
        "email": _build_exact_field_comparison(
            raw_left=_record_raw_email(left_record),
            raw_right=_record_raw_email(right_record),
            normalized_left=_safe_str(left_record.clean_email),
            normalized_right=_safe_str(right_record.clean_email),
            comparison_method="admin_review_exact(clean_email)",
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
        "address": _build_similarity_field_comparison(
            raw_left=_record_raw_address(left_record),
            raw_right=_record_raw_address(right_record),
            normalized_left=_safe_str(left_record.clean_address),
            normalized_right=_safe_str(right_record.clean_address),
            comparison_method="admin_review_jaro_winkler(clean_address)",
            field_name="Adres",
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

    return {
        "tc_exact_match": int(field_comparisons["tc"]["exactMatch"]),
        "tc_conflict": int(bool(left_tc and right_tc and left_tc != right_tc)),
        "phone_exact_match": int(field_comparisons["phone"]["exactMatch"]),
        "email_exact_match": int(field_comparisons["email"]["exactMatch"]),
        "city_exact_match": int(field_comparisons["city"]["exactMatch"]),
        "first_name_exact_match": int(field_comparisons["firstName"]["exactMatch"]),
        "surname_exact_match": int(field_comparisons["surname"]["exactMatch"]),
        "name_similarity": round(field_comparisons["fullName"]["score0To100"] / 100, 4),
        "first_name_similarity": round(
            field_comparisons["firstName"]["score0To100"] / 100,
            4,
        ),
        "surname_similarity": round(
            field_comparisons["surname"]["score0To100"] / 100,
            4,
        ),
        "shared_contact_flag": int(
            bool(
                (left_phone and right_phone and left_phone == right_phone)
                or (left_email and right_email and left_email == right_email)
            )
        ),
        "common_non_empty_fields": sum(
            [
                int(bool(left_name and right_name)),
                int(bool(left_tc and right_tc)),
                int(bool(left_phone and right_phone)),
                int(bool(left_email and right_email)),
                int(bool(left_city and right_city)),
            ]
        ),
    }


def _build_risk_flags(features: dict[str, Any]) -> list[str]:
    risk_flags: list[str] = []
    if features.get("tc_conflict", 0):
        risk_flags.append("tc_conflict")
    if features.get("shared_contact_flag", 0):
        risk_flags.append("shared_contact")
    if int(features.get("common_non_empty_fields", 0) or 0) <= 2:
        risk_flags.append("sparse_data")
    return risk_flags


def _build_rule_reasons(
    match_candidate: MatchCandidate,
    features: dict[str, Any],
    field_comparisons: dict[str, dict[str, Any]],
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

    full_name_result = field_comparisons["fullName"]["comparisonResult"]
    if full_name_result in {"exact_match", "strong_match", "partial_match"}:
        reasons.append(f"Ad soyad sonucu: {full_name_result}.")

    reasons.append("Nihai durum manuel inceleme icin beklemede.")
    return reasons


def _candidate_confidence(match_candidate: MatchCandidate) -> float:
    return _safe_float(
        match_candidate.confidence,
        default=_safe_float(match_candidate.score),
    )


def serialize_match_candidate(match_candidate: MatchCandidate) -> dict[str, Any]:
    left_record = match_candidate.left_record
    right_record = match_candidate.right_record

    if left_record is None or right_record is None:
        raise ValueError("Match candidate is missing normalized record joins")

    field_comparisons = _build_field_comparisons(left_record, right_record)
    features = _derive_features(left_record, right_record, field_comparisons)
    risk_flags = _build_risk_flags(features)
    rule_reasons = _build_rule_reasons(match_candidate, features, field_comparisons)
    confidence = _candidate_confidence(match_candidate)

    return {
        "id": match_candidate.id,
        "left_id": match_candidate.left_id,
        "right_id": match_candidate.right_id,
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
        "donor2_name": _safe_str(right_record.clean_name),
        "donor2_email": _safe_str(right_record.clean_email) or None,
        "donor2_phone": _safe_str(right_record.clean_phone) or None,
        "donor2_city": _safe_str(right_record.clean_city) or None,
        "donor2_tc": _safe_str(right_record.clean_tc) or None,
        "ml_score": confidence,
        "decision_reason": None,
        "features": features,
        "fieldComparisons": field_comparisons,
        "riskFlags": risk_flags,
        "ruleReasons": rule_reasons,
        "decisionSource": _safe_str(match_candidate.match_type) or "match_candidate",
        "finalDecision": "review",
        "splinkMatchProbability": confidence,
        "splinkMatchWeight": None,
        "created_at": match_candidate.created_at.isoformat() if match_candidate.created_at else None,
    }


def get_pending_match_candidates(
    session: Session,
    *,
    upload_id: int | None = None,
    limit: int = 50,
) -> list[MatchCandidate]:
    query = (
        session.query(MatchCandidate)
        .options(
            joinedload(MatchCandidate.detection_run),
            joinedload(MatchCandidate.left_record).joinedload(NormalizedRecord.raw_record),
            joinedload(MatchCandidate.right_record).joinedload(NormalizedRecord.raw_record),
        )
        .filter(MatchCandidate.decision == "pending")
    )

    if upload_id is not None:
        query = query.join(DetectionRun).filter(DetectionRun.upload_id == upload_id)

    return (
        query.order_by(
            func.coalesce(MatchCandidate.confidence, MatchCandidate.score).desc(),
            MatchCandidate.created_at.desc(),
        )
        .limit(limit)
        .all()
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
        entity = Entity(
            canonical_name=(
                _safe_str(canonical_name)
                or _pick_canonical_value(left_record.clean_name, right_record.clean_name)
                or f"Entity {match_candidate.id}"
            ),
            canonical_phone=_pick_canonical_value(
                left_record.clean_phone,
                right_record.clean_phone,
            ),
            canonical_email=_pick_canonical_value(
                left_record.clean_email,
                right_record.clean_email,
            ),
            canonical_city=_pick_canonical_value(
                left_record.clean_city,
                right_record.clean_city,
            ),
            canonical_tc=_pick_canonical_value(
                left_record.clean_tc,
                right_record.clean_tc,
            ),
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
