import axios from "axios";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

export type NormalizedRecord = {
  adSoyad: string;
  tcKimlikNo: string;
  telefon: string;
  email: string;
  sehir: string;
};

export type FieldComparison = {
  rawLeftValue?: string | null;
  rawRightValue?: string | null;
  normalizedLeftValue?: string | null;
  normalizedRightValue?: string | null;
  comparisonMethod: string;
  comparisonResult: string;
  score0To100: number;
  exactMatch: boolean;
  notes: string;
};

export type DetectDuplicatePair = {
  pairId: string;
  left_index: number;
  right_index: number;
  record1: Record<string, unknown>;
  record2: Record<string, unknown>;
  features: Record<string, unknown>;
  fieldComparisons: Record<string, FieldComparison>;
  riskFlags: string[];
  ruleReasons: string[];
  reasons: string[];
  splinkMatchProbability?: number | null;
  splinkMatchWeight?: number | null;
  ml_probability?: number | null;
  decision: string;
  finalDecision: string;
  decisionSource: string;
};

export type DetectResponse = {
  sessionId: string;
  uploadId?: number | null;
  candidatePairs: number;
  duplicatePairs: number;
  insertedRows: number;
  totalRecords?: number;
  duplicates: DetectDuplicatePair[];
};

export type DetectOptions = {
  minRulesToMatch?: number;
  saveToDb?: boolean;
  sessionId?: string;
};

export type DetectFromUrlPayload = {
  url: string;
  method?: "GET" | "POST";
  apiKey?: string;
  minRulesToMatch?: number;
  saveToDb?: boolean;
  sessionId?: string;
};

export type NormalizeResponse = {
  totalRecords: number;
  normalizedRecords: Array<Record<string, unknown>>;
  uploadId?: number | null;
  normalizationRunId?: number | null;
  totalProcessed?: number;
  successCount?: number;
  failedCount?: number;
  previewRows?: Array<Record<string, unknown>>;
  validationWarnings?: string[];
};

export type MappingTargetFieldsResponse = {
  fields: string[];
};

export type ColumnMappingSuggestion = {
  sourceColumnName: string;
  targetFieldName: string;
  confidence: number;
  mappingType: string;
};

export type ColumnMappingResponse = {
  uploadId: number;
  sourceColumns: string[];
  suggestions: ColumnMappingSuggestion[];
};

export type FileUploadIngestResponse = {
  uploadId: number;
  fileName: string;
  totalRecords: number;
  sourceColumns: string[];
};

