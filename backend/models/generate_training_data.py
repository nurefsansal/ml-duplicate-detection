import itertools
from pathlib import Path

import pandas as pd

from src.preprocess import DataCleaner
from backend.services.normalization_service import (
    canonical_name,
    phonetic_name_key,
    metaphone_name_key,
    normalize_email_key,
)
from backend.services.feature_service import build_pair_features

INPUT_FILE = Path("dirtydata.xlsx")
OUTPUT_FILE = Path("backend/models/training_candidates.csv")


def load_source_data(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)

    keep_cols = ["Muhatap No", "Ad Soyad", "E-mail", "Telefon", "TC", "Şehir"]
    df = df[[c for c in keep_cols if c in df.columns]].copy()

    for col in keep_cols:
        if col not in df.columns:
            df[col] = ""

    df["Muhatap No"] = df["Muhatap No"].fillna("").astype(str).str.strip()
    df["Ad Soyad"] = df["Ad Soyad"].fillna("").astype(str).str.strip()
    df["E-mail"] = df["E-mail"].fillna("").astype(str).str.strip()
    df["Telefon"] = df["Telefon"].fillna("").astype(str).str.strip()
    df["TC"] = df["TC"].fillna("").astype(str).str.strip()
    df["Şehir"] = df["Şehir"].fillna("").astype(str).str.strip()

    return df


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    cleaner = DataCleaner()
    clean = cleaner.process(df)

    for col in [
        "clean_name",
        "clean_email",
        "clean_phone",
        "clean_tc",
        "clean_city",
        "clean_first_name",
        "clean_surname",
    ]:
        if col not in clean.columns:
            clean[col] = ""

    clean["clean_name"] = clean["clean_name"].fillna("").astype(str).apply(canonical_name)
    clean["name_phonetic_key"] = clean["clean_name"].fillna("").astype(str).apply(phonetic_name_key)
    clean["name_metaphone_key"] = clean["clean_name"].fillna("").astype(str).apply(metaphone_name_key)
    clean["email_normalized_key"] = clean["clean_email"].fillna("").astype(str).apply(normalize_email_key)

    clean["clean_first_name"] = clean["clean_first_name"].fillna("").astype(str).str.strip()
    clean["clean_surname"] = clean["clean_surname"].fillna("").astype(str).str.strip()

    return clean


def is_non_empty(value) -> bool:
    if value is None:
        return False
    value = str(value).strip()
    return value != "" and value.lower() != "nan"


def normalize_pair(left_idx: int, right_idx: int) -> tuple[int, int]:
    return (min(left_idx, right_idx), max(left_idx, right_idx))


def is_good_candidate(features: dict) -> bool:
    """
    Güçlü duplicate candidate'ları seçer.
    Amaç:
    - çok alakasız pair'leri elemek
    - sadece isim benziyor diye herkesi candidate yapmamak
    """

    tc_exact_match = int(features.get("tc_exact_match", 0))
    tc_conflict = int(features.get("tc_conflict", 0))
    phone_exact_match = int(features.get("phone_exact_match", 0))
    phone_last7_match = int(features.get("phone_last7_match", 0))
    email_exact_match = int(features.get("email_exact_match", 0))
    city_exact_match = int(features.get("city_exact_match", 0))
    phonetic_exact_match = int(features.get("phonetic_exact_match", 0))
    first_name_exact_match = int(features.get("first_name_exact_match", 0))
    surname_exact_match = int(features.get("surname_exact_match", 0))
    shared_contact_flag = int(features.get("shared_contact_flag", 0))
    shared_contact_name_conflict = int(features.get("shared_contact_name_conflict", 0))
    household_risk_flag = int(features.get("household_risk_flag", 0))
    common_non_empty_fields = int(features.get("common_non_empty_fields", 0))

    name_similarity = float(features.get("name_similarity", 0.0))
    email_similarity = float(features.get("email_similarity", 0.0))
    first_name_similarity = float(features.get("first_name_similarity", 0.0))
    surname_similarity = float(features.get("surname_similarity", 0.0))

    # En güçlü sinyaller
    if tc_exact_match == 1:
        return True

    if email_exact_match == 1:
        return True

    if phone_exact_match == 1:
        return True

    # Aynı telefon son 7 + isim güçlü yakınsa
    if phone_last7_match == 1 and name_similarity >= 0.82:
        return True

    # İsim çok benzerse tek başına yetmesin
    if (
        name_similarity >= 0.93
        and (
            phone_last7_match == 1
            or email_similarity >= 0.95
            or phonetic_exact_match == 1
            or common_non_empty_fields >= 2
        )
    ):
        return True

    # Ad ve soyad ayrı ayrı çok yakınsa
    if (
        first_name_similarity >= 0.90
        and surname_similarity >= 0.93
        and (
            shared_contact_flag == 1
            or phonetic_exact_match == 1
            or common_non_empty_fields >= 2
        )
    ):
        return True

    # Aynı ad + aynı soyad + birden fazla ortak dolu alan
    if (
        first_name_exact_match == 1
        and surname_exact_match == 1
        and common_non_empty_fields >= 2
    ):
        return True

    # Aile / household riski varsa ve güçlü eşleşme yoksa duplicate candidate alma
    if (
        household_risk_flag == 1
        and shared_contact_name_conflict == 1
        and tc_exact_match == 0
        and email_exact_match == 0
        and phone_exact_match == 0
    ):
        return False

    # TC çelişiyorsa güçlü başka kanıt yoksa alma
    if tc_conflict == 1 and email_exact_match == 0 and phone_exact_match == 0:
        return False

    # Şehir tek başına duplicate adayı yapmaz
    if city_exact_match == 1 and name_similarity < 0.85 and shared_contact_flag == 0:
        return False

    return False


