import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  startDetectionFromUpload,
  listUploads,
  type DetectResponse,
  type UploadItem,
} from "../../services/api";
import {
  finalDecisionTone,
  mapDetectPairToView,
  type UiDuplicatePair,
} from "../../utils/duplicatePairView";

const algorithms = [
  { id: "levenshtein", label: "Levenshtein", desc: "Karakter düzenleme mesafesi" },
  { id: "jaro", label: "Jaro-Winkler", desc: "Önek ağırlıklı benzerlik" },
  { id: "soundex", label: "Soundex", desc: "Fonetik eşleştirme" },
];

export default function MukerrerTespit() {
  const navigate = useNavigate();
  const [selectedAlgo, setSelectedAlgo] = useState<string[]>(["levenshtein", "jaro"]);
  const [threshold, setThreshold] = useState(75);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const [realResults, setRealResults] = useState<DetectResponse | null>(null);
  const [results, setResults] = useState<UiDuplicatePair[]>([]);

  // Upload selection
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [loadingUploads, setLoadingUploads] = useState(false);
  const [selectedUploadId, setSelectedUploadId] = useState<number | "">(() => {
    const stored = localStorage.getItem("lastUploadId");
    return stored ? Number(stored) : "";
  });
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
    setLoadingUploads(true);
    listUploads(50, { hasNormalizedRecords: true })
      .then((d) => {
        const list = d.uploads ?? [];
        setUploads(list);
        // Auto-select from localStorage only if that upload is in the filtered list
        const storedId = localStorage.getItem("lastUploadId");
        if (storedId) {
          const found = list.find((u) => u.id === Number(storedId));
          if (found) {
            setSelectedUploadId(found.id);
            setSelectedNormalizationRunId(found.latest_normalization_run_id ?? null);
          } else {
            setSelectedUploadId("");
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoadingUploads(false));
  }, []);

  const toggleAlgo = (id: string) => {
    setSelectedAlgo((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  const handleStart = async () => {
    if (selectedUploadId === "") {
      setErrorMessage("Lütfen tespit yapılacak bir yükleme seçin.");
      return;
    }

    setRunning(true);
    setDone(false);
    setProgress(0);
    setErrorMessage("");
    setStatusMessage("");
    setRealResults(null);
    setResults([]);

    const progressInterval = window.setInterval(() => {
      setProgress((value) => Math.min(value + Math.floor(Math.random() * 5) + 1, 85));
    }, 400);

    try {
      const result = await startDetectionFromUpload(selectedUploadId, {
        normalizationRunId: selectedNormalizationRunId,
        minRulesToMatch: Math.ceil((threshold / 100) * 4),
      });

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

  return (
    <DashboardLayout>
      <Header
        title="Mükerrer Tespit"
        subtitle="Normalize edilmiş kayıtlar üzerinden benzer kayıtları tespit edin"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="rounded bg-red-50 px-2 py-1 text-xs text-red-600">
                Backend: Erişilemiyor
              </span>
            )}
            <button
              onClick={handleStart}
              disabled={running || selectedUploadId === ""}
              className="flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-lg bg-red-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-60"
            >
              <i className={running ? "ri-loader-4-line animate-spin" : "ri-radar-line"} />
              {running ? `Taranıyor... %${progress}` : "Tespiti Başlat"}
            </button>
          </div>
        }
      />

      <div className="flex-1 space-y-5 overflow-y-auto p-6">
        {/* Upload selector */}
        <div className="rounded-xl border border-gray-100 bg-white p-5">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">
            Yükleme Seç (Normalize Edilmiş Veri)
          </h3>
          <p className="mb-3 text-xs text-gray-400">
            Tespit yapılacak normalize edilmiş veri setini seçin. Önce Veri Yükleme veya
            Veri Normalizasyon adımını tamamlamış olmanız gerekir.
          </p>

          {loadingUploads ? (
            <p className="text-sm text-gray-400">Yüklemeler yükleniyor…</p>
          ) : uploads.length === 0 ? (
            <div className="flex items-start gap-3 rounded-xl border border-amber-100 bg-amber-50 p-4">
              <i className="ri-alert-line text-lg text-amber-500 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-amber-700 font-medium">Normalize edilmiş yükleme yok</p>
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
                    onClick={() => navigate("/veri-normalizasyon")}
                    className="underline cursor-pointer"
                  >
                    Veri Normalizasyon
                  </button>{" "}
                  adımlarını tamamlayın.
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <select
                value={selectedUploadId}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === "") {
                    setSelectedUploadId("");
                    setSelectedNormalizationRunId(null);
                  } else {
                    const numId = Number(v);
                    setSelectedUploadId(numId);
                    const found = uploads.find((u) => u.id === numId);
                    setSelectedNormalizationRunId(found?.latest_normalization_run_id ?? null);
                  }
                }}
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:border-red-400 focus:ring-1 focus:ring-red-100"
              >
                <option value="">— Normalize edilmiş yükleme seçin —</option>
                {uploads.map((u) => (
                  <option key={u.id} value={u.id}>
                    #{u.id} — {u.file_name} ({u.total_records} kayıt
                    {u.latest_normalization_run_id ? `, Run #${u.latest_normalization_run_id}` : ""})
                  </option>
                ))}
              </select>

              {selectedUploadId !== "" && (
                <p className="text-xs text-green-600">
                  <i className="ri-checkbox-circle-fill mr-1"></i>
                  Upload #{selectedUploadId}
                  {selectedNormalizationRunId
                    ? ` · Normalizasyon Run #${selectedNormalizationRunId}`
                    : ""}{" "}
                  — tespit başlatılabilir.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Error / Status */}
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

        {/* Algorithm + threshold */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <div className="rounded-xl border border-gray-100 bg-white p-5 lg:col-span-2">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Algoritma Seçimi</h3>
            <div className="grid grid-cols-3 gap-3">
              {algorithms.map((algorithm) => {
                const active = selectedAlgo.includes(algorithm.id);
                return (
                  <button
                    key={algorithm.id}
                    onClick={() => toggleAlgo(algorithm.id)}
                    className={`cursor-pointer rounded-xl border-2 p-4 text-left transition-all ${
                      active ? "border-red-500 bg-red-50" : "border-gray-100 hover:border-gray-200"
                    }`}
                  >
                    <div className={`mb-2 flex h-8 w-8 items-center justify-center rounded-lg ${active ? "bg-red-100" : "bg-gray-100"}`}>
                      <i className={`ri-cpu-line text-base ${active ? "text-red-600" : "text-gray-400"}`} />
                    </div>
                    <p className={`text-sm font-semibold ${active ? "text-red-700" : "text-gray-700"}`}>
                      {algorithm.label}
                    </p>
                    <p className="mt-0.5 text-xs text-gray-400">{algorithm.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="rounded-xl border border-gray-100 bg-white p-5">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Benzerlik Eşiği</h3>
            <div className="mb-4 text-center">
              <span className="text-4xl font-bold text-red-600">%{threshold}</span>
              <p className="mt-1 text-xs text-gray-400">ve üzeri olasılıklar öne çıkarılacak</p>
            </div>
            <input
              type="range"
              min={50}
              max={100}
              value={threshold}
              onChange={(event) => setThreshold(Number(event.target.value))}
              className="w-full cursor-pointer accent-red-600"
            />
            <div className="mt-1 flex justify-between text-[10px] text-gray-400">
              <span>%50 Geniş</span>
              <span>%100 Tam</span>
            </div>
          </div>
        </div>

        {/* Progress */}
        {(running || done) && (
          <div className={`flex items-center gap-4 rounded-xl border p-4 ${done ? "border-green-100 bg-green-50" : "border-red-100 bg-red-50"}`}>
            <div className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg ${done ? "bg-green-100" : "bg-red-100"}`}>
              <i className={`text-lg ${done ? "ri-checkbox-circle-fill text-green-600" : "ri-loader-4-line animate-spin text-red-600"}`} />
            </div>
            <div className="flex-1">
              <p className={`text-sm font-semibold ${done ? "text-green-700" : "text-red-700"}`}>
                {done
                  ? statusMessage
                  : `${realResults?.totalRecords || "Veri"} taranıyor... %${progress}`}
              </p>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/70">
                <div
                  className={`h-1.5 rounded-full transition-all duration-150 ${done ? "bg-green-500" : "bg-red-500"}`}
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
                color: "text-red-600",
                bg: "bg-red-50",
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
              onClick={() => navigate("/yonetici-onayi")}
              className="flex items-center gap-2 bg-red-600 text-white text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-red-700 cursor-pointer transition-colors whitespace-nowrap"
            >
              <i className="ri-checkbox-circle-line"></i> Yönetici Onayına Git
            </button>
            <button
              onClick={() => navigate("/mukerrer-kayitlar")}
              className="flex items-center gap-2 border border-gray-200 text-gray-700 text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors whitespace-nowrap"
            >
              <i className="ri-file-copy-2-line"></i> Mükerrer Kayıtları Gör
            </button>
          </div>
        )}

        {/* Results */}
        {done && results.length > 0 && (
          <div className="rounded-xl border border-gray-100 bg-white">
            <div className="flex items-center justify-between border-b border-gray-50 px-5 py-4">
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
                        ? "bg-red-50 text-red-600"
                        : pair.score >= 80
                          ? "bg-orange-50 text-orange-500"
                          : "bg-yellow-50 text-yellow-600";
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
                            {pair.finalDecisionLabel}
                          </span>
                          <p className="mt-1 text-[11px] text-gray-400">
                            {pair.ruleReasons[0] || "Ek açıklama yok"}
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
            <p className="text-xs text-gray-400 mt-1">Seçili veri seti için eşik değerini düşürmeyi deneyin.</p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
