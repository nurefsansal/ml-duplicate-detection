import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import DropZone from "./components/DropZone";
import SourceSelector from "./components/SourceSelector";
import UploadProgress from "./components/UploadProgress";
import UploadHistoryTable from "./components/UploadHistoryTable";
import {
  type UploadFileResponse,
  uploadFileOnly,
  healthCheck,
} from "../../services/api";
import InstitutionDbConnectorPanel from "../../components/feature/InstitutionDbConnectorPanel";
import { useJobPolling } from "../../hooks/useJobPolling";
import { JobStatusBanner } from "../../components/feature/JobStatusBanner";
import { FlowNav } from "../../components/feature/FlowNav";
import { formatUploadIdWithDate } from "../../utils/formatUploadDate";

type SourceType = "excel" | "csv" | "api" | "institution";

function formatSourceLabel(source: string): string {
  const value = source.toLowerCase();
  if (value === "excel") return "Excel";
  if (value === "csv") return "CSV";
  if (value === "api") return "API";
  if (value === "institution") return "Kurum Veritabanı";
  return source;
}

export default function VeriYukleme() {
  const navigate = useNavigate();
  const [source, setSource] = useState<SourceType>("excel");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState("");
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<UploadFileResponse | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  useEffect(() => {
    let mounted = true;
    healthCheck()
      .then(() => { if (mounted) setBackendHealthy(true); })
      .catch(() => { if (mounted) setBackendHealthy(false); });
    return () => { mounted = false; };
  }, []);

  const getError = (error: unknown) => {
    if (typeof error === "object" && error && "response" in error) {
      const resp = (error as { response?: { data?: { detail?: string } } }).response;
      if (resp?.data?.detail) return resp.data.detail;
    }
    if (error instanceof Error) return error.message;
    return "Bilinmeyen bir hata oluştu";
  };

  const handleFileSelect = async (file: File) => {
    setFileName(file.name);
    setProgress(0);
    setUploading(true);
    setErrorMessage("");
    setStatusMessage("");
    setResult(null);
    setJobId(null);

    try {
      const response = await uploadFileOnly(file);
      setResult(response);
      setJobId(typeof response.job_id === "number" ? response.job_id : null);

      if (typeof response.upload_id === "number") {
        localStorage.setItem("lastUploadId", String(response.upload_id));
      }

      if (response.job_id) {
        setStatusMessage(`Yükleme başlatıldı (İş No: ${response.job_id}). Arka planda sürüyor…`);
      } else {
        setStatusMessage(`Yükleme başlatıldı. Arka planda sürüyor…`);
      }
    } catch (error) {
      setErrorMessage(getError(error));
      setProgress(0);
    } finally {
      // uploading state will be finalized when job completes (polling).
    }
  };

  const handleCancel = () => {
    setUploading(false);
    setProgress(0);
    setFileName("");
    setJobId(null);
  };

  const { job: uploadJob, error: jobError } = useJobPolling(jobId);

  useEffect(() => {
    if (jobError) {
      setErrorMessage(jobError);
    }
  }, [jobError]);

  useEffect(() => {
    if (!uploadJob) return;
    setProgress(Math.max(0, Math.min(100, Number(uploadJob.progress || 0))));

    if (uploadJob.status === "completed") {
      setUploading(false);
      setProgress(100);
      const uploadId = result?.upload_id;
        setStatusMessage(
          uploadId
            ? `Yükleme tamamlandı. İlk kayıtlar hazır (Yükleme No: ${uploadId}).`
            : "Yükleme tamamlandı. İlk kayıtlar hazır.",
        );
    }
    if (uploadJob.status === "failed") {
      setUploading(false);
      setErrorMessage(uploadJob.error_message || "Yükleme sırasında hata oluştu");
      setProgress(0);
    }
  }, [uploadJob, result?.upload_id]);

  return (
    <DashboardLayout>
      <Header
        title="Veri Yükleme"
        subtitle="Excel veya CSV dosyanızı ekleyin, ilk kayıtlar sisteme alınsın"
        actions={
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-xs font-medium text-slate-600 shadow-sm">
            <i className="ri-information-line text-sm text-primary-600" />
            <span>Maks. 100 MB &bull; .xlsx .csv destekleniyor</span>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        <FlowNav
          step="upload"
          uploadId={result?.upload_id ?? null}
          canGoNext={uploadJob?.status === "completed" || !jobId}
        />

        {/* Stat cards */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="ui-card p-5">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Sistem Durumu</p>
            <p
              className={`mt-1 text-sm font-semibold ${
                backendHealthy
                  ? "text-emerald-600"
                  : backendHealthy === false
                    ? "text-danger-700"
                    : "text-slate-400"
              }`}
            >
              {backendHealthy === null ? "Kontrol ediliyor…" : backendHealthy ? "Bağlantı aktif" : "Erişilemiyor"}
            </p>
          </div>
          <div className="ui-card p-5">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Yüklenen Ham Kayıt</p>
            <p className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-slate-900">
              {result ? result.total_records : 0}
            </p>
          </div>
          <div className="ui-card p-5">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Yükleme No</p>
            <p className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-slate-900">
              {result?.upload_id
                ? formatUploadIdWithDate(result.upload_id, new Date().toISOString())
                : "—"}
            </p>
          </div>
        </div>

        {/* Info banner: this page does NOT run normalization */}
        <div className="flex items-start gap-3 rounded-2xl border border-primary-200/80 bg-gradient-to-r from-primary-50/90 to-indigo-50/70 p-4 shadow-sm">
          <i className="ri-information-line mt-0.5 flex-shrink-0 text-lg text-primary-600" />
          <div>
              <p className="text-sm font-semibold text-primary-950">Bu adımda yalnızca ilk veri alınır</p>
              <p className="mt-0.5 text-xs font-medium text-primary-900/80">
                Dosyanız sisteme kaydedilir. Standardizasyon ve mükerrer tespit adımları
                bir sonraki ekranda devam eder.
              </p>
          </div>
        </div>

        <JobStatusBanner job={uploadJob} />

        {statusMessage && (
          <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            {statusMessage}
          </div>
        )}
        {errorMessage && (
          <div className="rounded-2xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm font-medium text-danger-800 shadow-sm">
            {errorMessage}
          </div>
        )}

        {/* Source selector */}
        <div className="bg-white rounded-xl p-5 border border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900 mb-1">Veri Kaynağını Seçin</h3>
          <p className="text-xs text-gray-400 mb-4">Dosyanızı veya bağlantı tipini buradan belirleyin</p>
          <SourceSelector selected={source} onChange={setSource} />
        </div>

        {/* File upload */}
        {(source === "excel" || source === "csv") && (
          <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">
                {source === "excel" ? "Excel Dosyası Ekleyin" : "CSV Dosyası Ekleyin"}
              </h3>
            {!uploading ? (
              <DropZone onFileSelect={handleFileSelect} />
            ) : (
              <UploadProgress
                progress={Math.min(progress, 100)}
                fileName={fileName}
                onCancel={handleCancel}
              />
            )}
          </div>
        )}

        {/* API source: info banner */}
        {source === "api" && (
          <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">API Bağlantısı</h3>
            <div className="flex items-start gap-3 rounded-xl border border-blue-100 bg-blue-50 p-4">
              <i className="ri-information-line text-lg text-blue-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-blue-700">
                API üzerinden doğrudan veri alma özelliği şu anda kapalı. Verinizi önce Excel
                veya CSV olarak dışa aktarabilir, ardından bu ekrandan yükleyebilirsiniz.
              </p>
            </div>
          </div>
        )}

        {source === "institution" && (
          <div className="bg-white rounded-xl p-5 border border-gray-100">
            <InstitutionDbConnectorPanel
              showImport
              onImported={(data) => {
                setResult({
                  upload_id: data.upload_id,
                  total_records: data.total_records,
                  source_columns: [],
                  source_type: "institution",
                  file_name: data.source ?? "kurum-db",
                } as unknown as UploadFileResponse);
                localStorage.setItem("lastUploadId", String(data.upload_id));
                setStatusMessage(
                  `İçe aktarma tamamlandı. ${data.total_records} kayıt alındı (Yükleme No: ${data.upload_id}).`,
                );
                setErrorMessage("");
              }}
            />
          </div>
        )}

        {/* Success actions */}
        {result && (
          <div className="bg-white rounded-xl p-5 border border-green-100">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Yükleme Tamamlandı</h3>

            {/* Source columns */}
            {result.source_columns.length > 0 && (
              <div className="mb-4 p-3 bg-gray-50 rounded-lg">
                <p className="text-xs font-medium text-gray-600 mb-2">
                  Dosyada bulunan alanlar ({result.source_columns.length}):
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {result.source_columns.map((col) => (
                    <span
                      key={col}
                      className="inline-block px-2 py-0.5 bg-white border border-gray-200 rounded text-xs text-gray-700 font-mono"
                    >
                      {col}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              {[
                {
                  label: "Yükleme No",
                  value: formatUploadIdWithDate(result.upload_id!, new Date().toISOString()),
                },
                { label: "Toplam Kayıt", value: String(result.total_records) },
                { label: "Kaynak", value: formatSourceLabel(result.source_type) },
                { label: "Kolon Sayısı", value: String(result.source_columns.length) },
              ].map((s) => (
                <div key={s.label} className="bg-gray-50 rounded-lg p-3 text-center">
                  <p className="text-base font-bold text-gray-900">{s.value}</p>
                  <p className="text-[10px] text-gray-400 mt-0.5">{s.label}</p>
                </div>
              ))}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => navigate(`/veri-normalizasyon?upload_id=${result.upload_id}`)}
                className="ui-btn-primary cursor-pointer whitespace-nowrap"
              >
                <i className="ri-filter-3-line"></i> Standardize Et
              </button>
              <button
                onClick={() => navigate(`/ham-veri?upload_id=${result.upload_id}`)}
                className="flex items-center gap-2 border border-gray-200 text-gray-700 text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors whitespace-nowrap"
              >
                <i className="ri-table-line"></i> Yüklenen Veriyi Gör
              </button>
            </div>
          </div>
        )}

        <UploadHistoryTable />
      </div>
    </DashboardLayout>
  );
}
