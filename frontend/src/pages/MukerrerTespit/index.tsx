import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useRequireUploadId } from "../../hooks/useRequireUploadId";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  startDetectionFromUpload,
  listUploads,
  type DetectResponse,
  type UploadItem,
} from "../../services/api";
import { useJobPolling } from "../../hooks/useJobPolling";
import { JobStatusBanner } from "../../components/feature/JobStatusBanner";
import { FlowNav } from "../../components/feature/FlowNav";
import {
  finalDecisionTone,
  mapDetectPairToView,
  type UiDuplicatePair,
} from "../../utils/duplicatePairView";

export default function MukerrerTespit() {
  const navigate = useNavigate();
  const [, setSearchParams] = useSearchParams();
  const uploadId = useRequireUploadId();
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const [realResults, setRealResults] = useState<DetectResponse | null>(null);
  const [results, setResults] = useState<UiDuplicatePair[]>([]);
  const [jobId, setJobId] = useState<number | null>(null);
  // Upload selection
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [loadingUploads, setLoadingUploads] = useState(false);
  // Tracks the latest_normalization_run_id of the currently selected upload
  const [selectedNormalizationRunId, setSelectedNormalizationRunId] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    import("../../services/api")
      .then(({ healthCheck }) => healthCheck())
      .then(() => { if (mounted) setBackendHealthy(true); })
      .catch(() => { if (mounted) setBackendHealthy(false); });
    return () => { mounted = false; };
  }, []);

  // Fetch only uploads that have normalized_records — avoids showing incomplete uploads
  useEffect(() => {
    if (uploadId === null) return;
    setLoadingUploads(true);
    listUploads(50, { hasNormalizedRecords: true })
      .then((d) => {
        const list = d.uploads ?? [];
        setUploads(list);
        const found = list.find((u) => u.id === uploadId);
        setSelectedNormalizationRunId(found?.latest_normalization_run_id ?? null);
      })
      .catch(() => {})
      .finally(() => setLoadingUploads(false));
  }, [uploadId]);

  const handleStart = async () => {
    if (uploadId === null) return;

    setRunning(true);
    setDone(false);
    setProgress(0);
    setErrorMessage("");
    setStatusMessage("");
    setRealResults(null);
    setResults([]);
    setJobId(null);

    const progressInterval = window.setInterval(() => {
      setProgress((value) => {
        if (value >= 85) {
          return value;
        }
        if (value === 0) {
          return 10;
        }
        return Math.min(value + 8, 85);
      });
    }, 400);

    try {
      const result = await startDetectionFromUpload(uploadId, {
        normalizationRunId: selectedNormalizationRunId,
      });

      if (typeof result.jobId === "number") {
        setJobId(result.jobId);
        setStatusMessage(`Tarama başlatıldı (İş No: ${result.jobId}). Arka planda sürüyor…`);
        setProgress(5);
        return;
      }

      if (typeof result.uploadId === "number") {
        localStorage.setItem("lastDetectUploadId", String(result.uploadId));
      }
      if (typeof result.detectionRunId === "number") {
        localStorage.setItem("lastDetectionRunId", String(result.detectionRunId));
      }

      setRealResults(result);
      const views = (result.duplicates || []).map(mapDetectPairToView);
      setResults(views);
      setProgress(100);
      setDone(true);

      const groupCount = result.duplicateGroupCount ?? 0;
      const pairCount = result.duplicatePairs ?? 0;
      const affected = result.affectedRecordCount ?? 0;
      setStatusMessage(
        groupCount > 0
          ? `Tarama tamamlandı. ${groupCount} benzer grup, ${pairCount} aday çift ve ${affected} etkilenen kayıt bulundu${
              typeof result.detectionRunId === "number"
                ? ` (Çalışma No: ${result.detectionRunId})`
                : ""
            }`
          : `Tarama tamamlandı. Benzer kayıt bulunamadı${
              typeof result.detectionRunId === "number"
                ? ` (Çalışma No: ${result.detectionRunId})`
                : ""
            }`,
      );
    } catch (error: unknown) {
      const axiosDetail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErrorMessage(
        axiosDetail ||
          (error instanceof Error ? error.message : "Tarama sırasında bir hata oluştu."),
      );
      setProgress(0);
    } finally {
      clearInterval(progressInterval);
      setRunning(false);
    }
  };

  const { job: detectionJob, error: jobError } = useJobPolling(jobId);

  useEffect(() => {
    if (jobError) setErrorMessage(jobError);
  }, [jobError]);

  useEffect(() => {
    if (!detectionJob) return;
    setProgress(Math.max(0, Math.min(100, Number(detectionJob.progress || 0))));
    if (detectionJob.status === "running") setRunning(true);
    if (detectionJob.status === "failed") {
      setRunning(false);
      setErrorMessage(detectionJob.error_message || "Tarama sırasında bir hata oluştu.");
      setProgress(0);
    }
    if (detectionJob.status === "completed") {
      setRunning(false);
      setProgress(100);
      setDone(true);
      setStatusMessage("Tarama tamamlandı. Sonuçlar hazırlanıyor…");
      const id = uploadId;
      if (id !== null) {
        navigate(`/mukerrer-kayitlar?upload_id=${id}&decision=pending`);
      }
    }
  }, [detectionJob, navigate, uploadId]);

  if (uploadId === null) {
    return (
      <DashboardLayout>
        <Header
          title="Benzer Kayıtları Bul"
          subtitle="Hazırlanan veriler içinde benzer görünen kayıtları tarayın"
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
        title="Benzer Kayıtları Bul"
        subtitle="Hazırlanan veriler içinde benzer görünen kayıtları tarayın"
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2 sm:gap-3">
            {backendHealthy === false && (
              <span className="rounded-lg border border-danger-200 bg-danger-50 px-2.5 py-1 text-xs font-medium text-danger-800">
                Sistem: Erişilemiyor
              </span>
            )}
            <button
              onClick={handleStart}
              disabled={running}
              className="ui-btn-primary disabled:opacity-60"
            >
              <i className={running ? "ri-loader-4-line animate-spin" : "ri-radar-line"} />
              {running ? `Taranıyor... %${progress}` : "Taramayı Başlat"}
            </button>
          </div>
        }
      />

      <div className="flex-1 space-y-6 overflow-y-auto p-6 lg:p-8">
        <FlowNav
          step="detect"
          uploadId={uploadId}
          canGoNext={done}
        />

        <JobStatusBanner job={detectionJob} />

        {/* Upload selector */}
        <div className="ui-card p-6 shadow-card-lg">
          <h3 className="mb-3 text-sm font-semibold tracking-tight text-slate-900">
            İşlem Yapılacak Veri
          </h3>
          <p className="mb-3 text-xs text-gray-400">
            Tarama yapılacak veri setini seçin. Önce veri yükleme ve standardizasyon adımlarını tamamlamış olmanız gerekir.
          </p>

          {loadingUploads ? (
            <p className="text-sm text-gray-400">Yüklemeler yükleniyor…</p>
          ) : uploads.length === 0 ? (
            <div className="flex items-start gap-3 rounded-xl border border-amber-100 bg-amber-50 p-4">
              <i className="ri-alert-line text-lg text-amber-500 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-amber-700 font-medium">Hazır veri bulunamadı</p>
                <p className="text-xs text-amber-600 mt-0.5">
                  Tarama yapabilmek için önce{" "}
                  <button
                    onClick={() => navigate("/veri-yukleme")}
                    className="underline cursor-pointer"
                  >
                    Veri Yükleme
                  </button>{" "}
                  ve ardından{" "}
                  <button
                    onClick={() =>
                      navigate(`/veri-normalizasyon?upload_id=${uploadId}`)
                    }
                    className="underline cursor-pointer"
                  >
                    Standardize Et
                  </button>{" "}
                  adımlarını tamamlayın.
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <select
                value={uploadId}
                onChange={(e) => {
                  const numId = Number(e.target.value);
                  if (!Number.isFinite(numId) || numId <= 0) return;
                  setSearchParams(
                    (p) => {
                      p.set("upload_id", String(numId));
                      return p;
                    },
                    { replace: true },
                  );
                  const found = uploads.find((u) => u.id === numId);
                  setSelectedNormalizationRunId(found?.latest_normalization_run_id ?? null);
                }}
                className="ui-focus-ring w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm"
              >
                {uploads.map((u) => (
                  <option key={u.id} value={u.id}>
                    #{u.id} — {u.file_name} ({u.total_records} kayıt
                    {u.latest_normalization_run_id ? `, Çalışma #${u.latest_normalization_run_id}` : ""})
                  </option>
                ))}
              </select>

              {uploadId > 0 && (
                <p className="text-xs text-green-600">
                  <i className="ri-checkbox-circle-fill mr-1"></i>
                  Yükleme #{uploadId}
                  {selectedNormalizationRunId
                    ? ` · Standardizasyon Çalışması #${selectedNormalizationRunId}`
                    : ""}{" "}
                  — taramaya hazır.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Error / Status */}
        {errorMessage && (
          <div className="flex items-center gap-3 rounded-2xl border border-danger-200 bg-danger-50 p-4 shadow-sm">
            <i className="ri-error-warning-fill text-lg text-danger-700" />
            <p className="text-sm font-medium text-danger-800">{errorMessage}</p>
          </div>
        )}

        {statusMessage && (
          <div className="flex items-center gap-3 rounded-xl border border-green-100 bg-green-50 p-4">
            <i className="ri-checkbox-circle-fill text-lg text-green-600" />
            <p className="text-sm text-green-700">{statusMessage}</p>
          </div>
        )}

        {/* Progress */}
        {(running || done) && (
          <div
            className={`flex items-center gap-4 rounded-2xl border p-4 shadow-sm ${
              done ? "border-emerald-200 bg-emerald-50" : "border-primary-200 bg-primary-50"
            }`}
          >
            <div
              className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl ${
                done ? "bg-emerald-100" : "bg-primary-100"
              }`}
            >
              <i
                className={`text-lg ${done ? "ri-checkbox-circle-fill text-emerald-600" : "ri-loader-4-line animate-spin text-primary-700"}`}
              />
            </div>
            <div className="flex-1">
              <p className={`text-sm font-semibold ${done ? "text-emerald-900" : "text-primary-900"}`}>
                {done
                  ? statusMessage
                  : `${realResults?.totalRecords || "Veri"} taranıyor... %${progress}`}
              </p>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/70">
                <div
                  className={`h-1.5 rounded-full transition-all duration-150 ${done ? "bg-emerald-500" : "bg-gradient-to-r from-primary-500 to-indigo-500"}`}
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Post-detection summary stats */}
        {done && realResults && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              {
                label: "Toplam Kayıt",
                value: realResults.totalRecords ?? 0,
                icon: "ri-database-2-line",
                color: "text-gray-600",
                bg: "bg-gray-50",
              },
              {
                label: "Benzer Grup",
                value: realResults.duplicateGroupCount ?? 0,
                icon: "ri-group-line",
                color: "text-primary-800",
                bg: "bg-primary-50",
              },
              {
                label: "Aday Çift",
                value: realResults.duplicatePairs ?? 0,
                icon: "ri-links-line",
                color: "text-orange-600",
                bg: "bg-orange-50",
              },
              {
                label: "Etkilenen Kayıt",
                value: realResults.affectedRecordCount ?? 0,
                icon: "ri-user-line",
                color: "text-amber-600",
                bg: "bg-amber-50",
              },
            ].map(({ label, value, icon, color, bg }) => (
              <div key={label} className={`rounded-xl border border-gray-100 ${bg} p-4`}>
                <div className="flex items-center gap-2 mb-1">
                  <i className={`${icon} ${color} text-base`} />
                  <p className="text-xs text-gray-500">{label}</p>
                </div>
                <p className={`text-2xl font-bold ${color}`}>{value.toLocaleString("tr-TR")}</p>
              </div>
            ))}
          </div>
        )}

        {/* Post-detection actions */}
        {done && (
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => navigate(`/mukerrer-kayitlar?upload_id=${uploadId}&decision=pending`)}
              className="ui-btn-primary cursor-pointer whitespace-nowrap"
            >
              <i className="ri-file-copy-2-line"></i> İnceleme Ekranına Git
            </button>
          </div>
        )}

        {done && results.length === 0 && !errorMessage && (
          <div className="rounded-xl border border-gray-100 bg-white px-5 py-10 text-center">
            <i className="ri-checkbox-circle-line text-3xl text-green-500 mb-2 block"></i>
            <p className="text-sm font-medium text-gray-700">Mükerrer kayıt bulunamadı.</p>
            <p className="text-xs text-gray-400 mt-1">Farklı bir veri seti seçerek veya standardizasyonu kontrol ederek tekrar deneyin.</p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