def add_pairs_from_group(
    df: pd.DataFrame,
    idxs: list[int],
    pair_set: set[tuple[int, int]],
    max_pairs_per_block: int,
    strict_filter: bool = True,
):
    if len(idxs) < 2:
        return

    idxs = sorted(idxs)[:max_pairs_per_block]

    for left_idx, right_idx in itertools.combinations(idxs, 2):
        left = df.loc[left_idx].to_dict()
        right = df.loc[right_idx].to_dict()
        features = build_pair_features(left, right)

        pair = normalize_pair(left_idx, right_idx)

        if strict_filter:
            if is_good_candidate(features):
                pair_set.add(pair)
        else:
            pair_set.add(pair)


def generate_strong_pairs(df: pd.DataFrame, max_pairs_per_block: int = 200) -> set[tuple[int, int]]:
    pairs = set()

    strong_block_columns = [
        "clean_tc",
        "clean_phone",
        "email_normalized_key",
    ]

    for col in strong_block_columns:
        if col not in df.columns:
            continue

        valid = df[df[col].apply(is_non_empty)]
        groups = valid.groupby(col).groups

        for _, idxs in groups.items():
            add_pairs_from_group(
                df=df,
                idxs=list(idxs),
                pair_set=pairs,
                max_pairs_per_block=max_pairs_per_block,
                strict_filter=False,
            )

    return pairs


def generate_name_based_pairs(df: pd.DataFrame, max_pairs_per_block: int = 40) -> set[tuple[int, int]]:
    pairs = set()

    if "name_phonetic_key" not in df.columns:
        return pairs

    valid = df[df["name_phonetic_key"].apply(is_non_empty)]
    groups = valid.groupby("name_phonetic_key").groups

    for _, idxs in groups.items():
        add_pairs_from_group(
            df=df,
            idxs=list(idxs),
            pair_set=pairs,
            max_pairs_per_block=max_pairs_per_block,
            strict_filter=True,
        )

    return pairs


def generate_same_surname_hard_negatives(df: pd.DataFrame, limit: int = 300) -> set[tuple[int, int]]:
    """
    Aynı soyadlı ama duplicate olmayabilecek zor örnekler.
    """
    pairs = set()

    if "clean_surname" not in df.columns:
        return pairs

    valid = df[df["clean_surname"].apply(is_non_empty)]
    groups = valid.groupby("clean_surname").groups

    for _, idxs in groups.items():
        idxs = sorted(list(idxs))
        if len(idxs) < 2:
            continue

        idxs = idxs[:60]

        for left_idx, right_idx in itertools.combinations(idxs, 2):
            left = df.loc[left_idx].to_dict()
            right = df.loc[right_idx].to_dict()
            features = build_pair_features(left, right)

            tc_exact_match = int(features.get("tc_exact_match", 0))
            phone_exact_match = int(features.get("phone_exact_match", 0))
            email_exact_match = int(features.get("email_exact_match", 0))
            first_name_exact_match = int(features.get("first_name_exact_match", 0))
            shared_contact_flag = int(features.get("shared_contact_flag", 0))
            household_risk_flag = int(features.get("household_risk_flag", 0))
            surname_exact_match = int(features.get("surname_exact_match", 0))
            name_similarity = float(features.get("name_similarity", 0.0))

            if (
                surname_exact_match == 1
                and tc_exact_match == 0
                and phone_exact_match == 0
                and email_exact_match == 0
                and first_name_exact_match == 0
                and (
                    shared_contact_flag == 1
                    or household_risk_flag == 1
                    or (0.45 <= name_similarity <= 0.85)
                )
            ):
                pairs.add(normalize_pair(left_idx, right_idx))

                if len(pairs) >= limit:
                    return pairs

    return pairs


