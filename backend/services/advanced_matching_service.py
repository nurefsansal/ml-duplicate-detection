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
