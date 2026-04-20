def resolve_match_decision(probability: float, features: dict) -> str:
    """
    Domain-aware karar motoru:
    - ortak telefon/email tek başına merge sebebi değildir
    - aile/household riski varsa review veya different_person
    - tc conflict varsa direkt farklı kişi
    """

    if features.get("tc_conflict", 0) == 1:
        return "different_person"

    household_risk = features.get("household_risk_flag", 0) == 1
    shared_contact_name_conflict = features.get("shared_contact_name_conflict", 0) == 1

    tc_exact = features.get("tc_exact_match", 0) == 1
    first_name_exact = features.get("first_name_exact_match", 0) == 1
    surname_exact = features.get("surname_exact_match", 0) == 1
    name_similarity = features.get("name_similarity", 0.0)

    # Ortak telefon/email + isim çatışması => asla otomatik birleştirme yok
    if household_risk or shared_contact_name_conflict:
        if tc_exact and first_name_exact:
            return "review"
        return "different_person"

    # En güçlü otomatik birleştirme
    if tc_exact and (first_name_exact or name_similarity >= 0.90):
        if probability >= 0.90:
            return "same_person"
        return "review"

    # Genel yüksek güven
    if probability >= 0.97 and first_name_exact and surname_exact:
        return "same_person"

    # Orta güven -> inceleme
    if probability >= 0.80:
        return "review"

    return "different_person"