import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { normalizationRules, type NormalizationRule } from "../../mocks/records";
import {
  listUploads,
  getUploadColumns,
  saveColumnMappings,
  startNormalizationRun,
  type UploadItem,
  type NormalizationRunResponse,
  type ColumnMappingItem,
} from "../../services/api";

const categoryColors: Record<string, string> = {
  metin: "bg-blue-50 text-blue-600",
  karakter: "bg-purple-50 text-purple-600",
  format: "bg-orange-50 text-orange-600",
  dogrulama: "bg-green-50 text-green-600",
  adres: "bg-yellow-50 text-yellow-700",
};

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

export default function VeriNormalizasyon() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [rules, setRules] = useState<NormalizationRule[]>(normalizationRules);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [normalizeResult, setNormalizeResult] = useState<NormalizationRunResponse | null>(null);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);

  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [loadingUploads, setLoadingUploads] = useState(false);

  const urlUploadId = searchParams.get("upload_id");
  const [selectedUploadId, setSelectedUploadId] = useState<number | "">(() => {
    if (urlUploadId) return Number(urlUploadId);
    const stored = localStorage.getItem("lastUploadId");
    return stored ? Number(stored) : "";
  });

  const [sourceColumns, setSourceColumns] = useState<string[]>([]);
  const [suggestedMappings, setSuggestedMappings] = useState<Record<string, string>>({});
  const [columnMappings, setColumnMappings] = useState<Record<string, string>>({});
  const [loadingColumns, setLoadingColumns] = useState(false);

  useEffect(() => {
    let mounted = true;
    import("../../services/api")
      .then(({ healthCheck }) => healthCheck())
      .then(() => { if (mounted) setBackendHealthy(true); })
      .catch(() => { if (mounted) setBackendHealthy(false); });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    setLoadingUploads(true);
    listUploads(50)
      .then((d) => setUploads(d.uploads ?? []))
      .catch(() => {})
      .finally(() => setLoadingUploads(false));
  }, []);

  useEffect(() => {
    if (selectedUploadId === "") {
      setSourceColumns([]);
      setSuggestedMappings({});
      setColumnMappings({});
      return;
    }
    setLoadingColumns(true);
    getUploadColumns(selectedUploadId)
      .then((data) => {
        setSourceColumns(data.source_columns ?? []);
        setSuggestedMappings(data.suggested_mappings ?? {});
        const initial: Record<string, string> = {};
        for (const col of data.source_columns ?? []) {
          initial[col] = data.suggested_mappings?.[col] ?? "";
        }
        setColumnMappings(initial);
      })
      .catch(() => {})
      .finally(() => setLoadingColumns(false));
  }, [selectedUploadId]);

  const toggleRule = (id: number) => {
    setRules((prev) => prev.map((r) => (r.id === id ? { ...r, active: !r.active } : r)));
  };

  const handleRun = async () => {
    if (selectedUploadId === "") {
      setErrorMessage("Lütfen normalizasyon yapılacak bir yükleme seçin");
      return;
    }

    setRunning(true);
    setDone(false);
    setProgress(0);
    setErrorMessage("");
    setStatusMessage("");
    setNormalizeResult(null);

    const progressInterval = setInterval(() => {
      setProgress((p) => Math.min(p + Math.floor(Math.random() * 15) + 5, 90));
    }, 200);

    const mappingItems: ColumnMappingItem[] = Object.entries(columnMappings)
      .filter(([, target]) => target && target !== "other")
      .map(([source_column, target_field]) => ({ source_column, target_field }));

    try {
      if (mappingItems.length > 0) {
        try {
          await saveColumnMappings(selectedUploadId, mappingItems);
        } catch {
          clearInterval(progressInterval);
          setRunning(false);
          setErrorMessage("Kolon eşleştirmeleri kaydedilemedi. Lütfen tekrar deneyin.");
          return;
        }
      }

      const result = await startNormalizationRun(
        selectedUploadId,
        mappingItems.length > 0 ? mappingItems : undefined,
      );
      setNormalizeResult(result);
      setProgress(100);
      setDone(true);

      localStorage.setItem("lastUploadId", String(result.upload_id));
      localStorage.setItem("lastNormalizationRunId", String(result.normalization_run_id));

      setStatusMessage(
        `Normalizasyon tamamlandı — ${result.total_processed} kayıt işlendi, ${result.success_count} geçerli (Run ID: ${result.normalization_run_id})`,
      );
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Normalizasyon sırasında hata oluştu");
      setProgress(0);
    } finally {
      clearInterval(progressInterval);
      setRunning(false);
    }
  };

  const activeCount = rules.filter((r) => r.active).length;

  return (
    <DashboardLayout>
      <Header
        title="Veri Normalizasyon"
        subtitle="Yüklenen ham kayıtları standart formata dönüştürün ve temiz veri seti oluşturun"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded">
                Backend: Erişilemiyor
              </span>
            )}
            <button
              onClick={handleRun}
              disabled={running || selectedUploadId === ""}
              className="flex items-center gap-2 bg-red-600 text-white text-sm font-medium px-5 py-2 rounded-lg hover:bg-red-700 disabled:opacity-60 cursor-pointer transition-colors whitespace-nowrap"
            >
              <i className={`${running ? "ri-loader-4-line animate-spin" : "ri-play-line"}`}></i>
              {running ? "Çalışıyor..." : "Normalizasyonu Çalıştır"}
            </button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* Upload selector */}
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-1">Yükleme Seç</h3>
          <p className="text-xs text-gray-400 mb-3">
            Normalizasyon yapılacak ham veri yüklemesini seçin. Önce Veri Yükleme adımını tamamlamış olmanız gerekir.
          </p>

          {loadingUploads ? (
            <p className="text-sm text-gray-400">Yüklemeler yükleniyor…</p>
          ) : uploads.length === 0 ? (
            <div className="flex items-start gap-3 rounded-xl border border-amber-100 bg-amber-50 p-4">
              <i className="ri-alert-line text-lg text-amber-500 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-amber-700 font-medium">Henüz yükleme yok</p>
                <p className="text-xs text-amber-600 mt-0.5">
                  Önce{" "}
                  <button
                    onClick={() => navigate("/veri-yukleme")}
                    className="underline cursor-pointer"
                  >
                    Veri Yükleme
                  </button>{" "}
                  sayfasından dosya yükleyin.
                </p>
              </div>
            </div>
          ) : (
            <select
              value={selectedUploadId}
              onChange={(e) => {
                const v = e.target.value;
                setSelectedUploadId(v === "" ? "" : Number(v));
                setDone(false);
                setNormalizeResult(null);
                setErrorMessage("");
                setStatusMessage("");
              }}
              className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:border-red-400 focus:ring-1 focus:ring-red-100"
            >
              <option value="">— Yükleme seçin —</option>
              {uploads.map((u) => (
                <option key={u.id} value={u.id}>
                  #{u.id} — {u.file_name} ({u.total_records} kayıt · {u.processing_stage ?? u.status})
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Column mapping panel */}
        {selectedUploadId !== "" && (
          <div className="bg-white rounded-xl border border-gray-100 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-1">Kolon Eşleştirme</h3>
            <p className="text-xs text-gray-400 mb-3">
              Kaynak kolonlarınızı hedef sistem alanlarıyla eşleştirin. Öneriler otomatik doldurulmuştur.
            </p>

            {loadingColumns ? (
              <p className="text-sm text-gray-400">Kolonlar yükleniyor…</p>
            ) : sourceColumns.length === 0 ? (
              <p className="text-sm text-gray-400">Bu upload için ham kayıt bulunamadı.</p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                <div className="grid grid-cols-2 gap-2 text-xs font-medium text-gray-500 px-1 pb-1 border-b border-gray-100">
                  <span>Kaynak Kolon</span>
                  <span>Hedef Alan</span>
                </div>
                {sourceColumns.map((col) => (
                  <div key={col} className="grid grid-cols-2 gap-2 items-center">
                    <span className="text-xs text-gray-700 font-mono bg-gray-50 px-2 py-1.5 rounded truncate">
                      {col}
                    </span>
                    <select
                      value={columnMappings[col] ?? ""}
                      onChange={(e) =>
                        setColumnMappings((prev) => ({ ...prev, [col]: e.target.value }))
                      }
                      className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs bg-white focus:outline-none focus:border-red-400"
                    >
                      {TARGET_FIELD_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Error / Status Messages */}
        {errorMessage && (
          <div className="rounded-xl p-4 border bg-red-50 border-red-100 flex items-center gap-3">
            <i className="ri-error-warning-fill text-red-600 text-lg"></i>
            <p className="text-sm text-red-700">{errorMessage}</p>
          </div>
        )}

        {statusMessage && (
          <div className="rounded-xl p-4 border bg-green-50 border-green-100 flex items-center gap-3">
            <i className="ri-checkbox-circle-fill text-green-600 text-lg"></i>
            <p className="text-sm text-green-700">{statusMessage}</p>
          </div>
        )}

        {/* Progress */}
        {(running || done) && (
          <div className={`rounded-xl p-4 border flex items-center gap-4 ${done ? "bg-green-50 border-green-100" : "bg-red-50 border-red-100"}`}>
            <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${done ? "bg-green-100" : "bg-red-100"}`}>
              <i className={`text-lg ${done ? "ri-checkbox-circle-fill text-green-600" : "ri-loader-4-line text-red-600 animate-spin"}`}></i>
            </div>
            <div className="flex-1">
              <p className={`text-sm font-semibold ${done ? "text-green-700" : "text-red-700"}`}>
                {done ? statusMessage : `Normalizasyon çalışıyor... %${progress}`}
              </p>
              <div className="mt-1.5 bg-white/60 rounded-full h-1.5 overflow-hidden">
                <div
                  className={`h-1.5 rounded-full transition-all duration-200 ${done ? "bg-green-500" : "bg-red-500"}`}
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Post-normalization actions */}
        {done && normalizeResult && (
          <div className="bg-white rounded-xl border border-green-100 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Sonraki Adım</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              {[
                { label: "İşlenen Kayıt", value: String(normalizeResult.total_processed) },
                { label: "Başarılı", value: String(normalizeResult.success_count) },
                { label: "Hatalı", value: String(normalizeResult.failed_count) },
                { label: "Run ID", value: String(normalizeResult.normalization_run_id) },
              ].map((s) => (
                <div key={s.label} className="bg-gray-50 rounded-lg p-3 text-center">
                  <p className="text-base font-bold text-gray-900">{s.value}</p>
                  <p className="text-[10px] text-gray-400 mt-0.5">{s.label}</p>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => navigate(`/temiz-veri-seti?upload_id=${normalizeResult.upload_id}`)}
                className="flex items-center gap-2 bg-red-600 text-white text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-red-700 cursor-pointer transition-colors whitespace-nowrap"
              >
                <i className="ri-table-line"></i> Temiz Veriyi Görüntüle
              </button>
              <button
                onClick={() => navigate("/mukerrer-tespit")}
                className="flex items-center gap-2 border border-gray-200 text-gray-700 text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors whitespace-nowrap"
              >
                <i className="ri-radar-line"></i> Mükerrer Tespite Git
              </button>
            </div>
          </div>
        )}

        {/* Rules List */}
        <div className="bg-white rounded-xl border border-gray-100">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-50">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">Normalizasyon Kuralları</h3>
              <p className="text-xs text-gray-400 mt-0.5">{activeCount} / {rules.length} kural aktif</p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setRules((r) => r.map((x) => ({ ...x, active: true })))}
                className="text-xs text-red-600 font-medium hover:underline cursor-pointer whitespace-nowrap"
              >
                Tümünü Aktif Et
              </button>
              <button
                onClick={() => setRules((r) => r.map((x) => ({ ...x, active: false })))}
                className="text-xs text-gray-500 font-medium hover:underline cursor-pointer whitespace-nowrap"
              >
                Tümünü Kapat
              </button>
            </div>
          </div>
          <div className="divide-y divide-gray-50 max-h-[360px] overflow-y-auto">
            {rules.map((rule) => (
              <div key={rule.id} className="flex items-start gap-3 px-5 py-4 hover:bg-gray-50/40 transition-colors">
                <button
                  onClick={() => toggleRule(rule.id)}
                  className={`relative w-11 min-w-[44px] h-5 rounded-full overflow-hidden flex items-center transition-colors duration-200 flex-shrink-0 mt-0.5 cursor-pointer ${rule.active ? "bg-red-500" : "bg-gray-200"}`}
                >
                  <span className={`absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow-sm transition-transform duration-200 ${rule.active ? "translate-x-6" : "translate-x-0"}`} />
                </button>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium text-gray-800">{rule.name}</p>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${categoryColors[rule.category] || "bg-gray-100 text-gray-500"}`}>
                      {rule.category}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">{rule.description}</p>
                  <p className="text-[10px] text-gray-300 mt-1">Alan: {rule.field}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
