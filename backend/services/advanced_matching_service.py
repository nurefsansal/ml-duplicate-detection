from __future__ import annotations

import re
from difflib import SequenceMatcher


def _safe_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_for_name(value: str) -> str:
    text = _safe_str(value).lower()
    if not text:
        return ""

    tr_map = str.maketrans(
        {
            "c": "c",
            "g": "g",
            "i": "i",
            "o": "o",
            "s": "s",
            "u": "u",
            "\u00e7": "c",
            "\u011f": "g",
            "\u0131": "i",
            "\u00f6": "o",
            "\u015f": "s",
            "\u00fc": "u",
        }
    )
    text = text.translate(tr_map)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _name_tokens(value: str) -> list[str]:
    normalized = _normalize_for_name(value)
    if not normalized:
        return []
    return [token for token in normalized.split(" ") if token]


def _sorted_name(value: str) -> str:
    tokens = _name_tokens(value)
    if not tokens:
        return ""
    return " ".join(sorted(tokens))


def _split_name_parts(value: str) -> tuple[str, str]:
    tokens = _name_tokens(value)
    if not tokens:
        return "", ""
    if len(tokens) == 1:
        return tokens[0], ""
    return tokens[0], tokens[-1]


def _levenshtein_distance(a: str, b: str) -> int:
    a = _safe_str(a)
    b = _safe_str(b)
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ch_a in enumerate(a, start=1):
        curr = [i]
        for j, ch_b in enumerate(b, start=1):
            ins = curr[j - 1] + 1
            rem = prev[j] + 1
            rep = prev[j - 1] + (ch_a != ch_b)
            curr.append(min(ins, rem, rep))
        prev = curr
    return prev[-1]


def _jaro_similarity(a: str, b: str) -> float:
    a = _safe_str(a)
    b = _safe_str(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    len_a = len(a)
    len_b = len(b)
    match_dist = max(len_a, len_b) // 2 - 1

    a_matches = [False] * len_a
    b_matches = [False] * len_b

    matches = 0
    transpositions = 0

    for i in range(len_a):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len_b)

        for j in range(start, end):
            if b_matches[j] or a[i] != b[j]:
                continue
            a_matches[i] = True
            b_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len_a):
        if not a_matches[i]:
            continue
        while not b_matches[k]:
            k += 1
        if a[i] != b[k]:
            transpositions += 1
        k += 1

    transpositions /= 2

    return (
        (matches / len_a)
        + (matches / len_b)
        + ((matches - transpositions) / matches)
    ) / 3.0


def jaro_winkler_similarity(a: str, b: str) -> float:
    a = _normalize_for_name(a)
    b = _normalize_for_name(b)
    if not a or not b:
        return 0.0

    jaro = _jaro_similarity(a, b)
    prefix = 0
    for left_ch, right_ch in zip(a, b):
        if left_ch != right_ch:
            break
        prefix += 1
        if prefix == 4:
            break

    return round(jaro + (prefix * 0.1 * (1.0 - jaro)), 4)


def levenshtein_similarity(a: str, b: str) -> float:
    a = _normalize_for_name(a)
    b = _normalize_for_name(b)
    if not a or not b:
        return 0.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0.0
    distance = _levenshtein_distance(a, b)
    return round(1.0 - (distance / max_len), 4)


def sequence_similarity(a: str, b: str) -> float:
    a = _normalize_for_name(a)
    b = _normalize_for_name(b)
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio(), 4)


def _token_similarity(left_token: str, right_token: str) -> float:
    left_value = _normalize_for_name(left_token)
    right_value = _normalize_for_name(right_token)
    if not left_value or not right_value:
        return 0.0
    if left_value == right_value:
        return 1.0

    if len(left_value) == 1 or len(right_value) == 1:
        return 0.92 if left_value[0] == right_value[0] else 0.0

    score = max(
        jaro_winkler_similarity(left_value, right_value),
        levenshtein_similarity(left_value, right_value),
        sequence_similarity(left_value, right_value),
    )
    if left_value.startswith(right_value) or right_value.startswith(left_value):
        score = max(score, 0.9)
    return round(score, 4)


