import { useState, useEffect } from "react";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import DropZone from "./components/DropZone";
import SourceSelector from "./components/SourceSelector";
import UploadProgress from "./components/UploadProgress";
import UploadHistoryTable from "./components/UploadHistoryTable";
import {
  type DetectResponse,
  type NormalizedRecord,
  detectDuplicates,
  detectDuplicatesFromFile,
  detectDuplicatesFromUrl,
  healthCheck,
} from "../../services/api";

type SourceType = "excel" | "csv" | "api" | "manuel";

export default function VeriYukleme() {
  const [source, setSource] = useState<SourceType>("excel");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState("");
  const [apiUrl, setApiUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiMethod, setApiMethod] = useState<"GET" | "POST">("GET");
  const [saveToDb, setSaveToDb] = useState(true);
  const [loadingAction, setLoadingAction] = useState(false);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<DetectResponse | null>(null);
  const [manualRecords, setManualRecords] = useState<NormalizedRecord[]>([]);
  const [manuelForm, setManuelForm] = useState({
    adSoyad: "",
    tcKimlikNo: "",
    telefon: "",
    email: "",
    sehir: "",
  });

  useEffect(() => {
    let mounted = true;
    healthCheck()
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

  const getError = (error: unknown) => {
    if (typeof error === "object" && error && "response" in error) {
      const response = (error as { response?: { data?: { detail?: string } } })
        .response;
      if (response?.data?.detail) {
        return response.data.detail;
      }
    }
    if (error instanceof Error) {
      return error.message;
    }
    return "Bilinmeyen bir hata oluştu";
  };

  const handleFileSelect = async (file: File) => {
    setFileName(file.name);
    setProgress(0);
    setUploading(true);
    setLoadingAction(true);
    setErrorMessage("");
    setStatusMessage("");

    const timer = setInterval(() => {
      setProgress((p) => Math.min(p + 8, 92));
    }, 180);

    try {
      const response = await detectDuplicatesFromFile(file, { saveToDb });
      setResult(response);
      setStatusMessage(
        `Analiz tamamlandı. Aday: ${response.candidatePairs}, Mükerrer: ${response.duplicatePairs}, DB'ye yazılan: ${response.insertedRows}`,
      );
      setProgress(100);
    } catch (error) {
      setErrorMessage(getError(error));
      setProgress(0);
    } finally {
      clearInterval(timer);
      setLoadingAction(false);
      setTimeout(() => setUploading(false), 600);
    }
  };

  const handleCancel = () => {
    setUploading(false);
    setProgress(0);
    setFileName("");
  };

  const handleApiFetch = async () => {
    if (!apiUrl.trim()) {
      setErrorMessage("Lütfen API endpoint URL girin");
      return;
    }

    setLoadingAction(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const response = await detectDuplicatesFromUrl({
        url: apiUrl.trim(),
        method: apiMethod,
        apiKey: apiKey.trim() || undefined,
        saveToDb,
      });
      setResult(response);
      setStatusMessage(
        `API verisi işlendi. Mükerrer çift: ${response.duplicatePairs}. DB'ye yazılan: ${response.insertedRows}`,
      );
    } catch (error) {
      setErrorMessage(getError(error));
    } finally {
      setLoadingAction(false);
    }
  };

  const handleManualSave = () => {
    if (!manuelForm.adSoyad.trim()) {
      setErrorMessage("Manuel kayıt için en az Ad Soyad alanı zorunlu");
      return;
    }

    setManualRecords((prev) => [...prev, { ...manuelForm }]);
    setManuelForm({
      adSoyad: "",
      tcKimlikNo: "",
      telefon: "",
      email: "",
      sehir: "",
    });
    setErrorMessage("");
    setStatusMessage("Manuel kayıt listeye eklendi");
  };

  const handleManualDetect = async () => {
    if (manualRecords.length === 0) {
      setErrorMessage("Önce en az bir manuel kayıt ekleyin");
      return;
    }

    setLoadingAction(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const response = await detectDuplicates(manualRecords, { saveToDb });
      setResult(response);
      setStatusMessage(
        `Manuel kayıt analizi tamamlandı. Mükerrer çift: ${response.duplicatePairs}. DB'ye yazılan: ${response.insertedRows}`,
      );
    } catch (error) {
      setErrorMessage(getError(error));
    } finally {
      setLoadingAction(false);
    }
  };

  const previewRows = result?.duplicates ?? [];
  const previewKeys =
    previewRows.length > 0 ? Object.keys(previewRows[0]).slice(0, 8) : [];

  return (
    <DashboardLayout>
      <Header
        title="Veri Yükleme"
        subtitle="Excel, CSV, API veya manuel giriş ile kayıt yükleyin"
        actions={
          <div className="flex items-center gap-3 text-xs text-gray-500 bg-gray-50 border border-gray-100 rounded-lg px-3 py-2">
            <i className="ri-information-line text-sm"></i>
            <span>Maks. 50 MB &bull; .xlsx .csv destekleniyor</span>
            <label className="flex items-center gap-1.5 text-gray-700">
              <input
                type="checkbox"
                checked={saveToDb}
                onChange={(e) => setSaveToDb(e.target.checked)}
                className="accent-red-600"
              />
              Sonuçları PostgreSQL'e kaydet
            </label>
          </div>
        }
      />
      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-white rounded-xl p-4 border border-gray-100">
            <p className="text-xs text-gray-400">Backend Durumu</p>
            <p
              className={`text-sm font-semibold mt-1 ${backendHealthy ? "text-green-600" : "text-red-600"}`}
            >
              {backendHealthy === null
                ? "Kontrol ediliyor"
                : backendHealthy
                  ? "Bağlantı aktif"
                  : "Erişilemiyor"}
            </p>
          </div>
          <div className="bg-white rounded-xl p-4 border border-gray-100">
            <p className="text-xs text-gray-400">Toplam Aday Çift</p>
            <p className="text-lg font-bold text-gray-900 mt-1">
              {result?.candidatePairs ?? 0}
            </p>
          </div>
          <div className="bg-white rounded-xl p-4 border border-gray-100">
            <p className="text-xs text-gray-400">Bulunan Mükerrer</p>
            <p className="text-lg font-bold text-red-600 mt-1">
              {result?.duplicatePairs ?? 0}
            </p>
          </div>
        </div>

        {statusMessage ? (
          <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            {statusMessage}
          </div>
        ) : null}
        {errorMessage ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {errorMessage}
          </div>
        ) : null}

        <div className="bg-white rounded-xl p-5 border border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900 mb-1">
            Veri Kaynağı Seçin
          </h3>
          <p className="text-xs text-gray-400 mb-4">
            Hangi kaynaktan veri yüklemek istediğinizi seçin
          </p>
          <SourceSelector selected={source} onChange={setSource} />
        </div>

        {(source === "excel" || source === "csv") && (
          <div className="bg-white rounded-xl p-5 border border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">
              {source === "excel" ? "Excel Dosyası Yükle" : "CSV Dosyası Yükle"}
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

        {source === "api" && (
          <div className="bg-white rounded-xl p-5 border border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">
              API Bağlantısı
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">
                  API Endpoint URL
                </label>
                <input
                  type="text"
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  placeholder="https://api.example.com/records"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 focus:ring-1 focus:ring-red-100 transition-all"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    API Key (Opsiyonel)
                  </label>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Bearer token veya API key"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Metod
                  </label>
                  <select
                    value={apiMethod}
                    onChange={(e) =>
                      setApiMethod(e.target.value as "GET" | "POST")
                    }
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 bg-white"
                  >
                    <option>GET</option>
                    <option>POST</option>
                  </select>
                </div>
              </div>
              <button
                onClick={handleApiFetch}
                disabled={loadingAction}
                className="flex items-center gap-2 bg-red-600 text-white text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-red-700 cursor-pointer transition-colors whitespace-nowrap disabled:opacity-60"
              >
                <i className="ri-plug-line"></i> Bağlan ve Veri Çek
              </button>
            </div>
          </div>
        )}

        {source === "manuel" && (
          <div className="bg-white rounded-xl p-5 border border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">
              Manuel Kayıt Girişi
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {Object.keys(manuelForm).map((key) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5 capitalize">
                    {key}
                  </label>
                  <input
                    type="text"
                    value={manuelForm[key as keyof typeof manuelForm]}
                    onChange={(e) =>
                      setManuelForm((f) => ({ ...f, [key]: e.target.value }))
                    }
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 focus:ring-1 focus:ring-red-100 transition-all"
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-3 mt-4">
              <button
                onClick={handleManualSave}
                className="flex items-center gap-2 bg-red-600 text-white text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-red-700 cursor-pointer transition-colors whitespace-nowrap"
              >
                <i className="ri-save-line"></i> Kaydet
              </button>
              <button
                onClick={() =>
                  setManuelForm({
                    adSoyad: "",
                    tcKimlikNo: "",
                    telefon: "",
                    email: "",
                    sehir: "",
                  })
                }
                className="flex items-center gap-2 border border-gray-200 text-gray-600 text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors whitespace-nowrap"
              >
                <i className="ri-add-line"></i> Yeni Ekle
              </button>
              <button
                onClick={handleManualDetect}
                disabled={loadingAction}
                className="flex items-center gap-2 border border-red-200 text-red-700 bg-red-50 text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-red-100 cursor-pointer transition-colors whitespace-nowrap disabled:opacity-60"
              >
                <i className="ri-search-eye-line"></i> Kaydedilenleri Analiz Et
                ({manualRecords.length})
              </button>
            </div>
          </div>
        )}

        <div className="bg-white rounded-xl p-5 border border-gray-100">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-900">
              Canlı Tespit Sonuçları
            </h3>
            {loadingAction ? (
              <span className="text-xs text-gray-500">İşleniyor...</span>
            ) : null}
          </div>
          {previewRows.length === 0 ? (
            <p className="text-sm text-gray-500">Henüz analiz sonucu yok.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50">
                    {previewKeys.map((key) => (
                      <th
                        key={key}
                        className="text-left px-3 py-2 font-medium text-gray-500"
                      >
                        {key}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewRows.slice(0, 20).map((row, idx) => (
                    <tr key={idx} className="border-t border-gray-100">
                      {previewKeys.map((key) => (
                        <td
                          key={`${idx}-${key}`}
                          className="px-3 py-2 text-gray-700"
                        >
                          {String((row as Record<string, unknown>)[key] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <UploadHistoryTable />
      </div>
    </DashboardLayout>
  );
}
