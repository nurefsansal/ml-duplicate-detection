def resolve_match_decision(probability: float, features: dict) -> str:
    """
    TC-first karar motoru.

    Kural hiyerarşisi:
    1. TC varsa → TC'ye göre karar ver (diğer sinyaller ikincil)
    2. TC yoksa → çoklu güçlü sinyal gereksinimi (sadece isim yetmez)

    Returns: approved | pending | rejected
    """
    score = float(probability or 0.0)

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
    first_name_exact = features.get("first_name_exact_match", 0) == 1
    surname_exact = features.get("surname_exact_match", 0) == 1

    name_is_strong = bool(
        first_name_exact
        or (surname_exact and name_similarity >= 0.85)
        or name_similarity >= 0.90
    )
    strong_identity_signal = bool(phone_exact or email_exact or muhatap_exact)
    name_only_risk = bool(
        name_similarity >= 0.85
        and not phone_exact
        and not email_exact
        and not muhatap_exact
        and not tc_exact
    )

    # 1) TC conflict varsa approved kesinlikle yasak.
    if tc_conflict:
        if strong_identity_signal:
            return "pending"
        return "rejected"

    # 2) TC exact varsa kural tabanli oncelik.
    if tc_exact:
        if household_risk or muhatap_conflict or same_surname_name_conflict:
            return "pending"
        return "approved"

    # 3) TC iki tarafta da yoksa name-only ile approved verme.
    if name_only_risk:
        return "pending" if score >= 0.40 else "rejected"

    # 4) Fuzzy sinyaller yardimci; tek basina approved olmasin.
    if household_risk:
        return "pending"
    if muhatap_conflict:
        return "pending" if score >= 0.60 else "rejected"
    if same_surname_name_conflict and not strong_identity_signal:
        return "pending" if score >= 0.40 else "rejected"

    # TC yokken approved icin en az bir guclu identity sinyali zorunlu.
    if strong_identity_signal and name_is_strong and score >= 0.60:
        return "approved"
    if strong_identity_signal:
        return "pending"
    if name_is_strong or city_exact:
        return "pending" if score >= 0.50 else "rejected"

    return "rejected"
