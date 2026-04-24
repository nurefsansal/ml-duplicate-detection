import type {
  AdminPendingMatch,
  DetectDuplicatePair,
  FieldComparison,
} from "../services/api";
import type { DuplicateGroup } from "../mocks/records";

export type FieldComparisonKey =
  | "fullName"
  | "firstName"
  | "surname"
  | "tc"
  | "phone"
  | "email"
  | "city"
  | "address";

export type PairWorkflowState = "bekleyen" | "onaylandi" | "reddedildi";

export type UiPairRecord = {
  adSoyad: string;
  tcKimlikNo: string;
  telefon: string;
  email: string;
  sehir: string;
  muhatapNo: string;
  adres?: string;
};

export type UiDuplicatePair = {
  id: string;
  pairId: string;
  backendMatchId?: number;
  matchType?: string;
  backendDecision?: string;
  records: [UiPairRecord, UiPairRecord];
  score: number;
  workflowState: PairWorkflowState;
  finalDecision: string;
  finalDecisionLabel: string;
  matchDetails: Record<string, number>;
  fieldComparisons: Record<string, FieldComparison>;
  riskFlags: string[];
  ruleReasons: string[];
  decisionSource: string;
  splinkMatchProbability: number;
  splinkMatchWeight?: number | null;
  decisionReason?: string;
  createdAt?: string | null;
  reviewedAt?: string | null;
  reviewNote?: string;
  reviewedBy?: string | null;
};

export const FIELD_ORDER: FieldComparisonKey[] = [
  "fullName",
  "firstName",
  "surname",
  "tc",
  "phone",
  "email",
  "city",
  "address",
];

export const FIELD_LABELS: Record<FieldComparisonKey, string> = {
  fullName: "Ad Soyad",
  firstName: "Ad",
  surname: "Soyad",
  tc: "TC Kimlik No",
  phone: "Telefon",
  email: "E-posta",
  city: "Sehir",
  address: "Adres",
};

function toPercent(value: unknown, fallback = 0): number {
  const num = Number(value);
  if (Number.isNaN(num)) {
    return fallback;
  }
  if (num >= 0 && num <= 1) {
    return Math.max(0, Math.min(100, Math.round(num * 100)));
  }
  return Math.max(0, Math.min(100, Math.round(num)));
}

function toPercentValue(value: unknown, fallback = 0): number {
  const num = Number(value);
  if (Number.isNaN(num)) {
    return fallback;
  }
  if (num >= 0 && num <= 1) {
    return Math.max(0, Math.min(100, Math.round(num * 10000) / 100));
  }
  return Math.max(0, Math.min(100, Math.round(num * 100) / 100));
}

function toText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function pickRecordValue(record: Record<string, unknown>, aliases: string[]): string {
  const normalizedEntries = Object.keys(record).map((key) => [
    normalizeKey(key),
    key,
  ] as const);
  const keyMap = new Map<string, string>(normalizedEntries);

  for (const alias of aliases) {
    const actualKey = keyMap.get(normalizeKey(alias));
    if (!actualKey) {
      continue;
    }
    const value = toText(record[actualKey]).trim();
    if (value) {
      return value;
    }
  }

  return "";
}

function normalizeKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function fieldValue(
  comparison: FieldComparison | undefined,
  side: "left" | "right",
  preferNormalized = false,
): string {
  if (!comparison) {
    return "";
  }

  const rawValue =
    side === "left" ? comparison.rawLeftValue : comparison.rawRightValue;
  const normalizedValue =
    side === "left"
      ? comparison.normalizedLeftValue
      : comparison.normalizedRightValue;

  return preferNormalized
    ? normalizedValue || rawValue || ""
    : rawValue || normalizedValue || "";
}

function buildRecordFromDetectPair(
  pair: DetectDuplicatePair,
  side: "left" | "right",
): UiPairRecord {
  const record = side === "left" ? pair.record1 : pair.record2;
  const comparisons = pair.fieldComparisons || {};

  return {
    adSoyad:
      fieldValue(comparisons.fullName, side) ||
      pickRecordValue(record, ["Ad Soyad", "adSoyad", "full_name", "clean_name_ordered", "clean_name"]),
    tcKimlikNo:
      fieldValue(comparisons.tc, side) ||
      pickRecordValue(record, ["TC", "tcKimlikNo", "clean_tc"]),
    telefon:
      fieldValue(comparisons.phone, side) ||
      pickRecordValue(record, ["Telefon", "telefon", "clean_phone"]),
    email:
      fieldValue(comparisons.email, side) ||
      pickRecordValue(record, ["E-mail", "email", "clean_email", "email_normalized_key"]),
    sehir:
      fieldValue(comparisons.city, side) ||
      pickRecordValue(record, ["Sehir", "city", "clean_city"]),
    adres:
      fieldValue(comparisons.address, side) ||
      pickRecordValue(record, ["Adres", "address"]),
    muhatapNo: String(side === "left" ? pair.left_index : pair.right_index),
  };
}

