from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any

from backend.services.advanced_matching_service import (
    hybrid_name_similarity,
    jaro_winkler_similarity,
    levenshtein_similarity,
    same_surname_name_conflict,
    token_name_similarity,
)


def _safe_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _max_similarity(a: str, b: str) -> float:
    seq_sim = _similarity(a, b)
    jw_sim = jaro_winkler_similarity(a, b)
    lev_sim = levenshtein_similarity(a, b)
    return round(max(seq_sim, jw_sim, lev_sim), 4)


def normalize_email_for_similarity(email: str) -> str:
    value = _safe_str(email).lower()
    if not value or "@" not in value:
        return value
    username, domain = value.rsplit("@", 1)
    username = username.split("+", 1)[0]
    if domain in {"gmail.com", "googlemail.com"}:
        username = username.replace(".", "")
    return f"{username}@{domain}"


def email_similarity_score(left: str, right: str) -> float:
    left_raw = _safe_str(left).lower()
    right_raw = _safe_str(right).lower()
    if not left_raw or not right_raw:
        return 0.0

    left_norm = normalize_email_for_similarity(left_raw)
    right_norm = normalize_email_for_similarity(right_raw)
    if left_norm and left_norm == right_norm:
        return 1.0

    if "@" not in left_norm or "@" not in right_norm:
        return round(SequenceMatcher(None, left_norm, right_norm).ratio(), 4)

    left_user, left_domain = left_norm.rsplit("@", 1)
    right_user, right_domain = right_norm.rsplit("@", 1)

    username_similarity = SequenceMatcher(None, left_user, right_user).ratio()
    domain_match = float(left_domain == right_domain)
    domain_similarity = SequenceMatcher(None, left_domain, right_domain).ratio()

    # Domain tek başına güçlü kanıt sayılmamalı.
    score = (username_similarity * 0.8) + (domain_similarity * 0.15) + (domain_match * 0.05)
    return round(max(0.0, min(1.0, score)), 4)