def generate_aggressive_hard_negatives(df: pd.DataFrame, limit: int = 500) -> set[tuple[int, int]]:
    """
    Modeli zorlayan agresif hard-negative örnekler:
    - aynı soyad + farklı ad
    - ortak iletişim + düşük isim uyumu
    - household riski
    - orta seviye isim benzerliği
    """
    pairs = set()

    if "clean_surname" not in df.columns:
        return pairs

    valid = df[df["clean_surname"].apply(is_non_empty)]
    groups = valid.groupby("clean_surname").groups

    for _, idxs in groups.items():
        idxs = sorted(list(idxs))
        if len(idxs) < 2:
            continue

        idxs = idxs[:80]

        for left_idx, right_idx in itertools.combinations(idxs, 2):
            left = df.loc[left_idx].to_dict()
            right = df.loc[right_idx].to_dict()
            features = build_pair_features(left, right)

            if (
                int(features.get("tc_exact_match", 0)) == 1
                or int(features.get("phone_exact_match", 0)) == 1
                or int(features.get("email_exact_match", 0)) == 1
            ):
                continue

            name_sim = float(features.get("name_similarity", 0.0))
            first_name_sim = float(features.get("first_name_similarity", 0.0))
            surname_match = int(features.get("surname_exact_match", 0))
            shared_contact = int(features.get("shared_contact_flag", 0))
            shared_contact_name_conflict = int(features.get("shared_contact_name_conflict", 0))
            household = int(features.get("household_risk_flag", 0))
            city_exact = int(features.get("city_exact_match", 0))
            phonetic_exact = int(features.get("phonetic_exact_match", 0))

            pair = normalize_pair(left_idx, right_idx)

            if surname_match == 1 and first_name_sim < 0.70 and name_sim < 0.85:
                pairs.add(pair)

            if shared_contact == 1 and name_sim < 0.80:
                pairs.add(pair)

            if household == 1 and shared_contact_name_conflict == 1:
                pairs.add(pair)

            if 0.60 < name_sim < 0.88:
                pairs.add(pair)

            if city_exact == 1 and phonetic_exact == 1 and name_sim < 0.88:
                pairs.add(pair)

            if len(pairs) >= limit:
                return pairs

    return pairs


def generate_cross_name_confusion_pairs(df: pd.DataFrame, limit: int = 300) -> set[tuple[int, int]]:
    """
    Soyad aynı olmasa bile fonetik / isim benzerliği yüzünden karışabilecek örnekler.
    """
    pairs = set()

    if "name_phonetic_key" not in df.columns:
        return pairs

    valid = df[df["name_phonetic_key"].apply(is_non_empty)]
    groups = valid.groupby("name_phonetic_key").groups

    for _, idxs in groups.items():
        idxs = sorted(list(idxs))
        if len(idxs) < 2:
            continue

        idxs = idxs[:50]

        for left_idx, right_idx in itertools.combinations(idxs, 2):
            left = df.loc[left_idx].to_dict()
            right = df.loc[right_idx].to_dict()
            features = build_pair_features(left, right)

            tc_exact = int(features.get("tc_exact_match", 0))
            phone_exact = int(features.get("phone_exact_match", 0))
            email_exact = int(features.get("email_exact_match", 0))
            name_sim = float(features.get("name_similarity", 0.0))
            surname_sim = float(features.get("surname_similarity", 0.0))
            first_name_sim = float(features.get("first_name_similarity", 0.0))
            phonetic_exact = int(features.get("phonetic_exact_match", 0))

            if tc_exact == 1 or phone_exact == 1 or email_exact == 1:
                continue

            if (
                phonetic_exact == 1
                and 0.65 <= name_sim <= 0.90
                and (
                    first_name_sim < 0.95
                    or surname_sim < 0.95
                )
            ):
                pairs.add(normalize_pair(left_idx, right_idx))

                if len(pairs) >= limit:
                    return pairs

    return pairs


