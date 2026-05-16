import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useRequireUploadId } from "../../hooks/useRequireUploadId";

import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  getUploadColumns,
  listUploads,
  saveColumnMappings,
  startNormalizationRun,
  type ColumnMappingItem,
  type NormalizationRunResponse,
  type UploadItem,
} from "../../services/api";
import { useJobPolling } from "../../hooks/useJobPolling";
import { JobStatusBanner } from "../../components/feature/JobStatusBanner";
import { FlowNav } from "../../components/feature/FlowNav";

const TARGET_FIELD_OPTIONS = [
  { value: "", label: "— eşleştirme yok —" },
  { value: "name", label: "Ad Soyad (name)" },
  { value: "tc", label: "TC Kimlik No (tc)" },
  { value: "phone", label: "Telefon (phone)" },
  { value: "email", label: "E-posta (email)" },
  { value: "city", label: "Şehir (city)" },
  { value: "muhatap_no", label: "Muhatap Kodu (muhatap_no)" },
  { value: "address", label: "Adres (address)" },
  { value: "other", label: "Diğer (atla)" },
];

function formatUploadStageLabel(stage: string | null | undefined, status: string | null | undefined): string {
  const value = (stage || status || "").toLowerCase();
  if (!value) return "Beklemede";
  if (value.includes("normalize")) return "Standardize edildi";
  if (value.includes("detect")) return "Benzer kayıt tarandı";
  if (value.includes("review")) return "İnceleme bekliyor";
  if (value.includes("complete")) return "Yükleme tamamlandı";
  if (value.includes("process")) return "İşleniyor";
  if (value.includes("fail") || value.includes("error")) return "Hata oluştu";
  if (value.includes("upload")) return "Dosya yüklendi";
  return stage || status || "-";
}