def token_name_similarity(a: str, b: str) -> float:
    left_tokens = _name_tokens(a)
    right_tokens = _name_tokens(b)
    if not left_tokens or not right_tokens:
        return 0.0

    available_right = list(enumerate(right_tokens))
    matched_scores: list[float] = []

    for left_token in left_tokens:
        best_position = -1
        best_score = 0.0
        for index, right_token in available_right:
            score = _token_similarity(left_token, right_token)
            if score > best_score:
                best_score = score
                best_position = index
        if best_position == -1 or best_score < 0.7:
            continue
        matched_scores.append(best_score)
        available_right = [
            (index, token)
            for index, token in available_right
            if index != best_position
        ]

    if not matched_scores:
        return 0.0

    denominator = max(len(left_tokens), len(right_tokens))
    return round(sum(matched_scores) / denominator, 4)


def same_surname_name_conflict(a: str, b: str) -> bool:
    left_tokens = _name_tokens(a)
    right_tokens = _name_tokens(b)
    if len(left_tokens) < 2 or len(right_tokens) < 2:
        return False

    left_surname = left_tokens[-1]
    right_surname = right_tokens[-1]
    if left_surname != right_surname:
        return False

    left_given_names = " ".join(left_tokens[:-1])
    right_given_names = " ".join(right_tokens[:-1])
    if not left_given_names or not right_given_names:
        return False
    if left_given_names == right_given_names:
        return False

    given_name_similarity = token_name_similarity(left_given_names, right_given_names)
    return bool(given_name_similarity < 0.85)


def hybrid_name_similarity(a: str, b: str) -> float:
    left_value = _normalize_for_name(a)
    right_value = _normalize_for_name(b)
    if not left_value or not right_value:
        return 0.0

    ordered_jaro = jaro_winkler_similarity(left_value, right_value)
    orderless_jaro = jaro_winkler_similarity(_sorted_name(left_value), _sorted_name(right_value))
    token_similarity = token_name_similarity(left_value, right_value)

    score = max(
        ordered_jaro,
        orderless_jaro,
        token_similarity,
        round((orderless_jaro * 0.5) + (token_similarity * 0.5), 4),
    )

    if same_surname_name_conflict(a, b):
        score = min(score, 0.74)

    return round(score, 4)


def soundex_tr(value: str) -> str:
    text = _normalize_for_name(value)
    if not text:
        return ""
    text = text.replace(" ", "")
    if not text:
        return ""

    first = text[0].upper()

    groups = {
        "b": "1", "f": "1", "p": "1", "v": "1",
        "c": "2", "g": "2", "j": "2", "k": "2", "q": "2", "s": "2", "x": "2", "z": "2",
        "d": "3", "t": "3",
        "l": "4",
        "m": "5", "n": "5",
        "r": "6",
    }

    encoded = [first]
    last_code = groups.get(text[0], "")

    for ch in text[1:]:
        code = groups.get(ch, "")
        if code and code != last_code:
            encoded.append(code)
        last_code = code

    return ("".join(encoded) + "000")[:4]


def metaphone_tr_like(value: str) -> str:
    text = _normalize_for_name(value)
    if not text:
        return ""

    text = text.replace("ph", "f").replace("w", "v").replace("x", "ks")
    text = text.replace("q", "k")
    text = re.sub(r"[aeiou]", "", text)
    text = re.sub(r"(.)\1+", r"\1", text)
    text = re.sub(r"\s+", "", text)
    return text[:12].upper()


def build_name_keys(value: str) -> dict:
    normalized = _normalize_for_name(value)
    return {
        "normalized_name": normalized,
        "soundex_key": soundex_tr(normalized),
        "metaphone_key": metaphone_tr_like(normalized),
    }
