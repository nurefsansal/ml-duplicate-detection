import pandas as pd
from itertools import combinations


def _pairs_from_group(indexes: list[int]) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    if len(indexes) < 2:
        return pairs

    for left, right in combinations(sorted(indexes), 2):
        pairs.add((left, right))

    return pairs


def _collect_pairs_by_column(df: pd.DataFrame, column: str) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()

    if column not in df.columns:
        return pairs

    valid_df = df[df[column].notna() & (df[column].astype(str).str.strip() != "")]
    if valid_df.empty:
        return pairs

    grouped = valid_df.groupby(column).groups

    for _, index_values in grouped.items():
        indexes = list(index_values)
        pairs.update(_pairs_from_group(indexes))

    return pairs


def generate_candidate_pairs(df: pd.DataFrame) -> list[tuple[int, int]]:
    """
    Multi-pass blocking:
    - clean_tc
    - clean_phone
    - email_normalized_key
    - name_phonetic_key + clean_city
    - clean_city
    """

    all_pairs: set[tuple[int, int]] = set()

    # 1. Strong identifiers
    all_pairs.update(_collect_pairs_by_column(df, "clean_tc"))
    all_pairs.update(_collect_pairs_by_column(df, "clean_phone"))
    all_pairs.update(_collect_pairs_by_column(df, "email_normalized_key"))

    # 2. Phonetic name
    all_pairs.update(_collect_pairs_by_column(df, "name_phonetic_key"))

    # 3. Same city as weak fallback
    all_pairs.update(_collect_pairs_by_column(df, "clean_city"))

    return sorted(all_pairs)