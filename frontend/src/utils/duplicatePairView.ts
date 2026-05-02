import type {
  AdminPendingMatch,
  DetectDuplicatePair,
  FieldComparison,
} from "../services/api";

export type FieldComparisonKey =
  | "fullName"
  | "firstName"
  | "surname"
  | "tc"
  | "phone"
  | "email"
  | "city"
  | "muhatapNo";

export type PairWorkflowState = "bekleyen" | "onaylandi" | "reddedildi";

export type UiPairRecord = {
  adSoyad: string;
  tcKimlikNo: string;
  telefon: string;
  email: string;
  sehir: string;
  muhatapNo: string;
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
  decisionType?: "auto" | "manual";
  reviewRequired?: boolean;
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
  "muhatapNo",
];

export const FIELD_LABELS: Record<FieldComparisonKey, string> = {
  fullName: "Ad Soyad",
  firstName: "Ad",
  surname: "Soyad",
  tc: "TC Kimlik No",
  phone: "Telefon",
  email: "E-posta",
  city: "Sehir",
  muhatapNo: "Muhatap Kodu",
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
    muhatapNo:
      fieldValue(comparisons.muhatapNo, side) ||
      pickRecordValue(record, ["Muhatap No", "muhatap_no", "muhatap kodu", "clean_muhatap_no", "customer_id"]),
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
    muhatapNo:
      fieldValue(comparisons.muhatapNo, side) ||
      "",
  };
}

function buildMatchDetails(
  features: Record<string, unknown>,
  records: [UiPairRecord, UiPairRecord],
  fieldComparisons: Record<string, FieldComparison>,
): Record<string, number> {
  const backendEmailSimilarity = Number(features.email_similarity);
  let emailScore = Number.NaN;

  if (!Number.isNaN(backendEmailSimilarity)) {
    emailScore =
      backendEmailSimilarity >= 0 && backendEmailSimilarity <= 1
        ? backendEmailSimilarity * 100
        : backendEmailSimilarity;
  } else {
    const comparisonScore = Number(fieldComparisons.email?.score0To100);
    if (!Number.isNaN(comparisonScore)) {
      emailScore =
        comparisonScore >= 0 && comparisonScore <= 1
          ? comparisonScore * 100
          : comparisonScore;
    }
  }

  if (Number.isNaN(emailScore)) {
    const fallbackSimilarity = fallbackEmailSimilarity(
      records[0].email,
      records[1].email,
    );
    emailScore = fallbackSimilarity * 100;
  }

  return {
    adSoyad: toPercent(fieldComparisons.fullName?.score0To100, 0),
    tcKimlikNo: toPercent(fieldComparisons.tc?.score0To100, 0),
    telefon: toPercent(fieldComparisons.phone?.score0To100, 0),
    email: toPercent(emailScore, 0),
    sehir: toPercent(fieldComparisons.city?.score0To100, 0),
  };
}

function normalizeEmailForSimilarity(email: string): {
  username: string;
  domain: string;
  full: string;
} {
  const cleaned = String(email || "").trim().toLowerCase();
  if (!cleaned || !cleaned.includes("@")) {
    return { username: "", domain: "", full: "" };
  }
  const [rawUser, rawDomain] = cleaned.split("@", 2);
  const userWithoutTag = rawUser.split("+")[0] || "";
  const username = userWithoutTag.replace(/\./g, "");
  const domain = rawDomain || "";
  return { username, domain, full: `${username}@${domain}` };
}

function simpleStringSimilarity(a: string, b: string): number {
  if (!a || !b) return 0;
  if (a === b) return 1;
  const aSet = new Set(a.split(""));
  const bSet = new Set(b.split(""));
  let intersection = 0;
  for (const ch of aSet) {
    if (bSet.has(ch)) intersection += 1;
  }
  const denom = Math.max(aSet.size, bSet.size, 1);
  return intersection / denom;
}

function fallbackEmailSimilarity(leftEmail: string, rightEmail: string): number {
  const left = normalizeEmailForSimilarity(leftEmail);
  const right = normalizeEmailForSimilarity(rightEmail);
  if (!left.full || !right.full) {
    return 0;
  }
  if (left.full === right.full) {
    return 0.95;
  }
  const usernameSim = simpleStringSimilarity(left.username, right.username);
  if (left.domain && right.domain && left.domain === right.domain) {
    return Math.max(0.6, 0.5 + usernameSim * 0.5);
  }
  return Math.max(0.2, usernameSim * 0.5);
}

