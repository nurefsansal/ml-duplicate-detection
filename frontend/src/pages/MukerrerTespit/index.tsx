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

/** Backend `minRulesToMatch`: 1–4 alan eşleşmesi gerekir (ad, TC, telefon, e-posta vb. kurallar). */
const MIN_RULES_DEFAULT = 3;

export default function MukerrerTespit() {
  const navigate = useNavigate();
  const [, setSearchParams] = useSearchParams();
  const uploadId = useRequireUploadId();
  const [minRulesToMatch, setMinRulesToMatch] = useState(MIN_RULES_DEFAULT);
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
        minRulesToMatch,
      });

      if (typeof result.jobId === "number") {
        setJobId(result.jobId);
        setStatusMessage(`Tespit başlatıldı (Job ID: ${result.jobId}). Arka planda işleniyor…`);
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
          ? `Tespit tamamlandı — ${groupCount} mükerrer grup, ${pairCount} çift, ${affected} etkilenen kayıt${
              typeof result.detectionRunId === "number"
                ? ` (Run #${result.detectionRunId})`
                : ""
            }`
          : `Tespit tamamlandı — mükerrer kayıt bulunamadı${
              typeof result.detectionRunId === "number"
                ? ` (Run #${result.detectionRunId})`
                : ""
            }`,
      );
    } catch (error: unknown) {
      const axiosDetail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErrorMessage(
        axiosDetail ||
          (error instanceof Error ? error.message : "Tespit sırasında hata oluştu."),
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
      setErrorMessage(detectionJob.error_message || "Tespit sırasında hata oluştu.");
      setProgress(0);
    }
    if (detectionJob.status === "completed") {
      setRunning(false);
      setProgress(100);
      setDone(true);
      setStatusMessage("Tespit tamamlandı. Sonuçlar listeleniyor…");
      const id = uploadId;
      if (id !== null) {
        navigate(`/mukerrer-kayitlar?upload_id=${id}`);
      }
    }
  }, [detectionJob, navigate, uploadId]);

  if (uploadId === null) {
    return (
      <DashboardLayout>
        <Header
          title="Mükerrer Tespit"
          subtitle="Standardize edilmiş kayıtlar üzerinden benzer kayıtları tespit edin"
        />
        <div className="flex-1 p-6 text-sm text-gray-600">
          Yükleme seçilmedi; Veri Yükleme sayfasına yönlendiriliyorsunuz…
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <Header
        title="Mükerrer Tespit"
        subtitle="Standardize edilmiş kayıtlar üzerinden benzer kayıtları tespit edin"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="rounded-lg border border-danger-200 bg-danger-50 px-2.5 py-1 text-xs font-medium text-danger-800">
                Backend: Erişilemiyor
              </span>
            )}
            <button
              onClick={handleStart}
              disabled={running}
              className="ui-btn-primary disabled:opacity-60"
            >
              <i className={running ? "ri-loader-4-line animate-spin" : "ri-radar-line"} />
              {running ? `Taranıyor... %${progress}` : "Tespiti Başlat"}
            </button>
          </div>
        }
      />

      <div className="flex-1 space-y-6 overflow-y-auto p-6 lg:p-8">
        <FlowNav
          step="detect"
          uploadId={uploadId}
        />

        <JobStatusBanner job={detectionJob} />

        {/* Upload selector */}
        <div className="ui-card p-6 shadow-card-lg">
          <h3 className="mb-3 text-sm font-semibold tracking-tight text-slate-900">
            Yükleme Seç (Standardize Edilmiş Veri)
          </h3>
          <p className="mb-3 text-xs text-gray-400">
            Tespit yapılacak standardize edilmiş veri setini seçin. Önce Veri Yükleme veya
            Veri Standardizasyon adımını tamamlamış olmanız gerekir.
          </p>

          {loadingUploads ? (
            <p className="text-sm text-gray-400">Yüklemeler yükleniyor…</p>
          ) : uploads.length === 0 ? (
            <div className="flex items-start gap-3 rounded-xl border border-amber-100 bg-amber-50 p-4">
              <i className="ri-alert-line text-lg text-amber-500 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-amber-700 font-medium">Standardize edilmiş yükleme yok</p>
                <p className="text-xs text-amber-600 mt-0.5">
                  Tespit yapabilmek için önce{" "}
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
                    Veri Standardizasyon
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
                    {u.latest_normalization_run_id ? `, Run #${u.latest_normalization_run_id}` : ""})
                  </option>
                ))}
              </select>

              {uploadId > 0 && (
                <p className="text-xs text-green-600">
                  <i className="ri-checkbox-circle-fill mr-1"></i>
                  Upload #{uploadId}
                  {selectedNormalizationRunId
                    ? ` · Standardizasyon Run #${selectedNormalizationRunId}`
                    : ""}{" "}
                  — tespit başlatılabilir.
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

        {/* Eşleşen kural sayısı — API'deki minRulesToMatch ile birebir */}
        <div className="ui-card p-6 shadow-card-lg">
          <h3 className="mb-2 text-sm font-semibold tracking-tight text-slate-900">
            Gerekli eşleşen kural sayısı
          </h3>
          <p className="mb-4 text-xs leading-relaxed text-slate-500">
            İki kaydın mükerrer adayı sayılması için tanımlı alan kurallarından (ör. ad, TC, telefon,
            e-posta) en az kaçının eşleşmesi gerektiğini seçin.{" "}
            <strong className="font-medium text-slate-700">Düşük</strong> değer daha çok aday üretir;{" "}
            <strong className="font-medium text-slate-700">yüksek</strong> değer daha seçici davranır.
            Bu ayar benzerlik yüzdesi değil; backend’deki <code className="rounded bg-slate-100 px-1 text-[11px]">minRulesToMatch</code>{" "}
            parametresidir (1–4).
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex h-14 min-w-[4rem] items-center justify-center rounded-xl border border-primary-200 bg-primary-50 px-4">
              <span className="text-3xl font-bold tabular-nums text-primary-800">{minRulesToMatch}</span>
            </div>
            <div className="min-w-0 flex-1">
              <input
                type="range"
                min={1}
                max={4}
                step={1}
                value={minRulesToMatch}
                onChange={(e) => setMinRulesToMatch(Number(e.target.value))}
                className="w-full cursor-pointer accent-primary-600"
              />
              <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                <span>1 — en geniş</span>
                <span>4 — en sıkı</span>
              </div>
            </div>
          </div>
        </div>

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
                label: "Mükerrer Grup",
                value: realResults.duplicateGroupCount ?? 0,
                icon: "ri-group-line",
                color: "text-primary-800",
                bg: "bg-primary-50",
              },
              {
                label: "Mükerrer Çift",
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
              onClick={() => navigate(`/yonetici-onayi?upload_id=${uploadId}`)}
              className="ui-btn-primary cursor-pointer whitespace-nowrap"
            >
              <i className="ri-checkbox-circle-line"></i> Yönetici Onayına Git
            </button>
            <button
              onClick={() => navigate(`/mukerrer-kayitlar?upload_id=${uploadId}`)}
              className="ui-btn-secondary cursor-pointer whitespace-nowrap"
            >
              <i className="ri-file-copy-2-line"></i> Mükerrer Kayıtları Gör
            </button>
          </div>
        )}

        {/* Results */}
        {done && results.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-card">
            <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/50 px-5 py-4">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Tespit Sonuçları</h3>
                <p className="mt-0.5 text-xs text-gray-400">{results.length} aday çift</p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50/70">
                    <th className="px-5 py-3 text-left font-medium text-gray-400">Grup</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Kayıt 1</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Kayıt 2</th>
                    <th className="px-4 py-3 text-center font-medium text-gray-400">Skor</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Karar</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Kaynak</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {results.map((pair) => {
                    const scoreColor =
                      pair.score >= 90
                        ? "border border-primary-200 bg-primary-50 text-primary-900"
                        : pair.score >= 80
                          ? "border border-amber-200 bg-amber-50 text-amber-900"
                          : "border border-slate-200 bg-slate-100 text-slate-800";
                    const decisionTypeLabel =
                      pair.finalDecision === "approved"
                        ? "Otomatik Onaylandı"
                        : pair.finalDecision === "rejected"
                          ? "Otomatik Reddedildi"
                          : "Manuel İnceleme";
                    return (
                      <tr key={pair.id} className="transition-colors hover:bg-gray-50/50">
                        <td className="px-5 py-3.5 font-medium text-gray-700">{pair.id}</td>
                        <td className="px-4 py-3.5">
                          <p className="font-medium text-gray-800">{pair.records[0].adSoyad}</p>
                          <p className="text-gray-400">
                            {pair.records[0].telefon || "-"} · {pair.records[0].email || "-"}
                          </p>
                        </td>
                        <td className="px-4 py-3.5">
                          <p className="font-medium text-gray-800">{pair.records[1].adSoyad}</p>
                          <p className="text-gray-400">
                            {pair.records[1].telefon || "-"} · {pair.records[1].email || "-"}
                          </p>
                        </td>
                        <td className="px-4 py-3.5 text-center">
                          <span className={`inline-block rounded-full px-2.5 py-1 text-sm font-bold ${scoreColor}`}>
                            %{pair.score.toFixed(1)}
                          </span>
                        </td>
                        <td className="px-4 py-3.5">
                          <span className={`inline-block rounded-full px-2.5 py-1 text-[11px] font-medium ${finalDecisionTone(pair.finalDecision)}`}>
                            {decisionTypeLabel}
                          </span>
                          <p className="mt-1 text-[11px] text-gray-400">
                            {pair.decisionReason || pair.ruleReasons[0] || "Ek açıklama yok"}
                          </p>
                        </td>
                        <td className="px-4 py-3.5 text-gray-500">
                          {pair.decisionSource === "splink_plus_rules" ? "Splink + kurallar" : pair.decisionSource}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {results.length === 0 && (
                <div className="py-10 text-center text-sm text-gray-400">
                  Bu filtreyle eşleşen kayıt bulunamadı.
                </div>
              )}
            </div>
          </div>
        )}

        {done && results.length === 0 && !errorMessage && (
          <div className="rounded-xl border border-gray-100 bg-white px-5 py-10 text-center">
            <i className="ri-checkbox-circle-line text-3xl text-green-500 mb-2 block"></i>
            <p className="text-sm font-medium text-gray-700">Mükerrer kayıt bulunamadı.</p>
            <p className="text-xs text-gray-400 mt-1">
              Seçili veri seti için gerekli kural sayısını düşürmeyi deneyin.
            </p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