export default function VeriNormalizasyon() {
  const navigate = useNavigate();
  const [, setSearchParams] = useSearchParams();
  const uploadId = useRequireUploadId();

  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [normalizeResult, setNormalizeResult] =
    useState<NormalizationRunResponse | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);

  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [loadingUploads, setLoadingUploads] = useState(false);

  const [sourceColumns, setSourceColumns] = useState<string[]>([]);
  const [columnMappings, setColumnMappings] = useState<Record<string, string>>(
    {},
  );
  const [loadingColumns, setLoadingColumns] = useState(false);

  useEffect(() => {
    let mounted = true;
    import("../../services/api")
      .then(({ healthCheck }) => healthCheck())
      .then(() => {
        if (mounted) {
          setBackendHealthy(true);
        }
      })
      .catch(() => {
        if (mounted) {
          setBackendHealthy(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    setLoadingUploads(true);
    listUploads(50)
      .then((data) => setUploads(data.uploads ?? []))
      .catch(() => {})
      .finally(() => setLoadingUploads(false));
  }, []);

  useEffect(() => {
    if (uploadId === null) {
      setSourceColumns([]);
      setColumnMappings({});
      return;
    }

    setLoadingColumns(true);
    getUploadColumns(uploadId)
      .then((data) => {
        const columns = data.source_columns ?? [];
        setSourceColumns(columns);

        const initialMappings: Record<string, string> = {};
        for (const column of columns) {
          initialMappings[column] = data.suggested_mappings?.[column] ?? "";
        }
        setColumnMappings(initialMappings);
      })
      .catch(() => {})
      .finally(() => setLoadingColumns(false));
  }, [uploadId]);

  const handleRun = async () => {
    if (uploadId === null) return;

    setRunning(true);
    setDone(false);
    setProgress(0);
    setErrorMessage("");
    setStatusMessage("");
    setNormalizeResult(null);
    setJobId(null);

    const mappingItems: ColumnMappingItem[] = Object.entries(columnMappings)
      .filter(([, targetField]) => targetField && targetField !== "other")
      .map(([source_column, target_field]) => ({
        source_column,
        target_field,
      }));

    try {
      if (mappingItems.length > 0) {
        try {
          await saveColumnMappings(uploadId, mappingItems);
        } catch {
          setRunning(false);
          setErrorMessage(
            "Kolon eşleştirmeleri kaydedilemedi. Lütfen tekrar deneyin.",
          );
          return;
        }
      }

      const result = await startNormalizationRun(
        uploadId,
        mappingItems.length > 0 ? mappingItems : undefined,
      );

      setNormalizeResult(result);
      setJobId(typeof result.job_id === "number" ? result.job_id : null);

      localStorage.setItem("lastUploadId", String(result.upload_id));
      localStorage.setItem(
        "lastNormalizationRunId",
        String(result.normalization_run_id),
      );

      setStatusMessage(
        result.job_id
          ? `Standardizasyon başlatıldı (İş No: ${result.job_id}). Arka planda sürüyor…`
          : "Standardizasyon başlatıldı. Arka planda sürüyor…",
      );
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Standardizasyon sırasında bir hata oluştu",
      );
      setProgress(0);
    } finally {
      // running state will be finalized when job completes (polling)
    }
  };

  const { job: normalizationJob, error: jobError } = useJobPolling(jobId);

  useEffect(() => {
    if (jobError) setErrorMessage(jobError);
  }, [jobError]);

  useEffect(() => {
    if (!normalizationJob) return;
    setProgress(Math.max(0, Math.min(100, Number(normalizationJob.progress || 0))));

    if (normalizationJob.status === "completed") {
      setRunning(false);
      setDone(true);
      setProgress(100);
        setStatusMessage(
          normalizeResult
          ? `Standardizasyon tamamlandı (Çalışma No: ${normalizeResult.normalization_run_id})`
          : "Standardizasyon tamamlandı",
        );
    }
    if (normalizationJob.status === "failed") {
      setRunning(false);
      setDone(false);
      setProgress(0);
      setErrorMessage(
        normalizationJob.error_message || "Standardizasyon sırasında bir hata oluştu",
      );
    }
    if (normalizationJob.status === "running") {
      setRunning(true);
    }
  }, [normalizationJob, normalizeResult]);

  if (uploadId === null) {
    return (
      <DashboardLayout>
        <Header
          title="Standardize Et"
          subtitle="Yüklediğiniz veriyi ortak bir formata getirip kullanıma hazır hale getirin"
        />
        <div className="flex-1 p-6 text-sm text-gray-600">
          Yükleme seçilmedi. Veri Yükleme sayfasına yönlendiriliyorsunuz…
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <Header
        title="Standardize Et"
        subtitle="Yüklediğiniz veriyi ortak bir formata getirip kullanıma hazır hale getirin"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="rounded bg-red-50 px-2 py-1 text-xs text-red-600">
                Sistem: Erişilemiyor
              </span>
            )}
            <button
              onClick={handleRun}
              disabled={running}
              className="flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-lg bg-red-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-60"
            >
              <i
                className={
                  running ? "ri-loader-4-line animate-spin" : "ri-play-line"
                }
              />
              {running ? "Hazırlanıyor..." : "Standardizasyonu Başlat"}
            </button>
          </div>
        }
      />

      <div className="flex-1 space-y-5 overflow-y-auto p-6">
        <FlowNav
          step="standardize"
          uploadId={uploadId}
          canGoNext={done}
        />

        <JobStatusBanner job={normalizationJob} />

        <div className="rounded-xl border border-gray-100 bg-white p-5">
          <h3 className="mb-1 text-sm font-semibold text-gray-900">
            İşlem Yapılacak Dosya
          </h3>
          <p className="mb-3 text-xs text-gray-400">
            Standardize edilecek dosyayı seçin. Önce veri yükleme adımını tamamlamış olmanız gerekir.
          </p>

          {loadingUploads ? (
            <p className="text-sm text-gray-400">Yüklemeler yükleniyor…</p>
          ) : uploads.length === 0 ? (
            <div className="flex items-start gap-3 rounded-xl border border-amber-100 bg-amber-50 p-4">
              <i className="ri-alert-line mt-0.5 flex-shrink-0 text-lg text-amber-500" />
              <div>
                <p className="text-sm font-medium text-amber-700">
                  Henüz yükleme yok
                </p>
                <p className="mt-0.5 text-xs text-amber-600">
                  Önce{" "}
                  <button
                    onClick={() => navigate("/veri-yukleme")}
                    className="cursor-pointer underline"
                  >
                    Veri Yükleme
                  </button>{" "}
                  sayfasından dosya yükleyin.
                </p>
              </div>
            </div>
          ) : (
            <select
              value={uploadId}
              onChange={(event) => {
                const value = event.target.value;
                const nextId = Number(value);
                if (!Number.isFinite(nextId) || nextId <= 0) return;
                setSearchParams(
                  (p) => {
                    p.set("upload_id", String(nextId));
                    return p;
                  },
                  { replace: true },
                );
                setDone(false);
                setNormalizeResult(null);
                setErrorMessage("");
                setStatusMessage("");
              }}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-100"
            >
              {uploads.map((upload) => (
                <option key={upload.id} value={upload.id}>
                  #{upload.id} — {upload.file_name} ({upload.total_records} kayıt
                  · {formatUploadStageLabel(upload.processing_stage, upload.status)})
                </option>
              ))}
            </select>
          )}
        </div>

        {uploadId > 0 && (
          <div className="rounded-xl border border-gray-100 bg-white p-5">
            <h3 className="mb-1 text-sm font-semibold text-gray-900">
              Alan Eşleştirme
            </h3>
            <p className="mb-3 text-xs text-gray-400">
              Dosyanızdaki alanları sistemde kullanılacak alanlarla eşleştirin. Uygun öneriler otomatik olarak doldurulmuştur.
            </p>

            {loadingColumns ? (
              <p className="text-sm text-gray-400">Kolonlar yükleniyor…</p>
            ) : sourceColumns.length === 0 ? (
              <p className="text-sm text-gray-400">
                Bu upload için ham kayıt bulunamadı.
              </p>
            ) : (
              <div className="max-h-64 space-y-2 overflow-y-auto">
                <div className="grid grid-cols-2 gap-2 border-b border-gray-100 px-1 pb-1 text-xs font-medium text-gray-500">
                  <span>Dosyadaki Alan</span>
                  <span>Sistemdeki Alan</span>
                </div>
                {sourceColumns.map((column) => (
                  <div
                    key={column}
                    className="grid grid-cols-2 items-center gap-2"
                  >
                    <span className="truncate rounded bg-gray-50 px-2 py-1.5 font-mono text-xs text-gray-700">
                      {column}
                    </span>
                    <select
                      value={columnMappings[column] ?? ""}
                      onChange={(event) =>
                        setColumnMappings((prev) => ({
                          ...prev,
                          [column]: event.target.value,
                        }))
                      }
                      className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs focus:border-red-400 focus:outline-none"
                    >
                      {TARGET_FIELD_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {errorMessage && (
          <div className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 p-4">
            <i className="ri-error-warning-fill text-lg text-red-600" />
            <p className="text-sm text-red-700">{errorMessage}</p>
          </div>
        )}

        {statusMessage && (
          <div className="flex items-center gap-3 rounded-xl border border-green-100 bg-green-50 p-4">
            <i className="ri-checkbox-circle-fill text-lg text-green-600" />
            <p className="text-sm text-green-700">{statusMessage}</p>
          </div>
        )}

        {(running || done) && (
          <div
            className={`flex items-center gap-4 rounded-xl border p-4 ${
              done
                ? "border-green-100 bg-green-50"
                : "border-red-100 bg-red-50"
            }`}
          >
            <div
              className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg ${
                done ? "bg-green-100" : "bg-red-100"
              }`}
            >
              <i
                className={`text-lg ${
                  done
                    ? "ri-checkbox-circle-fill text-green-600"
                    : "ri-loader-4-line animate-spin text-red-600"
                }`}
              />
            </div>
            <div className="flex-1">
              <p
                className={`text-sm font-semibold ${
                  done ? "text-green-700" : "text-red-700"
                }`}
              >
                {done
                  ? statusMessage
                  : `Standardize ediliyor... %${progress}`}
              </p>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/60">
                <div
                  className={`h-1.5 rounded-full transition-all duration-200 ${
                    done ? "bg-green-500" : "bg-red-500"
                  }`}
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {done && normalizeResult && (
          <div className="rounded-xl border border-green-100 bg-white p-5">
            <h3 className="mb-3 text-sm font-semibold text-gray-900">
              Sonraki Adım
            </h3>
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                {
                  label: "İşlenen Kayıt",
                  value: String(normalizeResult.total_processed),
                },
                {
                  label: "Başarılı",
                  value: String(normalizeResult.success_count),
                },
                {
                  label: "Hatalı",
                  value: String(normalizeResult.failed_count),
                },
                {
                  label: "Çalışma No",
                  value: String(normalizeResult.normalization_run_id),
                },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="rounded-lg bg-gray-50 p-3 text-center"
                >
                  <p className="text-base font-bold text-gray-900">
                    {stat.value}
                  </p>
                  <p className="mt-0.5 text-[10px] text-gray-400">
                    {stat.label}
                  </p>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() =>
                  navigate(
                    `/temiz-veri-seti?upload_id=${normalizeResult.upload_id}`,
                  )
                }
                className="flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-lg bg-red-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-red-700"
              >
                <i className="ri-table-line" /> Hazır Veriyi Gör
              </button>
              <button
                onClick={() =>
                  navigate(`/mukerrer-tespit?upload_id=${uploadId}`)
                }
                className="flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-lg border border-gray-200 px-5 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                <i className="ri-radar-line" /> Benzer Kayıtları Bul
              </button>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