export async function uploadSpreadsheetForMapping(
  file: File,
): Promise<FileUploadIngestResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post("/api/v1/uploads/file", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export async function normalizeRecords(records: NormalizedRecord[]) {
  const response = await apiClient.post("/api/v1/normalize", { records });
  return response.data;
}

export async function normalizeFromFile(file: File): Promise<NormalizeResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post("/api/v1/normalize-file", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export async function normalizeFromUpload(uploadId: number): Promise<NormalizeResponse> {
  const response = await apiClient.post("/api/v1/normalize/from-upload", { uploadId });
  return response.data;
}

export async function getTargetFields(): Promise<MappingTargetFieldsResponse> {
  const response = await apiClient.get("/api/v1/mappings/target-fields");
  return response.data;
}

export async function getMappings(uploadId: number): Promise<ColumnMappingResponse> {
  const response = await apiClient.get(`/api/v1/mappings/${uploadId}`);
  return response.data;
}

export async function suggestMappings(uploadId: number): Promise<ColumnMappingResponse> {
  const response = await apiClient.post(`/api/v1/mappings/${uploadId}/suggest`);
  return response.data;
}

export async function saveMappings(
  uploadId: number,
  mappings: Array<{
    sourceColumnName: string;
    targetFieldName: string;
    confidence?: number;
    mappingType?: string;
  }>,
): Promise<ColumnMappingResponse> {
  const response = await apiClient.post(`/api/v1/mappings/${uploadId}`, {
    mappings,
    replaceExisting: true,
  });
  return response.data;
}

export async function detectDuplicates(
  records: NormalizedRecord[],
  options?: DetectOptions,
): Promise<DetectResponse> {
  const response = await apiClient.post("/api/v1/detect", {
    records,
    minRulesToMatch: options?.minRulesToMatch ?? 2,
    saveToDb: options?.saveToDb ?? false,
    sessionId: options?.sessionId,
  });
  return response.data;
}

export async function detectDuplicatesFromFile(
  file: File,
  options?: DetectOptions,
): Promise<DetectResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("minRulesToMatch", String(options?.minRulesToMatch ?? 2));
  formData.append("saveToDb", String(Boolean(options?.saveToDb)));
  if (options?.sessionId) {
    formData.append("sessionId", options.sessionId);
  }

  const response = await apiClient.post("/api/v1/detect-file", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export async function detectDuplicatesFromUrl(
  payload: DetectFromUrlPayload,
): Promise<DetectResponse> {
  const response = await apiClient.post("/api/v1/detect-from-url", {
    url: payload.url,
    method: payload.method ?? "GET",
    apiKey: payload.apiKey,
    minRulesToMatch: payload.minRulesToMatch ?? 2,
    saveToDb: payload.saveToDb ?? false,
    sessionId: payload.sessionId,
  });
  return response.data;
}

export async function healthCheck() {
  const response = await apiClient.get("/health");
  return response.data;
}

export type DetectDuplicateResponse = DetectResponse;

export type DetectDuplicateOptions = {
  minRulesToMatch?: number;
  saveToDb?: boolean;
  sessionId?: string;
  algorithms?: string[];
  threshold?: number;
};

export async function detectDuplicatesFromFileWithOptions(
  file: File,
  options?: DetectDuplicateOptions,
): Promise<DetectDuplicateResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("minRulesToMatch", String(options?.minRulesToMatch ?? 2));
  formData.append("saveToDb", String(Boolean(options?.saveToDb)));
  if (options?.sessionId) {
    formData.append("sessionId", options.sessionId);
  }
  if (options?.algorithms) {
    formData.append("algorithms", JSON.stringify(options.algorithms));
  }
  if (options?.threshold) {
    formData.append("threshold", String(options.threshold));
  }

  const response = await apiClient.post("/api/v1/detect-file", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export type AdminPendingMatch = {
  id: number;
  donor1_id: number;
  donor2_id: number;
  donor1_name: string;
  donor1_email?: string | null;
  donor1_phone?: string | null;
  donor1_city?: string | null;
  donor1_tc?: string | null;
  donor2_name: string;
  donor2_email?: string | null;
  donor2_phone?: string | null;
  donor2_city?: string | null;
  donor2_tc?: string | null;
  ml_score: number;
  confidence?: number | null;
  decision_reason?: string | null;
  features: Record<string, unknown>;
  fieldComparisons?: Record<string, FieldComparison>;
  riskFlags?: string[];
  ruleReasons?: string[];
  decisionSource?: string;
  finalDecision?: string | null;
  splinkMatchProbability?: number | null;
  splinkMatchWeight?: number | null;
  created_at?: string | null;
};

export type AdminPendingMatchesResponse = {
  success: boolean;
  count: number;
  matches: AdminPendingMatch[];
};

export type AdminApproveResponse = {
  success: boolean;
  match_id: number;
  status: string;
  approved_by?: string;
  approved_at?: string;
  entity_id?: number;
  entity_name?: string;
  donor_count?: number;
};

export type AdminRejectResponse = {
  success: boolean;
  match_id: number;
  status: string;
  rejected_by?: string;
  rejected_at?: string;
  reason?: string;
};

export async function getPendingMatches(options?: {
  uploadId?: number;
  limit?: number;
}): Promise<AdminPendingMatchesResponse> {
  const response = await apiClient.get("/api/v1/admin/pending-matches", {
    params: {
      upload_id: options?.uploadId,
      limit: options?.limit ?? 50,
    },
  });
  return response.data;
}

export async function approvePendingMatch(payload: {
  matchId: number;
  approvedBy?: string;
  mergeIntoEntity?: boolean;
  canonicalName?: string;
}): Promise<AdminApproveResponse> {
  const response = await apiClient.post("/api/v1/admin/approve-match", {
    match_id: payload.matchId,
    approved_by: payload.approvedBy ?? "frontend_admin",
    merge_into_entity: payload.mergeIntoEntity ?? true,
    canonical_name: payload.canonicalName,
  });
  return response.data;
}

export async function rejectPendingMatch(payload: {
  matchId: number;
  rejectedBy?: string;
  reason?: string;
}): Promise<AdminRejectResponse> {
  const response = await apiClient.post("/api/v1/admin/reject-match", {
    match_id: payload.matchId,
    rejected_by: payload.rejectedBy ?? "frontend_admin",
    reason: payload.reason,
  });
  return response.data;
}
