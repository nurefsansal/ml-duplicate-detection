from difflib import SequenceMatcher


def _safe_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _last_n_match(a: str, b: str, n: int) -> int:
    if not a or not b:
        return 0
    return int(a[-n:] == b[-n:])


def _split_name_parts(full_name: str) -> tuple[str, str]:
    """
    clean_name alanı canonical/sorted halde gelebilir.
    Basit yaklaşım:
    - ilk token -> first name proxy
    - son token -> surname proxy

    Bu mükemmel değil ama household risk için güçlü bir başlangıç sağlar.
    """
    full_name = _safe_str(full_name)
    if not full_name:
        return "", ""

    parts = [p for p in full_name.split() if p]
    if not parts:
        return "", ""

    if len(parts) == 1:
        return parts[0], parts[0]

    return parts[0], parts[-1]


def build_pair_features(left: dict, right: dict) -> dict:
    left_name = _safe_str(left.get("clean_name"))
    right_name = _safe_str(right.get("clean_name"))

    left_tc = _safe_str(left.get("clean_tc"))
    right_tc = _safe_str(right.get("clean_tc"))

    left_phone = _safe_str(left.get("clean_phone"))
    right_phone = _safe_str(right.get("clean_phone"))

    left_email = _safe_str(left.get("clean_email"))
    right_email = _safe_str(right.get("clean_email"))

    left_city = _safe_str(left.get("clean_city"))
    right_city = _safe_str(right.get("clean_city"))

    left_phonetic = _safe_str(left.get("name_phonetic_key"))
    right_phonetic = _safe_str(right.get("name_phonetic_key"))

    left_first, left_surname = _split_name_parts(left_name)
    right_first, right_surname = _split_name_parts(right_name)

    first_name_similarity = round(_similarity(left_first, right_first), 4)
    surname_similarity = round(_similarity(left_surname, right_surname), 4)

    first_name_exact_match = int(bool(left_first and right_first and left_first == right_first))
    surname_exact_match = int(bool(left_surname and right_surname and left_surname == right_surname))

    tc_exact_match = int(bool(left_tc and right_tc and left_tc == right_tc))
    phone_exact_match = int(bool(left_phone and right_phone and left_phone == right_phone))
    email_exact_match = int(bool(left_email and right_email and left_email == right_email))
    city_exact_match = int(bool(left_city and right_city and left_city == right_city))
    phonetic_exact_match = int(bool(left_phonetic and right_phonetic and left_phonetic == right_phonetic))

    shared_contact_flag = int(bool(phone_exact_match or email_exact_match))

    shared_contact_name_conflict = int(
        bool(
            shared_contact_flag
            and first_name_similarity < 0.55
            and surname_similarity >= 0.80
        )
    )

    household_risk_flag = int(
        bool(
            (phone_exact_match or email_exact_match)
            and surname_similarity >= 0.80
            and first_name_similarity < 0.70
        )
    )

    tc_conflict = int(bool(left_tc and right_tc and left_tc != right_tc))

    return {
        "tc_exact_match": tc_exact_match,
        "tc_conflict": tc_conflict,
        "phone_exact_match": phone_exact_match,
        "phone_last7_match": _last_n_match(left_phone, right_phone, 7),
        "email_exact_match": email_exact_match,
        "city_exact_match": city_exact_match,
        "phonetic_exact_match": phonetic_exact_match,
        "name_similarity": round(_similarity(left_name, right_name), 4),
        "email_similarity": round(_similarity(left_email, right_email), 4),
        "first_name_similarity": first_name_similarity,
        "surname_similarity": surname_similarity,
        "first_name_exact_match": first_name_exact_match,
        "surname_exact_match": surname_exact_match,
        "shared_contact_flag": shared_contact_flag,
        "shared_contact_name_conflict": shared_contact_name_conflict,
        "household_risk_flag": household_risk_flag,
        "common_non_empty_fields": sum(
            [
                int(bool(left_tc and right_tc)),
                int(bool(left_phone and right_phone)),
                int(bool(left_email and right_email)),
                int(bool(left_name and right_name)),
                int(bool(left_city and right_city)),
            ]
        ),
    }