function buildRecordFromPendingMatch(
  match: AdminPendingMatch,
  side: "left" | "right",
): UiPairRecord {
  const comparisons = match.fieldComparisons || {};

  return {
    adSoyad:
      fieldValue(comparisons.fullName, side) ||
      (side === "left" ? match.donor1_name : match.donor2_name) ||
      "",
    tcKimlikNo:
      fieldValue(comparisons.tc, side) ||
      (side === "left" ? match.donor1_tc : match.donor2_tc) ||
      "",
    telefon:
      fieldValue(comparisons.phone, side) ||
      (side === "left" ? match.donor1_phone : match.donor2_phone) ||
      "",
    email:
      fieldValue(comparisons.email, side) ||
      (side === "left" ? match.donor1_email : match.donor2_email) ||
      "",
    sehir:
      fieldValue(comparisons.city, side) ||
      (side === "left" ? match.donor1_city : match.donor2_city) ||
      "",
    adres: fieldValue(comparisons.address, side) || "",
    muhatapNo: String(side === "left" ? match.donor1_id : match.donor2_id),
  };
}

function buildMatchDetails(
  fieldComparisons: Record<string, FieldComparison>,
): Record<string, number> {
  return {
    adSoyad: toPercent(fieldComparisons.fullName?.score0To100, 0),
    tcKimlikNo: toPercent(fieldComparisons.tc?.score0To100, 0),
    telefon: toPercent(fieldComparisons.phone?.score0To100, 0),
    email: toPercent(fieldComparisons.email?.score0To100, 0),
    sehir: toPercent(fieldComparisons.city?.score0To100, 0),
  };
}

export function finalDecisionLabel(value: string): string {
  if (value === "same_person") {
    return "Ayni Kisi";
  }
  if (value === "different_person") {
    return "Farkli Kisi";
  }
  if (value === "review") {
    return "Manuel Inceleme";
  }
  return "Bilinmiyor";
}

export function finalDecisionTone(value: string): string {
  if (value === "same_person") {
    return "bg-green-50 text-green-700";
  }
  if (value === "different_person") {
    return "bg-red-50 text-red-600";
  }
  return "bg-yellow-50 text-yellow-700";
}

export function mapDetectPairToView(
  pair: DetectDuplicatePair,
  index: number,
): UiDuplicatePair {
  const fieldComparisons = pair.fieldComparisons || {};
  const score = toPercentValue(
    pair.splinkMatchProbability ?? pair.ml_probability ?? 0,
    0,
  );

  return {
    id: `MG-${String(index + 1).padStart(3, "0")}`,
    pairId: pair.pairId,
    records: [
      buildRecordFromDetectPair(pair, "left"),
      buildRecordFromDetectPair(pair, "right"),
    ],
    score,
    workflowState: "bekleyen",
    finalDecision: pair.finalDecision || pair.decision,
    finalDecisionLabel: finalDecisionLabel(pair.finalDecision || pair.decision),
    matchDetails: buildMatchDetails(fieldComparisons),
    fieldComparisons,
    riskFlags: pair.riskFlags || [],
    ruleReasons: pair.ruleReasons || pair.reasons || [],
    decisionSource: pair.decisionSource,
    splinkMatchProbability: Number(
      pair.splinkMatchProbability ?? pair.ml_probability ?? 0,
    ),
    splinkMatchWeight: pair.splinkMatchWeight ?? null,
  };
}

export function mapPendingMatchToView(
  match: AdminPendingMatch,
): UiDuplicatePair {
  const fieldComparisons = match.fieldComparisons || {};
  const finalDecision =
    match.finalDecision || match.decision || match.decision_reason || "review";
  const rawScore =
    match.score ??
    match.confidence ??
    match.splinkMatchProbability ??
    match.ml_score ??
    0;

  return {
    id: String(match.id),
    pairId: `match-${match.id}`,
    backendMatchId: match.id,
    matchType: match.match_type || match.decisionSource || "unknown",
    backendDecision: match.decision || "pending",
    records: [
      buildRecordFromPendingMatch(match, "left"),
      buildRecordFromPendingMatch(match, "right"),
    ],
    score: toPercentValue(rawScore, 0),
    workflowState: "bekleyen",
    finalDecision,
    finalDecisionLabel: finalDecisionLabel(finalDecision),
    matchDetails: buildMatchDetails(fieldComparisons),
    fieldComparisons,
    riskFlags: match.riskFlags || [],
    ruleReasons: match.ruleReasons || [],
    decisionSource: match.decisionSource || "fallback_legacy",
    splinkMatchProbability: Number(rawScore),
    splinkMatchWeight: match.splinkMatchWeight ?? null,
    decisionReason: match.decision_reason || undefined,
    createdAt: match.created_at,
  };
}

