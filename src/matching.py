from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import recordlinkage


@dataclass(frozen=True)
class MatchConfig:
    """
    Central place for thresholds and rule weights.

    Current project requirement:
    - name: Jaro-Winkler with threshold 0.85
    - tc/phone/email: exact match
    - at least 2/4 rules must be satisfied
    """

    name_threshold: float = 0.85
    min_rules_to_match: int = 2


class EntityMatcher:
    """
    Record linkage / entity resolution engine using `recordlinkage`.
    """

    def __init__(self, config: MatchConfig | None = None) -> None:
        self.config = config or MatchConfig()

    def _ensure_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensures required clean_* columns exist.
        If a column is missing, it is created empty so the pipeline doesn't crash.
        """
        out = df.copy()
        for col in ["clean_city", "clean_name", "clean_tc", "clean_phone", "clean_email"]:
            if col not in out.columns:
                out[col] = ""
        return out

    def find_duplicates(
        self, df: pd.DataFrame
    ) -> tuple[pd.MultiIndex, pd.DataFrame, pd.DataFrame]:
        """
        Returns (pairs_index, features_df, duplicates_features_df).

        - pairs_index: candidate record pairs (MultiIndex of (left_id, right_id))
        - features_df: all rule results for candidate pairs
        - duplicates_features_df: subset where >= min_rules_to_match
        """
        df = self._ensure_columns(df)

        # recordlinkage indexer raises ZeroDivisionError for completely empty inputs.
        if df.empty:
            empty_pairs = pd.MultiIndex.from_arrays([[], []], names=["left_index", "right_index"])
            empty_features = pd.DataFrame(
                columns=["name_jw", "tc_exact", "phone_exact", "email_exact"],
                index=empty_pairs,
            )
            return empty_pairs, empty_features, empty_features.copy()

        # 1) Candidate generation (blocking by city for performance).
        indexer = recordlinkage.Index()
        indexer.block("clean_city")
        candidate_links = indexer.index(df)

        # 2) Comparison rules.
        compare = recordlinkage.Compare()
        compare.string(
            "clean_name",
            "clean_name",
            method="jarowinkler",
            threshold=self.config.name_threshold,
            label="name_jw",
        )
        compare.exact("clean_tc", "clean_tc", label="tc_exact")
        compare.exact("clean_phone", "clean_phone", label="phone_exact")
        compare.exact("clean_email", "clean_email", label="email_exact")

        features = compare.compute(candidate_links, df)

        # Exact comparisons should not count as a match when both sides are empty.
        left_index = features.index.get_level_values(0)
        right_index = features.index.get_level_values(1)

        for source_col, feature_col in [
            ("clean_tc", "tc_exact"),
            ("clean_phone", "phone_exact"),
            ("clean_email", "email_exact"),
        ]:
            left_vals = df.loc[left_index, source_col].reset_index(drop=True)
            right_vals = df.loc[right_index, source_col].reset_index(drop=True)

            left_empty = left_vals.fillna("").astype(str).str.strip().eq("")
            right_empty = right_vals.fillna("").astype(str).str.strip().eq("")
            both_empty = left_empty & right_empty

            if both_empty.any():
                features.loc[both_empty.to_numpy(), feature_col] = 0.0

        # 3) Filter: at least N rules must match.
        rule_sum = features.sum(axis=1)
        duplicates = features[rule_sum >= self.config.min_rules_to_match].copy()

        return candidate_links, features, duplicates

    def duplicates_as_dataframe(self, df: pd.DataFrame, duplicates_features: pd.DataFrame) -> pd.DataFrame:
        """
        Converts a duplicates MultiIndex/features frame to a human-friendly table:
        left_* columns + right_* columns + matched rule flags.
        """
        if duplicates_features.empty:
            return pd.DataFrame()

        # duplicates_features index is (left_index, right_index)
        left = df.loc[duplicates_features.index.get_level_values(0)].copy()
        right = df.loc[duplicates_features.index.get_level_values(1)].copy()

        left = left.reset_index().rename(columns={"index": "left_index"})
        right = right.reset_index().rename(columns={"index": "right_index"})

        # Keep a compact set of columns to display in the UI.
        display_cols = [
            "left_index",
            "right_index",
            "Ad Soyad",
            "Şehir",
            "Telefon",
            "TC",
            "E-mail",
            "clean_name",
            "clean_city",
            "clean_phone",
            "clean_tc",
            "clean_email",
        ]

        def _safe_cols(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
            cols = [c for c in display_cols if c in frame.columns]
            out = frame[cols].copy()
            rename_map = {c: f"{prefix}{c}" for c in out.columns if c not in ["left_index", "right_index"]}
            return out.rename(columns=rename_map)

        left_view = _safe_cols(left, "L_")
        right_view = _safe_cols(right, "R_")

        # Combine side-by-side and append match flags.
        combined = pd.concat([left_view, right_view], axis=1)
        combined = pd.concat([combined.reset_index(drop=True), duplicates_features.reset_index(drop=True)], axis=1)
        combined["rules_matched"] = duplicates_features.sum(axis=1).astype(int).values

        # Sort best matches first.
        combined = combined.sort_values(by=["rules_matched"], ascending=False).reset_index(drop=True)
        return combined

