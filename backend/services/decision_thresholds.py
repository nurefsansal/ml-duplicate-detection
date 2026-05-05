"""Probability thresholds derived from Ayarlar (0–100) — no SQLAlchemy imports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_THRESHOLDS_RAW: dict[str, float] = {
    "otoOnayla": 97.0,
    "bayrakla": 75.0,
    "yoksay": 50.0,
}


@dataclass(frozen=True)
class DecisionThresholdsProb:
    auto_approve: float
    manual_review: float
    reject: float

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> "DecisionThresholdsProb":
        merged = {**DEFAULT_THRESHOLDS_RAW}
        if isinstance(raw, dict):
            for key, default in DEFAULT_THRESHOLDS_RAW.items():
                if key in raw and raw[key] is not None:
                    try:
                        merged[key] = float(raw[key])
                    except (TypeError, ValueError):
                        merged[key] = default

        def _to_prob(key: str) -> float:
            v = float(merged.get(key, DEFAULT_THRESHOLDS_RAW[key]) or 0.0)
            if v > 1.0:
                v = v / 100.0
            return max(0.0, min(1.0, v))

        auto = _to_prob("otoOnayla")
        manual = _to_prob("bayrakla")
        reject = _to_prob("yoksay")
        if reject > manual:
            reject, manual = manual, reject
        if manual > auto:
            manual = auto
        if reject > manual:
            reject = manual
        return cls(auto_approve=auto, manual_review=manual, reject=reject)

    def as_percent_dict(self) -> dict[str, float]:
        return {
            "otoOnayla": round(self.auto_approve * 100, 2),
            "bayrakla": round(self.manual_review * 100, 2),
            "yoksay": round(self.reject * 100, 2),
        }