function syntheticComparison(
  leftValue: string,
  rightValue: string,
  score: number,
  comparisonMethod: string,
  notes: string,
): FieldComparison {
  const exactMatch = Boolean(leftValue && rightValue && leftValue === rightValue);
  return {
    rawLeftValue: leftValue,
    rawRightValue: rightValue,
    normalizedLeftValue: leftValue,
    normalizedRightValue: rightValue,
    comparisonMethod,
    comparisonResult: exactMatch
      ? "exact_match"
      : score >= 85
        ? "strong_match"
        : score >= 60
          ? "partial_match"
          : "mismatch",
    score0To100: score,
    exactMatch,
    notes,
  };
}

export function mapMockGroupToView(group: DuplicateGroup): UiDuplicatePair {
  const [leftRecord, rightRecord] = group.records;
  const details = group.matchDetails || {};
  const fieldComparisons: Record<string, FieldComparison> = {
    fullName: syntheticComparison(
      leftRecord.adSoyad,
      rightRecord.adSoyad,
      toPercent(details.adSoyad, 0),
      "mock_similarity",
      "Mock veri uzerinden olusturulan alan karsilastirmasi.",
    ),
    firstName: syntheticComparison(
      leftRecord.adSoyad.split(" ")[0] || "",
      rightRecord.adSoyad.split(" ")[0] || "",
      toPercent(details.adSoyad, 0),
      "mock_similarity",
      "Mock veri uzerinden olusturulan ad karsilastirmasi.",
    ),
    surname: syntheticComparison(
      leftRecord.adSoyad.split(" ").slice(-1)[0] || "",
      rightRecord.adSoyad.split(" ").slice(-1)[0] || "",
      toPercent(details.adSoyad, 0),
      "mock_similarity",
      "Mock veri uzerinden olusturulan soyad karsilastirmasi.",
    ),
    tc: syntheticComparison(
      leftRecord.tcKimlikNo,
      rightRecord.tcKimlikNo,
      toPercent(details.tcKimlikNo, 0),
      "mock_exact_match",
      "Mock veri uzerinden olusturulan TC karsilastirmasi.",
    ),
    phone: syntheticComparison(
      leftRecord.telefon,
      rightRecord.telefon,
      toPercent(details.telefon, 0),
      "mock_exact_match",
      "Mock veri uzerinden olusturulan telefon karsilastirmasi.",
    ),
    email: syntheticComparison(
      leftRecord.email,
      rightRecord.email,
      toPercent(details.email, 0),
      "mock_exact_match",
      "Mock veri uzerinden olusturulan e-posta karsilastirmasi.",
    ),
    city: syntheticComparison(
      leftRecord.sehir,
      rightRecord.sehir,
      toPercent(details.sehir, 0),
      "mock_exact_match",
      "Mock veri uzerinden olusturulan sehir karsilastirmasi.",
    ),
    address: syntheticComparison(
      leftRecord.adres || "",
      rightRecord.adres || "",
      0,
      "mock_supporting",
      "Mock veri uzerinden olusturulan destekleyici adres alani.",
    ),
  };

  return {
    id: group.id,
    pairId: group.id,
    records: [
      {
        adSoyad: leftRecord.adSoyad,
        tcKimlikNo: leftRecord.tcKimlikNo,
        telefon: leftRecord.telefon,
        email: leftRecord.email,
        sehir: leftRecord.sehir,
        muhatapNo: leftRecord.muhatapNo,
        adres: leftRecord.adres,
      },
      {
        adSoyad: rightRecord.adSoyad,
        tcKimlikNo: rightRecord.tcKimlikNo,
        telefon: rightRecord.telefon,
        email: rightRecord.email,
        sehir: rightRecord.sehir,
        muhatapNo: rightRecord.muhatapNo,
        adres: rightRecord.adres,
      },
    ],
    score: toPercent(group.score, 0),
    workflowState: group.decision,
    finalDecision: "review",
    finalDecisionLabel: "Manuel Inceleme",
    matchDetails: buildMatchDetails(fieldComparisons),
    fieldComparisons,
    riskFlags: [],
    ruleReasons: [],
    decisionSource: "mock_data",
    splinkMatchProbability: group.score / 100,
    splinkMatchWeight: null,
  };
}