def phone_similarity_score(left: str, right: str) -> float:
    left_digits = re.sub(r"\D", "", _safe_str(left))
    right_digits = re.sub(r"\D", "", _safe_str(right))
    if not left_digits or not right_digits:
        return 0.0
    if left_digits == right_digits:
        return 1.0
    if len(left_digits) >= 7 and len(right_digits) >= 7 and left_digits[-7:] == right_digits[-7:]:
        return 0.8
    if len(left_digits) >= 6 and len(right_digits) >= 6 and left_digits[-6:] == right_digits[-6:]:
        return 0.65
    return round(SequenceMatcher(None, left_digits, right_digits).ratio() * 0.7, 4)


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
    left_ordered_name = _safe_str(left.get("clean_name_ordered")) or left_name
    right_ordered_name = _safe_str(right.get("clean_name_ordered")) or right_name

    left_tc = _safe_str(left.get("clean_tc"))
    right_tc = _safe_str(right.get("clean_tc"))

    left_phone = _safe_str(left.get("clean_phone"))
    right_phone = _safe_str(right.get("clean_phone"))

    left_email = _safe_str(left.get("clean_email"))
    right_email = _safe_str(right.get("clean_email"))

    left_city = _safe_str(left.get("clean_city"))
    right_city = _safe_str(right.get("clean_city"))
    left_address = _safe_str(left.get("clean_address"))
    right_address = _safe_str(right.get("clean_address"))

    left_muhatap = _safe_str(left.get("clean_muhatap_no"))
    right_muhatap = _safe_str(right.get("clean_muhatap_no"))

    left_phonetic = _safe_str(left.get("name_phonetic_key"))
    right_phonetic = _safe_str(right.get("name_phonetic_key"))

    left_metaphone = _safe_str(left.get("name_metaphone_key"))
    right_metaphone = _safe_str(right.get("name_metaphone_key"))

    left_first, left_surname = _split_name_parts(left_ordered_name)
    right_first, right_surname = _split_name_parts(right_ordered_name)

    first_name_similarity = _max_similarity(left_first, right_first)
    surname_similarity = _max_similarity(left_surname, right_surname)

    first_name_jw = jaro_winkler_similarity(left_first, right_first)
    surname_jw = jaro_winkler_similarity(left_surname, right_surname)

    name_token_similarity_score = token_name_similarity(
        left_ordered_name,
        right_ordered_name,
    )
    name_jaro_winkler = hybrid_name_similarity(left_ordered_name, right_ordered_name)
    name_levenshtein_similarity = levenshtein_similarity(left_name, right_name)

    first_name_exact_match = int(bool(left_first and right_first and left_first == right_first))
    surname_exact_match = int(bool(left_surname and right_surname and left_surname == right_surname))

    tc_exact_match = int(bool(left_tc and right_tc and left_tc == right_tc))
    phone_exact_match = int(bool(left_phone and right_phone and left_phone == right_phone))
    email_exact_match = int(bool(left_email and right_email and left_email == right_email))
    phone_similarity = phone_similarity_score(left_phone, right_phone)
    email_similarity = email_similarity_score(left_email, right_email)
    email_domain_match = int(
        bool(
            "@" in left_email
            and "@" in right_email
            and left_email.lower().rsplit("@", 1)[1] == right_email.lower().rsplit("@", 1)[1]
        )
    )
    email_username_similarity = round(
        _similarity(
            normalize_email_for_similarity(left_email).split("@", 1)[0]
            if "@" in normalize_email_for_similarity(left_email)
            else normalize_email_for_similarity(left_email),
            normalize_email_for_similarity(right_email).split("@", 1)[0]
            if "@" in normalize_email_for_similarity(right_email)
            else normalize_email_for_similarity(right_email),
        ),
        4,
    )
    city_exact_match = int(bool(left_city and right_city and left_city == right_city))
    address_similarity = _max_similarity(left_address, right_address)
    muhatap_no_exact_match = int(bool(left_muhatap and right_muhatap and left_muhatap == right_muhatap))
    muhatap_no_conflict = int(bool(left_muhatap and right_muhatap and left_muhatap != right_muhatap))
    phonetic_exact_match = int(bool(left_phonetic and right_phonetic and left_phonetic == right_phonetic))
    metaphone_exact_match = int(bool(left_metaphone and right_metaphone and left_metaphone == right_metaphone))
    phonetic_close_match = int(bool(phonetic_exact_match or metaphone_exact_match))

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
    same_surname_name_conflict_flag = int(
        same_surname_name_conflict(left_ordered_name, right_ordered_name)
    )

    return {
        "tc_exact_match": tc_exact_match,
        "tc_conflict": tc_conflict,
        "tc_present_both": int(bool(left_tc and right_tc)),
        "phone_exact_match": phone_exact_match,
        "phone_match": phone_exact_match,
        "phone_last7_match": _last_n_match(left_phone, right_phone, 7),
        "phone_similarity": phone_similarity,
        "phone_present_both": int(bool(left_phone and right_phone)),
        "email_exact_match": email_exact_match,
        "email_domain_match": email_domain_match,
        "email_username_similarity": email_username_similarity,
        "city_exact_match": city_exact_match,
        "city_match": city_exact_match,
        "address_similarity": address_similarity,
        "muhatap_no_exact_match": muhatap_no_exact_match,
        "muhatap_no_conflict": muhatap_no_conflict,
        "muhatap_present_both": int(bool(left_muhatap and right_muhatap)),
        "phonetic_exact_match": phonetic_exact_match,
        "metaphone_exact_match": metaphone_exact_match,
        "phonetic_close_match": phonetic_close_match,
        "name_similarity": name_jaro_winkler,
        "name_jaro_winkler": name_jaro_winkler,
        "name_token_similarity": name_token_similarity_score,
        "name_levenshtein_similarity": name_levenshtein_similarity,
        "name_present_both": int(bool(left_name and right_name)),
        "email_similarity": email_similarity,
        "email_present_both": int(bool(left_email and right_email)),
        "first_name_similarity": first_name_similarity,
        "surname_similarity": surname_similarity,
        "first_name_jaro_winkler": first_name_jw,
        "surname_jaro_winkler": surname_jw,
        "first_name_exact_match": first_name_exact_match,
        "surname_exact_match": surname_exact_match,
        "shared_contact_flag": shared_contact_flag,
        "shared_contact_name_conflict": shared_contact_name_conflict,
        "household_risk_flag": household_risk_flag,
        "same_surname_name_conflict": same_surname_name_conflict_flag,
        "common_non_empty_fields": sum(
            [
                int(bool(left_tc and right_tc)),
                int(bool(left_phone and right_phone)),
                int(bool(left_email and right_email)),
                int(bool(left_name and right_name)),
                int(bool(left_city and right_city)),
                int(bool(left_address and right_address)),
                int(bool(left_muhatap and right_muhatap)),
            ]
        ),
    }


def should_suppress_tc_conflict_pair(features: dict[str, Any]) -> bool:
    """TC çakışıyorsa ve telefon/e-posta tam eşleşmiyorsa aday üretilmez."""
    if int(features.get("tc_conflict", 0) or 0) != 1:
        return False
    if int(features.get("phone_exact_match", 0) or 0) == 1:
        return False
    if int(features.get("email_exact_match", 0) or 0) == 1:
        return False
    return True
