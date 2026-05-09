from __future__ import annotations

from typing import Any

from backend.services.decision_thresholds import DecisionThresholdsProb


def resolve_match_decision(
    probability: float,
    features: dict,
    *,
    thresholds: DecisionThresholdsProb | None = None,
) -> str:
    """Backward-compatible: returns only the decision string."""
    decision, _ = resolve_match_decision_with_trace(probability, features, thresholds=thresholds)
    return decision


def resolve_match_decision_with_trace(
    probability: float,
    features: dict,
    *,
    thresholds: DecisionThresholdsProb | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    TC-first karar motoru + Ayarlar esikleri (olasilik 0-1).

    Kural hiyerarsisi:
    1. TC catismasi / hanehalki riski gibi guvenlik kurallari ayarlardan gucludur.
    2. Otomatik onay / bekleme / red icin olasilik esikleri (otoOnayla, bayrakla, yoksay).

    Returns:
        (decision, safety_overrides) where safety_overrides entries look like
        {"rule": str, "effect": str, "detail": str}.
    """
    t = thresholds or DecisionThresholdsProb.from_raw(None)
    score = float(probability or 0.0)
    safety_overrides: list[dict[str, Any]] = []

    def _override(rule: str, effect: str, detail: str) -> None:
        safety_overrides.append({"rule": rule, "effect": effect, "detail": detail})

    tc_conflict = features.get("tc_conflict", 0) == 1
    tc_exact = features.get("tc_exact_match", 0) == 1
    phone_exact = features.get("phone_exact_match", 0) == 1
    email_exact = features.get("email_exact_match", 0) == 1
    city_exact = features.get("city_exact_match", 0) == 1
    same_surname_name_conflict = features.get("same_surname_name_conflict", 0) == 1
    muhatap_exact = features.get("muhatap_no_exact_match", 0) == 1
    muhatap_conflict = features.get("muhatap_no_conflict", 0) == 1
    household_risk = features.get("household_risk_flag", 0) == 1

    name_similarity = float(features.get("name_similarity", 0.0) or 0.0)
    first_name_similarity = float(features.get("first_name_similarity", 0.0) or 0.0)
    surname_similarity = float(features.get("surname_similarity", 0.0) or 0.0)
    first_name_exact = features.get("first_name_exact_match", 0) == 1
    surname_exact = features.get("surname_exact_match", 0) == 1

    name_is_strong = bool(
        (first_name_exact and surname_similarity >= 0.85)
        or (surname_exact and first_name_similarity >= 0.85)
        or (first_name_similarity >= 0.85 and surname_similarity >= 0.85)
        or name_similarity >= 0.90
    )
    strong_identity_signal = bool(phone_exact or email_exact or muhatap_exact)
    tc_support_signal = bool(name_is_strong or strong_identity_signal or city_exact)
    name_only_risk = bool(
        name_similarity >= 0.85
        and not phone_exact
        and not email_exact
        and not muhatap_exact
        and not tc_exact
    )

    t_reject = t.reject
    t_manual = t.manual_review
    t_auto = t.auto_approve

    # 1) TC conflict -> settings cannot approve.
    if tc_conflict:
        _override("tc_conflict", "safety", "TC Kimlik No cakismasi; otomatik onay engellendi.")
        if strong_identity_signal:
            return "pending", safety_overrides
        return "rejected", safety_overrides

    # 2) TC exact remains strong, but now needs at least one supporting signal.
    if tc_exact:
        if household_risk or muhatap_conflict or same_surname_name_conflict:
            if household_risk:
                _override("household_risk_flag", "safety", "Hanehalki riski; manuel inceleme.")
            if muhatap_conflict:
                _override("muhatap_no_conflict", "safety", "Muhatap kodu cakismasi; manuel inceleme.")
            if same_surname_name_conflict:
                _override("same_surname_name_conflict", "safety", "Isim-soyad celiskisi; manuel inceleme.")
            return "pending", safety_overrides
        if tc_support_signal:
            return "approved", safety_overrides
        _override(
            "tc_exact_needs_support",
            "safety",
            "TC Kimlik No eslesiyor ancak destekleyici isim veya iletisim sinyali yetersiz.",
        )
        return "pending", safety_overrides

    # 3) TC yokken name-only ile approved verme.
    if name_only_risk:
        _override("name_only_risk", "safety", "Yalnizca isim sinyali; kimlik dogrulamasi zayif.")
        if score >= t_reject:
            return "pending", safety_overrides
        return "rejected", safety_overrides

    # 4) Household -> stronger than auto-approve band.
    if household_risk:
        _override("household_risk_flag", "safety", "Hanehalki riski; otomatik onay yok.")
        return "pending", safety_overrides

    if muhatap_conflict:
        _override("muhatap_no_conflict", "safety", "Muhatap kodu cakismasi.")
        if score >= t_manual:
            return "pending", safety_overrides
        return "rejected", safety_overrides

    if same_surname_name_conflict and not strong_identity_signal:
        _override("same_surname_name_conflict", "safety", "Soyad ayni, ad sinyali zayif.")
        if score >= t_reject:
            return "pending", safety_overrides
        return "rejected", safety_overrides

    # TC yokken approved icin en az bir guclu identity sinyali zorunlu.
    if strong_identity_signal and name_is_strong and score >= t_auto:
        return "approved", safety_overrides
    if strong_identity_signal:
        if score >= t_manual:
            return "pending", safety_overrides
        return "rejected", safety_overrides
    if name_is_strong or city_exact:
        if score >= t_manual:
            return "pending", safety_overrides
        return "rejected", safety_overrides

    return "rejected", safety_overrides
