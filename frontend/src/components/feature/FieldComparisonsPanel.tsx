import type { FieldComparison } from "../../services/api";
import {
  FIELD_LABELS,
  FIELD_ORDER,
  finalDecisionTone,
} from "../../utils/duplicatePairView";

type Props = {
  fieldComparisons: Record<string, FieldComparison>;
  overallScore: number;
  finalDecisionLabel?: string;
  finalDecision?: string;
  riskFlags?: string[];
  ruleReasons?: string[];
};

function scoreClass(score: number): string {
  if (score >= 90) {
    return "bg-gradient-to-r from-emerald-400 to-teal-500";
  }
  if (score >= 70) {
    return "bg-gradient-to-r from-amber-400 to-primary-400";
  }
  return "bg-gradient-to-r from-rose-400 to-orange-400";
}

function scoreTextClass(score: number): string {
  if (score >= 90) {
    return "text-emerald-700";
  }
  if (score >= 70) {
    return "text-amber-800";
  }
  return "text-danger-700";
}

function resultLabel(value: string): string {
  if (value === "exact_match") {
    return "Tam Eslesme";
  }
  if (value === "strong_match") {
    return "Guclu Eslesme";
  }
  if (value === "partial_match") {
    return "Kismi Eslesme";
  }
  if (value === "conflict") {
    return "Catisma";
  }
  if (value === "mismatch") {
    return "Uyusmuyor";
  }
  if (value === "missing") {
    return "Eksik Veri";
  }
  return "Destekleyici";
}

export default function FieldComparisonsPanel({
  fieldComparisons,
  overallScore,
  finalDecision,
  finalDecisionLabel,
  riskFlags = [],
  ruleReasons = [],
}: Props) {
  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-gray-50 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-xs font-semibold text-gray-600">Alan Bazli Skor Kirilimi</p>
          {finalDecisionLabel && finalDecision ? (
            <span
              className={`inline-flex items-center rounded-full px-3 py-1 text-[11px] font-semibold ${finalDecisionTone(finalDecision)}`}
            >
              {finalDecisionLabel}
            </span>
          ) : null}
        </div>

        <div className="space-y-3">
          {FIELD_ORDER.filter((fieldKey) => fieldComparisons[fieldKey]).map((fieldKey) => {
            const comparison = fieldComparisons[fieldKey];
            const score = Number(comparison.score0To100 || 0);

            return (
              <div key={fieldKey} className="rounded-lg border border-gray-200 bg-white p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold text-gray-700">
                      {FIELD_LABELS[fieldKey]}
                    </p>
                    <p className="text-[11px] text-gray-400">
                      {resultLabel(comparison.comparisonResult)}
                    </p>
                  </div>
                  <span className={`text-sm font-bold ${scoreTextClass(score)}`}>
                    %{score}
                  </span>
                </div>

                <div className="mb-3 h-1.5 rounded-full bg-gray-200">
                  <div
                    className={`h-1.5 rounded-full ${scoreClass(score)}`}
                    style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
                  />
                </div>

                <div className="grid grid-cols-1 gap-2 text-[11px] text-gray-600 sm:grid-cols-2">
                  <div>
                    <span className="block text-gray-400">Sol ham deger</span>
                    <span className="break-words">
                      {comparison.rawLeftValue || comparison.normalizedLeftValue || "-"}
                    </span>
                  </div>
                  <div>
                    <span className="block text-gray-400">Sag ham deger</span>
                    <span className="break-words">
                      {comparison.rawRightValue || comparison.normalizedRightValue || "-"}
                    </span>
                  </div>
                  <div>
                    <span className="block text-gray-400">Normalize sol deger</span>
                    <span className="break-words">
                      {comparison.normalizedLeftValue || comparison.rawLeftValue || "-"}
                    </span>
                  </div>
                  <div>
                    <span className="block text-gray-400">Normalize sag deger</span>
                    <span className="break-words">
                      {comparison.normalizedRightValue || comparison.rawRightValue || "-"}
                    </span>
                  </div>
                </div>

                <p className="mt-2 text-[11px] text-gray-500">{comparison.notes}</p>
              </div>
            );
          })}
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-gray-200 pt-3">
          <span className="text-xs font-semibold text-gray-700">Genel Skor</span>
          <span className="bg-gradient-to-r from-primary-700 to-indigo-700 bg-clip-text text-lg font-bold tabular-nums text-transparent">
            %{overallScore.toFixed(1)}
          </span>
        </div>
      </div>

      {(riskFlags.length > 0 || ruleReasons.length > 0) && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-gray-100 bg-white p-4">
            <p className="mb-2 text-xs font-semibold text-gray-700">Risk Bayraklari</p>
            {riskFlags.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {riskFlags.map((flag) => (
                  <span
                    key={flag}
                    className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-900"
                  >
                    {flag}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-400">Risk bayragi yok.</p>
            )}
          </div>

          <div className="rounded-xl border border-gray-100 bg-white p-4">
            <p className="mb-2 text-xs font-semibold text-gray-700">Kural Gerekceleri</p>
            {ruleReasons.length > 0 ? (
              <ul className="space-y-1 text-xs text-gray-600">
                {ruleReasons.map((reason) => (
                  <li key={reason} className="rounded-lg bg-gray-50 px-3 py-2">
                    {reason}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400">Aciklama bulunmuyor.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
