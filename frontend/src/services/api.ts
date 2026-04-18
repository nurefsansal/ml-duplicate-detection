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

export type DetectResponse = {
  sessionId: string;
  candidatePairs: number;
  duplicatePairs: number;
  insertedRows: number;
  totalRecords?: number;
  duplicates: Array<Record<string, unknown>>;
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

export async function normalizeRecords(records: NormalizedRecord[]) {
  const response = await apiClient.post("/api/v1/normalize", { records });
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
