import axios from "axios";
import { getAuthToken, setAuthSession } from "./auth";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
});

apiClient.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/** Onay/red etiketli eşleşmeler + canonical ML özellikleri (RF şeması ile uyumlu). */
export async function downloadMlGroundTruthCsv(): Promise<void> {
  const response = await apiClient.get("/api/v1/ml/ground-truth.csv", {
    responseType: "blob",
  });
  const blob =
    response.data instanceof Blob
      ? response.data
      : new Blob([response.data as BlobPart], { type: "text/csv;charset=utf-8" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "match_ground_truth.csv";
  a.click();
  window.URL.revokeObjectURL(url);
}

// ─── Shared types ─────────────────────────────────────────────────────────────

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
  decision_type?: "auto" | "manual";
  review_required?: boolean;
  reason?: string;
  finalDecision: string;
  decisionSource: string;
  final_score?: number;
  score_source?: string;
  score_breakdown?: Record<string, unknown>;
  applied_thresholds?: Record<string, number>;
  safety_overrides?: Array<Record<string, unknown>>;
};

export type DetectResponse = {
  sessionId: string;
  jobId?: number | null;
  uploadId?: number | null;
  normalizationRunId?: number | null;
  detectionRunId?: number | null;
  candidatePairs: number;
  duplicatePairs: number;
  duplicateGroupCount: number;
  affectedRecordCount: number;
  insertedRows: number;
  totalRecords?: number;
  duplicates: DetectDuplicatePair[];
};

export type DetectOptions = {
  minRulesToMatch?: number;
  saveToDb?: boolean;
  sessionId?: string;
};

export type NormalizeResponse = {
  totalRecords: number;
  normalizedRecords: Array<Record<string, unknown>>;
  uploadId?: number | null;
  normalizationRunId?: number | null;
  upload_id?: number | null;
  normalization_run_id?: number | null;
  totalProcessed?: number | null;
  successCount?: number | null;
  failedCount?: number | null;
  previewRows?: Array<Record<string, unknown>>;
  validationWarnings?: string[];
};

// ─── Upload types ─────────────────────────────────────────────────────────────

export type UploadItem = {
  id: number;
  file_name: string;
  source_type: string;
  total_records: number;
  status: string;
  processing_stage: string | null;
  created_at: string | null;
  completed_at: string | null;
  latest_normalization_run_id: number | null;
};

export type UploadListResponse = {
  success: boolean;
  count: number;
  uploads: UploadItem[];
};

export type UploadFileResponse = {
  success: boolean;
  upload_id: number | null;
  job_id?: number | null;
  file_name: string;
  source_type: string;
  total_records: number;
  source_columns: string[];
  suggested_mappings: Record<string, string>;
};

export type JobStatusResponse = {
  success: boolean;
  job: {
    id: number;
    type: string;
    status: string;
    progress: number;
    total_rows: number;
    processed_rows: number;
    error_message: string | null;
    created_at: string | null;
    updated_at: string | null;
    pipeline?: {
      run_id: number;
      pipeline_type: string;
      status: string;
      request_id?: string | null;
      upload_id?: number | null;
      normalization_run_id?: number | null;
      detection_run_id?: number | null;
      warning_count: number;
      error_count: number;
      last_stage?: string | null;
      last_event_type?: string | null;
      last_message?: string | null;
      last_event_at?: string | null;
    } | null;
  };
};

export type UploadColumnsResponse = {
  success: boolean;
  upload_id: number;
  source_columns: string[];
  suggested_mappings: Record<string, string>;
};

export type RawRecordItem = {
  id: number;
  upload_id: number;
  row_index: number | null;
  raw_payload: Record<string, unknown>;
  created_at?: string | null;
};

export type RawRecordsListResponse = {
  success: boolean;
  upload_id: number;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  records: RawRecordItem[];
};

// ─── Connector types ──────────────────────────────────────────────────────────

export type ConnectorConnectionInput = {
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  db_schema?: string | null;
  sslmode?: string | null;
  label?: string;
};

export type ConnectorHealthResponse = {
  success: boolean;
  connection: {
    label: string;
    driver: string;
    host: string | null;
    port: number | null;
    database: string | null;
    schema?: string | null;
  };
  health: {
    ok: boolean;
    label: string;
    driver: string;
    host: string | null;
    port: number | null;
    database: string | null;
  };
};

export type ConnectorTablesResponse = {
  success: boolean;
  tables: Array<{
    table_schema: string;
    table_name: string;
  }>;
};

export type ConnectorPreviewResponse = {
  success: boolean;
  table_name: string;
  limit: number;
  rows: Array<Record<string, unknown>>;
};

// ─── Column mapping types ──────────────────────────────────────────────────────

export type ColumnMappingItem = {
  source_column: string;
  target_field: string;
  is_required?: boolean;
  mapping_type?: string;
};

export type SaveColumnMappingsResponse = {
  success: boolean;
  upload_id: number;
  saved: number;
};

export type ColumnMappingsListResponse = {
  success: boolean;
  upload_id: number | null;
  count: number;
  mappings: Array<{
    id: number;
    upload_id: number;
    source_column_name: string;
    target_field_name: string;
    is_required: boolean;
    mapping_type: string;
    created_at: string | null;
  }>;
};

// ─── Normalization run types ───────────────────────────────────────────────────

export type NormalizationRunResponse = {
  success: boolean;
  job_id?: number | null;
  upload_id: number;
  normalization_run_id: number;
  total_processed: number;
  success_count: number;
  failed_count: number;
};

// ─── Normalized record types ───────────────────────────────────────────────────

export type NormalizedRecordDb = {
  source?: "entity" | "normalized_record";
  source_label?: string;
  id: number;
  entity_id?: number | null;
  record_id?: number | null;
  upload_id: number;
  normalization_run_id: number | null;
  clean_name: string;
  first_name: string;
  last_name: string;
  clean_email: string;
  clean_phone: string;
  clean_tc: string;
  clean_city: string;
  clean_address: string;
  clean_muhatap_no: string;
  is_valid: boolean;
  blocking_key: string;
  created_at: string | null;
};

export type NormalizedRecordsListResponse = {
  success: boolean;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  records: NormalizedRecordDb[];
};

// ─── Report types ──────────────────────────────────────────────────────────────

export type ReportOverview = {
  success: boolean;
  total_uploads: number;
  total_normalized_records: number;
  total_match_candidates: number;
  approved: number;
  rejected: number;
  pending: number;
};

export type ReportDataQuality = {
  success: boolean;
  total_normalized_records: number;
  valid_records: number;
  invalid_records: number;
  validity_rate: number;
  tc_fill_rate?: number;
  phone_fill_rate?: number;
  email_fill_rate?: number;
  normalization_runs: number;
  total_processed: number;
  total_success: number;
  total_failed: number;
};

export type ReportDetectionSummary = {
  success: boolean;
  total_detection_runs: number;
  total_match_candidates: number;
  total_duplicate_pairs: number;
  total_duplicate_groups: number;
  total_affected_records: number;
  approved: number;
  rejected: number;
  pending: number;
  avg_score_pct: number;
};

export type ReportReviewSummary = {
  success: boolean;
  total_reviews: number;
  approvals: number;
  rejections: number;
  recent_reviews?: Array<{
    id: number;
    user: string;
    decision: string;
    date: string | null;
    group_id: string;
    match_id: number;
    left_id?: number | null;
    right_id?: number | null;
  }>;
};

export type ReportUploadHistoryItem = {
  id: number;
  file_name: string;
  source_type: string;
  total_records: number;
  status: string;
  processing_stage: string | null;
  created_at: string | null;
  completed_at: string | null;
  created_by: string | null;
};

export type ReportUploadHistory = {
  success: boolean;
  count: number;
  uploads: ReportUploadHistoryItem[];
};

// ─── Admin types ───────────────────────────────────────────────────────────────

export type AdminPendingMatch = {
  id: number;
  left_id: number;
  right_id: number;
  score?: number | null;
  match_type?: string | null;
  decision?: string | null;
  decision_type?: "auto" | "manual" | null;
  review_required?: boolean | null;
  reason?: string | null;
  donor1_id: number;
  donor2_id: number;
  donor1_name: string;
  donor1_email?: string | null;
  donor1_phone?: string | null;
  donor1_city?: string | null;
  donor1_tc?: string | null;
  donor1_muhatap_no?: string | null;
  donor2_name: string;
  donor2_email?: string | null;
  donor2_phone?: string | null;
  donor2_city?: string | null;
  donor2_tc?: string | null;
  donor2_muhatap_no?: string | null;
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
  final_score?: number;
  score_source?: string;
  score_breakdown?: Record<string, unknown>;
  applied_thresholds?: Record<string, number>;
  safety_overrides?: Array<Record<string, unknown>>;
};

export type AdminPendingMatchesResponse = {
  success: boolean;
  decision?: "pending" | "approved" | "rejected";
  count: number;
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  matches: AdminPendingMatch[];
};

export type DuplicateGroupRecord = {
  record_id: number;
  raw_id: number;
  upload_id: number;
  membership_status?: "confirmed" | "pending" | "excluded";
  entity_id?: number | null;
  clean_name: string;
  clean_tc: string;
  clean_phone: string;
  clean_email: string;
  clean_city: string;
  clean_address: string;
  clean_muhatap_no: string;
  raw_payload?: Record<string, unknown>;
  normalized_payload: Record<string, unknown>;
  completeness_score: number;
};

export type DuplicateGroup = {
  group_id: string;
  entity_id?: number | null;
  record_ids: number[];
  match_candidate_ids?: number[];
  pair_count?: number;
  avg_score?: number;
  max_score?: number;
  group_score: number;
  group_score_max: number;
  match_count: number;
  muhatap_codes?: string[];
  different_muhatap_code?: boolean;
  records: DuplicateGroupRecord[];
  golden_record: {
    clean_name?: string;
    clean_tc?: string;
    clean_phone?: string;
    clean_email?: string;
    clean_city?: string;
    clean_address?: string;
    clean_muhatap_no?: string;
    merged_muhatap_sources?: Array<{
      record_id: number;
      clean_name: string;
      clean_muhatap_no: string;
    }>;
    merged_muhatap_report_line?: string;
    merged_member_snapshots?: Array<
      DuplicateGroupRecord & { muhatap_no_effective?: string }
    >;
  };
};

export type DuplicateGroupsResponse = {
  success: boolean;
  decision?: "pending" | "approved" | "rejected";
  count: number;
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  groups: DuplicateGroup[];
};

export type PartialApproveGroupResponse = {
  entity_id: number;
  confirmed_count: number;
  excluded_count: number;
  golden_record_id: number | null;
};

export type GoldenRecordUpdateResponse = {
  success: boolean;
  entity_id: number;
  canonical_data: DuplicateGroup["golden_record"];
  golden_record_id: number | null;
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

export type DetectDuplicateResponse = DetectResponse;

export type DetectDuplicateOptions = {
  minRulesToMatch?: number;
  saveToDb?: boolean;
  sessionId?: string;
  algorithms?: string[];
  threshold?: number;
};

export type LoginResponse = {
  success: boolean;
  access_token: string;
  token_type: "bearer";
  user: { username: string };
};

// ─── Core API functions ────────────────────────────────────────────────────────

export async function healthCheck() {
  const response = await apiClient.get("/health");
  return response.data;
}

export async function login(payload: {
  username: string;
  password: string;
}): Promise<LoginResponse> {
  const response = await apiClient.post("/api/v1/auth/login", payload);
  const data = response.data as LoginResponse;
  if (data?.access_token && data?.user?.username) {
    setAuthSession(data.access_token, data.user.username);
  }
  return data;
}

// ─── Normalize (LEGACY) ────────────────────────────────────────────────────────
// New main flow: uploadFileOnly → startNormalizationRun
// These endpoints (normalize, normalize-file) still exist on the backend but are
// no longer called by the main frontend pages.

/** @deprecated Use uploadFileOnly + startNormalizationRun instead. */
export async function normalizeRecords(records: NormalizedRecord[]) {
  const response = await apiClient.post("/api/v1/normalize", { records });
  return response.data;
}

/** @deprecated Use uploadFileOnly + startNormalizationRun instead. */
export async function normalizeFromFile(
  file: File,
): Promise<NormalizeResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post("/api/v1/normalize-file", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

// ─── Upload file (upload-only, no normalization) ───────────────────────────────

export async function uploadFileOnly(file: File): Promise<UploadFileResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post("/api/v1/uploads/file", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function getJobStatus(jobId: number): Promise<JobStatusResponse> {
  const response = await apiClient.get(`/api/v1/jobs/${jobId}`);
  return response.data;
}

// ─── Upload list ───────────────────────────────────────────────────────────────

export async function listUploads(
  limit = 50,
  options?: { hasNormalizedRecords?: boolean },
): Promise<UploadListResponse> {
  const response = await apiClient.get("/api/v1/uploads", {
    params: {
      limit,
      has_normalized_records: options?.hasNormalizedRecords ?? false,
    },
  });
  return response.data;
}

// ─── Upload columns ────────────────────────────────────────────────────────────

export async function getUploadColumns(
  uploadId: number,
): Promise<UploadColumnsResponse> {
  const response = await apiClient.get(`/api/v1/uploads/${uploadId}/columns`);
  return response.data;
}

// ─── Raw records ────────────────────────────────────────────────────────────────

export async function getRawRecords(params: {
  upload_id: number;
  page?: number;
  page_size?: number;
}): Promise<RawRecordsListResponse> {
  const response = await apiClient.get(
    `/api/v1/uploads/${params.upload_id}/raw-records`,
    {
      params: { page: params.page, page_size: params.page_size },
    },
  );
  return response.data;
}

// ─── Column mappings ───────────────────────────────────────────────────────────

export async function getColumnMappings(
  uploadId: number,
): Promise<ColumnMappingsListResponse> {
  const response = await apiClient.get("/api/v1/column-mappings", {
    params: { upload_id: uploadId },
  });
  return response.data;
}

export async function saveColumnMappings(
  uploadId: number,
  mappings: ColumnMappingItem[],
): Promise<SaveColumnMappingsResponse> {
  const response = await apiClient.post("/api/v1/column-mappings", {
    upload_id: uploadId,
    mappings,
  });
  return response.data;
}

// ─── Normalization runs ────────────────────────────────────────────────────────

export async function startNormalizationRun(
  uploadId: number,
  columnMappings?: ColumnMappingItem[],
): Promise<NormalizationRunResponse> {
  const response = await apiClient.post("/api/v1/normalization-runs", {
    upload_id: uploadId,
    column_mappings: columnMappings,
  });
  return response.data;
}

// ─── Detect (from DB — no file needed) ────────────────────────────────────────

export async function startDetectionFromUpload(
  uploadId: number,
  options?: {
    normalizationRunId?: number | null;
    minRulesToMatch?: number;
    sessionId?: string;
  },
): Promise<DetectResponse> {
  const response = await apiClient.post(
    "/api/v1/detect",
    {
      records: [],
      uploadId,
      normalizationRunId: options?.normalizationRunId ?? null,
      minRulesToMatch: options?.minRulesToMatch ?? 2,
      saveToDb: true,
      sessionId: options?.sessionId,
    },
    { timeout: 300_000 },
  );
  return response.data;
}

export async function startDetectionFromNormalizationRun(
  normalizationRunId: number,
  options?: { minRulesToMatch?: number; sessionId?: string },
): Promise<DetectResponse> {
  const response = await apiClient.post("/api/v1/detect", {
    records: [],
    normalizationRunId,
    minRulesToMatch: options?.minRulesToMatch ?? 2,
    saveToDb: true,
    sessionId: options?.sessionId,
  });
  return response.data;
}

// ─── Detect (LEGACY) ──────────────────────────────────────────────────────────
// New main flow: startDetectionFromUpload or startDetectionFromNormalizationRun
// These functions still work but are no longer used by the main detection page.

/** @deprecated Use startDetectionFromUpload instead. */
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

/** @deprecated Use startDetectionFromUpload instead. */
export async function detectDuplicatesFromFile(
  file: File,
  options?: DetectOptions,
): Promise<DetectResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("minRulesToMatch", String(options?.minRulesToMatch ?? 2));
  formData.append("saveToDb", String(Boolean(options?.saveToDb)));
  if (options?.sessionId) formData.append("sessionId", options.sessionId);
  const response = await apiClient.post("/api/v1/detect-file", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

/** @deprecated Use startDetectionFromUpload instead. */
export async function detectDuplicatesFromFileWithOptions(
  file: File,
  options?: DetectDuplicateOptions,
): Promise<DetectDuplicateResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("minRulesToMatch", String(options?.minRulesToMatch ?? 2));
  formData.append("saveToDb", String(Boolean(options?.saveToDb)));
  if (options?.sessionId) formData.append("sessionId", options.sessionId);
  if (options?.algorithms)
    formData.append("algorithms", JSON.stringify(options.algorithms));
  if (options?.threshold)
    formData.append("threshold", String(options.threshold));
  const response = await apiClient.post("/api/v1/detect-file", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

// ─── Normalized records ────────────────────────────────────────────────────────

export async function getNormalizedRecords(params?: {
  upload_id?: number;
  normalization_run_id?: number;
  is_valid?: boolean;
  search?: string;
  has_missing_tc?: boolean;
  has_missing_phone?: boolean;
  has_missing_email?: boolean;
  has_missing_city?: boolean;
  page?: number;
  page_size?: number;
}): Promise<NormalizedRecordsListResponse> {
  const response = await apiClient.get("/api/v1/normalized-records", {
    params,
  });
  return response.data;
}

export async function getNormalizedRecord(id: number) {
  const response = await apiClient.get(`/api/v1/normalized-records/${id}`);
  return response.data;
}

export function buildNormalizedRecordsExportUrl(params?: {
  upload_id?: number;
  normalization_run_id?: number;
  format?: "csv" | "json" | "xlsx";
}): string {
  const base = `${API_BASE_URL}/api/v1/normalized-records/export`;
  const qs = new URLSearchParams();
  if (params?.upload_id != null) qs.set("upload_id", String(params.upload_id));
  if (params?.normalization_run_id != null)
    qs.set("normalization_run_id", String(params.normalization_run_id));
  qs.set("format", params?.format ?? "csv");
  return `${base}?${qs.toString()}`;
}

// ─── Reports ───────────────────────────────────────────────────────────────────

export async function getReportOverview(params?: {
  date_from?: string;
  date_to?: string;
}): Promise<ReportOverview> {
  const response = await apiClient.get("/api/v1/reports/overview", { params });
  return response.data;
}

export async function getReportDataQuality(params?: {
  date_from?: string;
  date_to?: string;
}): Promise<ReportDataQuality> {
  const response = await apiClient.get("/api/v1/reports/data-quality", {
    params,
  });
  return response.data;
}

export async function getReportDetectionSummary(params?: {
  date_from?: string;
  date_to?: string;
}): Promise<ReportDetectionSummary> {
  const response = await apiClient.get("/api/v1/reports/detection-summary", {
    params,
  });
  return response.data;
}

export async function getReportReviewSummary(params?: {
  date_from?: string;
  date_to?: string;
}): Promise<ReportReviewSummary> {
  const response = await apiClient.get("/api/v1/reports/review-summary", {
    params,
  });
  return response.data;
}

export async function getReportUploadHistory(params?: {
  date_from?: string;
  date_to?: string;
  limit?: number;
}): Promise<ReportUploadHistory> {
  const response = await apiClient.get("/api/v1/reports/upload-history", {
    params,
  });
  return response.data;
}

function triggerCsvDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

async function downloadReportCsv(
  endpoint: string,
  filename: string,
  params?: Record<string, string | number | undefined>,
): Promise<void> {
  const response = await apiClient.get(endpoint, {
    params,
    responseType: "blob",
  });
  triggerCsvDownload(response.data as Blob, filename);
}

export async function downloadCleanDatasetCsv(options?: {
  uploadId?: number;
}): Promise<void> {
  await downloadReportCsv(
    "/api/v1/reports/export/clean_dataset.csv",
    "clean_dataset.csv",
    { upload_id: options?.uploadId },
  );
}

export async function downloadDuplicateGroupsCsv(options?: {
  uploadId?: number;
  decision?: "pending" | "approved" | "rejected";
}): Promise<void> {
  await downloadReportCsv(
    "/api/v1/reports/export/duplicate_groups.csv",
    "duplicate_groups.csv",
    {
      upload_id: options?.uploadId,
      decision: options?.decision,
    },
  );
}

export async function downloadApprovedMatchesCsv(options?: {
  uploadId?: number;
}): Promise<void> {
  await downloadReportCsv(
    "/api/v1/reports/export/approved_matches.csv",
    "approved_matches.csv",
    { upload_id: options?.uploadId },
  );
}

export async function downloadGoldenRecordsCsv(options?: {
  uploadId?: number;
  decision?: "pending" | "approved" | "rejected";
}): Promise<void> {
  await downloadReportCsv(
    "/api/v1/reports/export/golden_records.csv",
    "golden_records.csv",
    {
      upload_id: options?.uploadId,
      decision: options?.decision,
    },
  );
}

export type MuhatapMergeSummary = {
  target_muhatap_code?: string;
  target_name?: string;
  prior_muhatap_codes?: string[];
  merged_muhatap_report_line?: string;
};

export type UploadWithMergeItem = {
  id: number;
  file_name: string;
  source_type?: string;
  total_records?: number;
  status?: string;
  created_at?: string | null;
  merge_group_count?: number;
};

export type MuhatapMergeReportGroup = {
  group_id: string;
  entity_id?: number | null;
  muhatap_codes?: string[];
  record_ids: number[];
  group_score: number;
  golden_record: DuplicateGroup["golden_record"] & {
    target_muhatap_code?: string;
    prior_muhatap_codes?: string[];
    merged_muhatap_report_line?: string;
  };
  merge_summary?: MuhatapMergeSummary;
  records: DuplicateGroup["records"];
};

export type MuhatapMergeReportResponse = {
  success: boolean;
  decision?: string;
  upload_id?: number | null;
  total_all_groups?: number;
  count_with_merge_detail?: number;
  page?: number;
  page_size?: number;
  groups: MuhatapMergeReportGroup[];
  error?: string;
};

export async function getMuhatapMergeReport(options?: {
  uploadId?: number;
  decision?: "pending" | "approved" | "rejected";
  page?: number;
  pageSize?: number;
}): Promise<MuhatapMergeReportResponse> {
  const response = await apiClient.get("/api/v1/reports/muhatap-merge-detail", {
    params: {
      upload_id: options?.uploadId,
      decision: options?.decision ?? "approved",
      page: options?.page ?? 1,
      page_size: options?.pageSize ?? 50,
    },
  });
  return response.data as MuhatapMergeReportResponse;
}

export async function downloadMuhatapMergeDetailCsv(options?: {
  uploadId?: number;
  decision?: "pending" | "approved" | "rejected";
  /** İstemci tarafında kaydedilecek dosya adı (varsayılan: muhatap_merge_detail.csv) */
  filename?: string;
}): Promise<void> {
  await downloadReportCsv(
    "/api/v1/reports/export/muhatap_merge_detail.csv",
    options?.filename ?? "muhatap_merge_detail.csv",
    {
      upload_id: options?.uploadId,
      decision: options?.decision ?? "approved",
    },
  );
}

export async function listUploadsWithMuhatapMerge(
  limit = 100,
): Promise<{ success: boolean; count: number; uploads: UploadWithMergeItem[] }> {
  const response = await apiClient.get("/api/v1/reports/uploads-with-merge", {
    params: { limit },
  });
  return response.data;
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

export type UploadPipelineStatus = {
  success: boolean;
  upload_id: number;
  has_normalized_records: boolean;
  normalized_record_count: number;
  has_detection_run: boolean;
  latest_detection_run_id: number | null;
  match_candidate_count: number;
  can_review: boolean;
};

export async function getUploadPipelineStatus(
  uploadId: number,
): Promise<UploadPipelineStatus> {
  const response = await apiClient.get(`/api/v1/uploads/${uploadId}/pipeline-status`);
  return response.data as UploadPipelineStatus;
}

function asciiDownloadFilename(name: string, fallback: string): string {
  const base = name
    .normalize("NFKD")
    .replace(/[^\w.-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
  return base.endsWith(".pdf") ? base : `${base || fallback}.pdf`;
}

export async function downloadMuhatapMergePdf(options: {
  uploadId: number;
  decision?: "pending" | "approved" | "rejected";
  filename?: string;
}): Promise<void> {
  const response = await apiClient.get("/api/v1/reports/export/muhatap_merge.pdf", {
    params: {
      upload_id: options.uploadId,
      decision: options.decision ?? "approved",
    },
    responseType: "blob",
    validateStatus: () => true,
  });

  const blob = response.data instanceof Blob ? response.data : new Blob([response.data]);
  const contentType = String(response.headers["content-type"] || "").toLowerCase();

  if (response.status < 200 || response.status >= 300) {
    const text = await blob.text();
    let message = "PDF raporu indirilemedi.";
    try {
      const json = JSON.parse(text) as { detail?: string; error?: string };
      message = json.detail || json.error || message;
    } catch {
      if (text.trim()) message = text.trim().slice(0, 300);
    }
    throw new Error(message);
  }

  if (!contentType.includes("application/pdf")) {
    const text = await blob.text();
    throw new Error(text.trim().slice(0, 300) || "Sunucu PDF yerine beklenmeyen yanıt döndürdü.");
  }

  const header = await blob.slice(0, 4).text();
  if (!header.startsWith("%PDF")) {
    throw new Error("İndirilen dosya geçerli bir PDF değil. Backend loglarını kontrol edin.");
  }

  const fallback = `muhatap_birlestirme_${options.uploadId}`;
  const filename = asciiDownloadFilename(options.filename ?? fallback, fallback);
  triggerBlobDownload(blob, filename);
}

// ─── Admin ─────────────────────────────────────────────────────────────────────

export async function getPendingMatches(options?: {
  uploadId?: number;
  limit?: number;
  page?: number;
  pageSize?: number;
  differentMuhatapPair?: boolean;
}): Promise<AdminPendingMatchesResponse> {
  const response = await apiClient.get("/api/v1/matches", {
    params: {
      decision: "pending",
      upload_id: options?.uploadId,
      limit: options?.limit ?? 50,
      page: options?.page,
      page_size: options?.pageSize,
      different_muhatap_pair:
        options?.differentMuhatapPair === false ? false : true,
    },
  });
  return response.data;
}

export async function getMatches(options?: {
  decision?: "pending" | "approved" | "rejected";
  uploadId?: number;
  limit?: number;
  page?: number;
  pageSize?: number;
  /** false: tüm çiftler (varsayılan: yalnızca farklı muhatap kodlu çiftler) */
  differentMuhatapPair?: boolean;
}): Promise<AdminPendingMatchesResponse> {
  const response = await apiClient.get("/api/v1/matches", {
    params: {
      decision: options?.decision ?? "pending",
      upload_id: options?.uploadId,
      limit: options?.limit ?? 100,
      page: options?.page,
      page_size: options?.pageSize,
      different_muhatap_pair:
        options?.differentMuhatapPair === false ? false : true,
    },
  });
  return response.data;
}

export async function getDuplicateGroups(options?: {
  decision?: "pending" | "approved" | "rejected";
  uploadId?: number;
  limit?: number;
  page?: number;
  pageSize?: number;
  differentMuhatapCode?: boolean;
}): Promise<DuplicateGroupsResponse> {
  const response = await apiClient.get("/api/v1/duplicate-groups", {
    params: {
      decision: options?.decision ?? "approved",
      upload_id: options?.uploadId,
      limit: options?.limit ?? 5000,
      page: options?.page,
      page_size: options?.pageSize,
      different_muhatap_code:
        options?.differentMuhatapCode === false ? false : true,
    },
  });
  return response.data;
}

export async function partialApproveGroup(payload: {
  groupId: string;
  recordIds: number[];
  approvedRecordIds: number[];
  rejectedRecordIds: number[];
  uploadId?: number;
  decision?: "pending" | "approved" | "rejected";
  note?: string;
  goldenRecordOverride?: DuplicateGroup["golden_record"];
}): Promise<PartialApproveGroupResponse> {
  const body: Record<string, unknown> = {
    record_ids: payload.recordIds,
    approved_record_ids: payload.approvedRecordIds,
    rejected_record_ids: payload.rejectedRecordIds,
    upload_id: payload.uploadId,
    decision: payload.decision,
    note: payload.note,
  };
  if (payload.goldenRecordOverride) {
    body.golden_record_override = payload.goldenRecordOverride;
  }
  const response = await apiClient.post(
    `/api/v1/matches/group/${encodeURIComponent(payload.groupId)}/partial-approve`,
    body,
  );
  return response.data;
}

export async function updateGoldenRecord(payload: {
  entityId: number;
  fields: DuplicateGroup["golden_record"];
  note?: string;
}): Promise<GoldenRecordUpdateResponse> {
  const response = await apiClient.patch(
    `/api/v1/entities/${payload.entityId}/golden-record`,
    {
      fields: payload.fields,
      note: payload.note,
    },
  );
  return response.data;
}

export async function approvePendingMatch(payload: {
  matchId: number;
  approvedBy?: string;
  mergeIntoEntity?: boolean;
  canonicalName?: string;
}): Promise<AdminApproveResponse> {
  const body: Record<string, unknown> = {
    match_id: payload.matchId,
    merge_into_entity: payload.mergeIntoEntity ?? true,
  };
  if (payload.approvedBy) body.approved_by = payload.approvedBy;
  if (payload.canonicalName) body.canonical_name = payload.canonicalName;
  const response = await apiClient.post("/api/v1/admin/approve-match", body);
  return response.data;
}

export async function resetMatchDecision(payload: {
  matchId: number;
  reason?: string;
}): Promise<{ success: boolean; match_id: number; status: string; reset_by?: string }> {
  const body: Record<string, unknown> = {};
  if (payload.reason) body.reason = payload.reason;
  const response = await apiClient.post(
    `/api/v1/admin/matches/${payload.matchId}/reset`,
    body,
  );
  return response.data;
}

export async function rejectPendingMatch(payload: {
  matchId: number;
  rejectedBy?: string;
  reason?: string;
}): Promise<AdminRejectResponse> {
  const body: Record<string, unknown> = { match_id: payload.matchId };
  if (payload.rejectedBy) body.rejected_by = payload.rejectedBy;
  if (payload.reason) body.reason = payload.reason;
  const response = await apiClient.post("/api/v1/admin/reject-match", body);
  return response.data;
}

export async function getSettings(): Promise<Record<string, any>> {
  const response = await apiClient.get("/api/settings");
  return response.data;
}

export async function saveSettings(settings: Record<string, any>): Promise<void> {
  await apiClient.post("/api/settings/batch", { settings });
}
