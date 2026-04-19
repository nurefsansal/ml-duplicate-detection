import { useState, useEffect, useRef } from "react";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { normalizationRules, normalizationPreview, type NormalizationRule } from "../../mocks/records";
import { normalizeFromFile, type NormalizeResponse } from "../../services/api";

const categoryColors: Record<string, string> = {
  metin: "bg-blue-50 text-blue-600",
  karakter: "bg-purple-50 text-purple-600",
  format: "bg-orange-50 text-orange-600",
  dogrulama: "bg-green-50 text-green-600",
  adres: "bg-yellow-50 text-yellow-700",
};

export default function VeriNormalizasyon() {
  const [rules, setRules] = useState<NormalizationRule[]>(normalizationRules);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const [progress, setProgress] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [normalizeResult, setNormalizeResult] = useState<NormalizeResponse | null>(null);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Backend health check
  useEffect(() => {
    let mounted = true;
    import("../../services/api")
      .then(({ healthCheck }) => healthCheck())
      .then(() => {
        if (mounted) setBackendHealthy(true);
      })
      .catch(() => {
        if (mounted) setBackendHealthy(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const toggleRule = (id: number) => {
    setRules((prev) => prev.map((r) => (r.id === id ? { ...r, active: !r.active } : r)));
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setErrorMessage("");
      setStatusMessage("");
    }
  };

  const handleRun = async () => {
    if (!selectedFile) {
      setErrorMessage("Lütfen önce bir dosya seçin");
      return;
    }

    setRunning(true);
    setDone(false);
    setProgress(0);
    setUploading(true);
    setErrorMessage("");
    setStatusMessage("");
    setNormalizeResult(null);

    // Simulate progress
    const progressInterval = setInterval(() => {
      setProgress((p) => Math.min(p + Math.floor(Math.random() * 15) + 5, 90));
    }, 200);

    try {
      const result = await normalizeFromFile(selectedFile);
      setNormalizeResult(result);
      setProgress(100);
      setDone(true);
      setStatusMessage(`Normalizasyon tamamlandı — ${result.totalRecords} kayıt işlendi`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Normalizasyon sırasında hata oluştu");
      setProgress(0);
    } finally {
      clearInterval(progressInterval);
      setRunning(false);
      setUploading(false);
    }
  };

  const activeCount = rules.filter((r) => r.active).length;

  // Use real preview data if available, otherwise fallback to mock
  const previewData = normalizeResult?.normalizedRecords
    ? normalizeResult.normalizedRecords.slice(0, 5).map((record) => ({
        field: "Örnek",
        ham: record["Ad Soyad"] as string || "-",
        normalize: record["clean_name"] as string || "-",
      }))
    : normalizationPreview;

  return (
    <DashboardLayout>
      <Header
        title="Veri Normalizasyon"
        subtitle="Excel/CSV dosyalarındaki kayıtları standart formata dönüştürün"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded">
                Backend: Erişilemiyor
              </span>
            )}
            <button
              onClick={handleRun}
              disabled={running || !selectedFile}
              className="flex items-center gap-2 bg-red-600 text-white text-sm font-medium px-5 py-2 rounded-lg hover:bg-red-700 disabled:opacity-60 cursor-pointer transition-colors whitespace-nowrap"
            >
              <i className={`${running ? "ri-loader-4-line animate-spin" : "ri-play-line"}`}></i>
              {running ? "Çalışıyor..." : "Normalizasyonu Çalıştır"}
            </button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* File Upload */}
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Dosya Seç</h3>
          <div className="flex items-center gap-4">
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={handleFileSelect}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 cursor-pointer transition-colors"
            >
              <i className="ri-folder-open-line"></i>
              Dosya Seç
            </button>
            {selectedFile && (
              <span className="text-sm text-gray-600">
                Seçilen: <span className="font-medium">{selectedFile.name}</span>
                <span className="text-gray-400 ml-1">
                  ({(selectedFile.size / 1024).toFixed(1)} KB)
                </span>
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Desteklenen formatlar: .xlsx, .xls, .csv — Maks. 50 MB
          </p>
        </div>

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

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
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
            <div className="divide-y divide-gray-50 max-h-[400px] overflow-y-auto">
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

          {/* Preview Table */}
          <div className="bg-white rounded-xl border border-gray-100">
            <div className="px-5 py-4 border-b border-gray-50">
              <h3 className="text-sm font-semibold text-gray-900">
                {normalizeResult ? "Sonuç Önizleme" : "Ham vs Normalize Önizleme"}
              </h3>
              <p className="text-xs text-gray-400 mt-0.5">
                {normalizeResult
                  ? `${normalizeResult.normalizedRecords.length} normalize edilmiş kayıt`
                  : "Örnek kayıt üzerindeki dönüşüm sonuçları"}
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50/70">
                    <th className="text-left text-gray-400 font-medium px-5 py-3 w-24">Alan</th>
                    <th className="text-left text-gray-400 font-medium px-4 py-3">
                      {normalizeResult ? "Normalize Ad Soyad" : "Ham Veri"}
                    </th>
                    <th className="text-left text-gray-400 font-medium px-4 py-3">
                      {normalizeResult ? "Clean Name" : "Normalize"}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {normalizeResult
                    ? normalizeResult.normalizedRecords.slice(0, 8).map((record, i) => (
                        <tr key={i} className="hover:bg-gray-50/50 transition-colors">
                          <td className="px-5 py-3 font-medium text-gray-600 whitespace-nowrap">
                            #{i + 1}
                          </td>
                          <td className="px-4 py-3 text-gray-600 max-w-[140px]">
                            <span className="bg-gray-50 text-gray-700 px-1.5 py-0.5 rounded font-mono text-[11px] break-all">
                              {(record["Ad Soyad"] as string) || "-"}
                            </span>
                          </td>
                          <td className="px-4 py-3 max-w-[140px]">
                            <span className="bg-green-50 text-green-700 px-1.5 py-0.5 rounded font-mono text-[11px] break-all">
                              {(record["clean_name"] as string) || "-"}
                            </span>
                          </td>
                        </tr>
                      ))
                    : previewData.map((row, i) => (
                        <tr key={i} className="hover:bg-gray-50/50 transition-colors">
                          <td className="px-5 py-3 font-medium text-gray-600 whitespace-nowrap">{row.field}</td>
                          <td className="px-4 py-3 text-gray-400 max-w-[140px]">
                            <span className="bg-red-50 text-red-600 px-1.5 py-0.5 rounded font-mono text-[11px] break-all">{row.ham}</span>
                          </td>
                          <td className="px-4 py-3 max-w-[140px]">
                            <span className="bg-green-50 text-green-700 px-1.5 py-0.5 rounded font-mono text-[11px] break-all">{row.normalize}</span>
                          </td>
                        </tr>
                      ))}
                </tbody>
              </table>
            </div>
            <div className="px-5 py-4 border-t border-gray-50 bg-gray-50/30">
              <div className="flex items-center gap-4 text-xs text-gray-500">
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-red-100 inline-block"></span>
                  Ham veri
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-green-100 inline-block"></span>
                  Normalize veri
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            {
              label: "İşlenecek Kayıt",
              value: normalizeResult ? String(normalizeResult.totalRecords) : "124.836",
              icon: "ri-database-2-line",
              color: "text-gray-700",
            },
            {
              label: "Aktif Kural",
              value: String(activeCount),
              icon: "ri-settings-4-line",
              color: "text-red-600",
            },
            {
              label: "Tahmini Süre",
              value: normalizeResult ? "~1 dk" : "~4 dk",
              icon: "ri-time-line",
              color: "text-orange-500",
            },
            {
              label: "Son Çalışma",
              value: done ? "Şimdi" : "2 sa önce",
              icon: "ri-history-line",
              color: "text-green-600",
            },
          ].map((stat) => (
            <div key={stat.label} className="bg-white rounded-xl p-4 border border-gray-100 flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-gray-50 flex items-center justify-center flex-shrink-0">
                <i className={`${stat.icon} ${stat.color} text-lg`}></i>
              </div>
              <div>
                <p className="text-lg font-bold text-gray-900">{stat.value}</p>
                <p className="text-[11px] text-gray-400">{stat.label}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </DashboardLayout>
  );
}