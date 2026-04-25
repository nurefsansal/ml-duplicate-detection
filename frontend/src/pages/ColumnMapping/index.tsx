import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  getMappings,
  getTargetFields,
  normalizeFromUpload,
  saveMappings,
  suggestMappings,
} from "../../services/api";

type MappingState = Record<string, string>;

function formatApiError(err: unknown): string {
  if (typeof err === "object" && err && "response" in err) {
    const response = (err as { response?: { data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d))).join("; ");
    }
  }
  if (err instanceof Error) {
    return err.message;
  }
  return "Bilinmeyen bir hata oluştu";
}

export default function ColumnMappingPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const uploadId = Number(searchParams.get("uploadId") || "0");

  const [targetFields, setTargetFields] = useState<string[]>([]);
  const [sourceColumns, setSourceColumns] = useState<string[]>([]);
  const [mappingState, setMappingState] = useState<MappingState>({});
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!uploadId) {
      setError("Geçerli bir uploadId parametresi bulunamadı.");
      return;
    }

    setLoading(true);
    Promise.all([getTargetFields(), getMappings(uploadId)])
      .then(([fieldsResp, mappingResp]) => {
        setTargetFields(fieldsResp.fields);
        setSourceColumns(mappingResp.sourceColumns);
        const initialState: MappingState = {};
        for (const item of mappingResp.suggestions) {
          initialState[item.sourceColumnName] = item.targetFieldName;
        }
        setMappingState(initialState);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Mapping verisi alınamadı");
      })
      .finally(() => setLoading(false));
  }, [uploadId]);

  const canSave = useMemo(
    () => sourceColumns.length > 0 && Object.keys(mappingState).length > 0,
    [mappingState, sourceColumns.length],
  );

  const runSuggest = async () => {
    if (!uploadId) return;
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const resp = await suggestMappings(uploadId);
      setSourceColumns(resp.sourceColumns);
      const nextState: MappingState = {};
      for (const item of resp.suggestions) {
        nextState[item.sourceColumnName] = item.targetFieldName;
      }
      setMappingState((prev) => ({ ...prev, ...nextState }));
      setMessage("Otomatik eşleme önerileri getirildi.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Öneri alınamadı");
    } finally {
      setLoading(false);
    }
  };

  const runSave = async () => {
    if (!uploadId) return;
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const payload = sourceColumns.map((sourceColumnName) => ({
        sourceColumnName,
        targetFieldName: mappingState[sourceColumnName] || "ignored",
        confidence: 1,
        mappingType: "manual",
      }));
      await saveMappings(uploadId, payload);
      setMessage("Kolon eşleme kaydedildi.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Kaydetme başarısız");
    } finally {
      setLoading(false);
    }
  };

  const runNormalize = async () => {
    if (!uploadId || !Number.isFinite(uploadId)) {
      setError("Geçerli bir uploadId gerekli. Lütfen yükleme adımından bu sayfaya yönlendirin.");
      return;
    }
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const result = await normalizeFromUpload(uploadId);
      const runNote =
        typeof result.normalizationRunId === "number"
          ? ` (normalizasyon çalışması #${result.normalizationRunId})`
          : "";
      setMessage(`Normalizasyon tamamlandı: ${result.totalRecords} kayıt işlendi.${runNote}`);
      localStorage.setItem("lastNormalizeUploadId", String(uploadId));
      navigate("/veri-normalizasyon");
    } catch (err: unknown) {
      setError(formatApiError(err) || "Normalizasyon başarısız");
    } finally {
      setLoading(false);
    }
  };

  return (
    <DashboardLayout>
      <Header
        title="Kolon Eşleme"
        subtitle="Kaynak kolonları standart hedef alanlara eşleyin"
      />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <div className="bg-white border border-gray-100 rounded-xl p-4 text-sm text-gray-700">
          Upload ID: <span className="font-semibold">{uploadId || "-"}</span>
        </div>

        {message ? <div className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700">{message}</div> : null}
        {error ? <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

        <div className="bg-white border border-gray-100 rounded-xl p-5">
          <div className="flex flex-wrap gap-3 mb-4">
            <button
              onClick={runSuggest}
              disabled={loading || !uploadId}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-60"
            >
              Otomatik Öneri
            </button>
            <button
              onClick={runSave}
              disabled={loading || !canSave}
              className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm disabled:opacity-60"
            >
              Mapping'i Kaydet
            </button>
            <button
              onClick={runNormalize}
              disabled={loading || !uploadId}
              className="px-4 py-2 rounded-lg border border-gray-300 text-sm disabled:opacity-60"
            >
              Normalizasyona Geç
            </button>
          </div>

          {sourceColumns.length === 0 ? (
            <p className="text-sm text-gray-500">Kaynak kolon bulunamadı.</p>
          ) : (
            <div className="space-y-3">
              {sourceColumns.map((sourceColumn) => (
                <div key={sourceColumn} className="grid grid-cols-1 md:grid-cols-2 gap-3 items-center">
                  <div className="text-sm text-gray-700">{sourceColumn}</div>
                  <select
                    className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
                    value={mappingState[sourceColumn] || "ignored"}
                    onChange={(e) =>
                      setMappingState((prev) => ({ ...prev, [sourceColumn]: e.target.value }))
                    }
                  >
                    {targetFields.map((field) => (
                      <option key={field} value={field}>
                        {field}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