def generate_family_confusion_pairs(df: pd.DataFrame, limit: int = 500) -> set[tuple[int, int]]:
    """
    Aynı aile / aynı hane karışıklığı için özel örnekler üretir.

    Hedef:
    - soyadı aynı
    - ortak telefon / email / şehir / household sinyali var
    - ama ilk isim farklı

    Bunlar training'de çoğunlukla label=0 olacaktır.
    """
    pairs = set()

    if "clean_surname" not in df.columns:
        return pairs

    valid = df[df["clean_surname"].apply(is_non_empty)]
    groups = valid.groupby("clean_surname").groups

    for _, idxs in groups.items():
        idxs = sorted(list(idxs))
        if len(idxs) < 2:
            continue

        idxs = idxs[:100]

        for left_idx, right_idx in itertools.combinations(idxs, 2):
            left = df.loc[left_idx].to_dict()
            right = df.loc[right_idx].to_dict()
            features = build_pair_features(left, right)

            tc_exact = int(features.get("tc_exact_match", 0))
            phone_exact = int(features.get("phone_exact_match", 0))
            phone_last7 = int(features.get("phone_last7_match", 0))
            email_exact = int(features.get("email_exact_match", 0))
            city_exact = int(features.get("city_exact_match", 0))
            surname_exact = int(features.get("surname_exact_match", 0))
            first_name_exact = int(features.get("first_name_exact_match", 0))
            shared_contact = int(features.get("shared_contact_flag", 0))
            shared_contact_name_conflict = int(features.get("shared_contact_name_conflict", 0))
            household_risk = int(features.get("household_risk_flag", 0))

            first_name_similarity = float(features.get("first_name_similarity", 0.0))
            name_similarity = float(features.get("name_similarity", 0.0))

            # aynı kişi olma ihtimali çok yüksekse bunu family confusion'a alma
            if tc_exact == 1:
                continue

            if first_name_exact == 1 and name_similarity >= 0.93:
                continue

            # istediğimiz örnek:
            # aynı soyad + ortak temas/household + ad farklı
            if (
                surname_exact == 1
                and first_name_similarity < 0.75
                and (
                    phone_exact == 1
                    or phone_last7 == 1
                    or email_exact == 1
                    or city_exact == 1
                    or shared_contact == 1
                    or household_risk == 1
                )
            ):
                pairs.add(normalize_pair(left_idx, right_idx))

            # özellikle isim çatışması olan ortak iletişim örneği
            if (
                surname_exact == 1
                and shared_contact_name_conflict == 1
                and first_name_similarity < 0.85
            ):
                pairs.add(normalize_pair(left_idx, right_idx))

            if len(pairs) >= limit:
                return pairs

    return pairs


def generate_pairs(df: pd.DataFrame) -> list[tuple[int, int]]:
    pairs = set()

    strong_pairs = generate_strong_pairs(df, max_pairs_per_block=200)
    name_pairs = generate_name_based_pairs(df, max_pairs_per_block=40)
    same_surname_hard_negatives = generate_same_surname_hard_negatives(df, limit=300)
    aggressive_negatives = generate_aggressive_hard_negatives(df, limit=500)
    cross_name_confusions = generate_cross_name_confusion_pairs(df, limit=300)
    family_confusions = generate_family_confusion_pairs(df, limit=500)

    pairs.update(strong_pairs)
    pairs.update(name_pairs)
    pairs.update(same_surname_hard_negatives)
    pairs.update(aggressive_negatives)
    pairs.update(cross_name_confusions)
    pairs.update(family_confusions)

    return sorted(pairs)


def build_training_candidates(df: pd.DataFrame, pairs: list[tuple[int, int]]) -> pd.DataFrame:
    rows = []

    for left_idx, right_idx in pairs:
        left = df.loc[left_idx].to_dict()
        right = df.loc[right_idx].to_dict()

        features = build_pair_features(left, right)

        rows.append(
            {
                "left_index": left_idx,
                "right_index": right_idx,
                "left_muhatap_no": str(left.get("Muhatap No", "")),
                "right_muhatap_no": str(right.get("Muhatap No", "")),
                "left_name": str(left.get("Ad Soyad", "")),
                "right_name": str(right.get("Ad Soyad", "")),
                "left_phone": str(left.get("Telefon", "")),
                "right_phone": str(right.get("Telefon", "")),
                "left_email": str(left.get("E-mail", "")),
                "right_email": str(right.get("E-mail", "")),
                "left_tc": str(left.get("TC", "")),
                "right_tc": str(right.get("TC", "")),
                "left_city": str(left.get("Şehir", "")),
                "right_city": str(right.get("Şehir", "")),
                **features,
                "label": "",
            }
        )

    return pd.DataFrame(rows)


def main():
    df = load_source_data(INPUT_FILE)
    df = normalize_df(df)
    pairs = generate_pairs(df)
    candidates = build_training_candidates(df, pairs)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print(f"training candidate file created: {OUTPUT_FILE}")
    print(f"pair count: {len(candidates)}")


if __name__ == "__main__":
    main()