export function finalDecisionLabel(value: string): string {
  if (value === "approved" || value === "same_person") {
    return "Onaylandı";
  }
  if (value === "rejected" || value === "different_person") {
    return "Reddedildi";
  }
  if (value === "pending" || value === "review") {
    return "Bekliyor";
  }
  return "Bilinmiyor";
}

export function finalDecisionTone(value: string): string {
  if (value === "approved" || value === "same_person") {
    return "bg-green-50 text-green-700";
  }
  if (value === "rejected" || value === "different_person") {
    return "bg-red-50 text-red-600";
  }
  return "bg-yellow-50 text-yellow-700";
}

export function mapDetectPairToView(
  pair: DetectDuplicatePair,
  index: number,
): UiDuplicatePair {
  const fieldComparisons = pair.fieldComparisons || {};
  const leftRecord = buildRecordFromDetectPair(pair, "left");
  const rightRecord = buildRecordFromDetectPair(pair, "right");
  const score = toPercentValue(
    pair.splinkMatchProbability ?? pair.ml_probability ?? 0,
    0,
  );

  return {
    id: `MG-${String(index + 1).padStart(3, "0")}`,
    pairId: pair.pairId,
    records: [leftRecord, rightRecord],
    score,
    workflowState: "bekleyen",
    finalDecision: pair.finalDecision || pair.decision,
    finalDecisionLabel: finalDecisionLabel(pair.finalDecision || pair.decision),
    matchDetails: buildMatchDetails(
      pair.features || {},
      [leftRecord, rightRecord],
      fieldComparisons,
    ),
    fieldComparisons,
    riskFlags: pair.riskFlags || [],
    ruleReasons: pair.ruleReasons || pair.reasons || [],
    decisionSource: pair.decisionSource,
    decisionType: pair.decision_type || "auto",
    reviewRequired: Boolean(pair.review_required ?? pair.decision === "pending"),
    splinkMatchProbability: Number(
      pair.splinkMatchProbability ?? pair.ml_probability ?? 0,
    ),
    splinkMatchWeight: pair.splinkMatchWeight ?? null,
    decisionReason: pair.reason || undefined,
  };
}

export function mapPendingMatchToView(
  match: AdminPendingMatch,
): UiDuplicatePair {
  const fieldComparisons = match.fieldComparisons || {};
  const leftRecord = buildRecordFromPendingMatch(match, "left");
  const rightRecord = buildRecordFromPendingMatch(match, "right");
  const finalDecision =
    match.finalDecision || match.decision || match.decision_reason || "review";
  const rawScore =
    match.score ??
    match.confidence ??
    match.splinkMatchProbability ??
    match.ml_score ??
    0;

  const workflowState: PairWorkflowState =
    match.decision === "approved"
      ? "onaylandi"
      : match.decision === "rejected"
        ? "reddedildi"
        : "bekleyen";

  return {
    id: String(match.id),
    pairId: `match-${match.id}`,
    backendMatchId: match.id,
    matchType: match.match_type || match.decisionSource || "unknown",
    backendDecision: match.decision || "pending",
    records: [leftRecord, rightRecord],
    score: toPercentValue(rawScore, 0),
    workflowState,
    finalDecision,
    finalDecisionLabel: finalDecisionLabel(finalDecision),
    matchDetails: buildMatchDetails(
      match.features || {},
      [leftRecord, rightRecord],
      fieldComparisons,
    ),
    fieldComparisons,
    riskFlags: match.riskFlags || [],
    ruleReasons: match.ruleReasons || [],
    decisionSource: match.decisionSource || "fallback_legacy",
    splinkMatchProbability: Number(rawScore),
    splinkMatchWeight: match.splinkMatchWeight ?? null,
    decisionReason: match.decision_reason || undefined,
    decisionType: (match.decision_type as "auto" | "manual" | undefined) || "manual",
    reviewRequired: Boolean(match.review_required ?? true),
    createdAt: match.created_at,
  };
}
