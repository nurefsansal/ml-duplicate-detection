import { useState, useEffect } from "react";
import { useRef } from "react";
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
  apiClient,
} from "../../services/api";

type SourceType = "excel" | "csv" | "api" | "manuel" | "institution";

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
  const [connectorProfile, setConnectorProfile] = useState<any | null>(null);
  const [connectorTables, setConnectorTables] = useState<Array<{table_schema:string;table_name:string}>>([]);
  const [selectedConnectorTable, setSelectedConnectorTable] = useState<string | null>(null);
  const [instLoading, setInstLoading] = useState(false);
  const [instStatus, setInstStatus] = useState("");
  const [instError, setInstError] = useState("");
  const [connectorPassword, setConnectorPassword] = useState<string>("");
  const connectorPasswordRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let mounted = true;
    healthCheck()
      .then(() => { if (mounted) setBackendHealthy(true); })
      .catch(() => { if (mounted) setBackendHealthy(false); });
    // load saved connector profile if any
    try {
      const p = localStorage.getItem("institution-db-profile");
      if (p) setConnectorProfile(JSON.parse(p));
    } catch (e) {
      // ignore
    }
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    // Eğer kullanıcı 'Kurum DB' kaynağını seçtiyse, parola alanına odaklansın
    if (source === "institution") {
      setTimeout(() => connectorPasswordRef.current?.focus(), 50);
    }
  }, [source]);

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

    const timer = setInterval(() => {
      setProgress((p) => Math.min(p + 8, 92));
    }, 180);

    try {
      const response = await uploadFileOnly(file);
      setResult(response);

      if (typeof response.upload_id === "number") {
        localStorage.setItem("lastUploadId", String(response.upload_id));
      }

      setStatusMessage(
        `Yükleme tamamlandı — ${response.total_records} ham kayıt kaydedildi (Upload ID: ${response.upload_id})`,
      );
      setProgress(100);
    } catch (error) {
      setErrorMessage(getError(error));
      setProgress(0);
    } finally {
      clearInterval(timer);
      setTimeout(() => setUploading(false), 600);
    }
  };

  const handleCancel = () => {
    setUploading(false);
    setProgress(0);
    setFileName("");
  };

  return (
    <DashboardLayout>
      <Header
        title="Veri Yükleme"
        subtitle="Excel veya CSV dosyası yükleyin — ham kayıtlar raw_records tablosuna kaydedilir"
        actions={
          <div className="flex items-center gap-2 text-xs text-gray-500 bg-gray-50 border border-gray-100 rounded-lg px-3 py-2">
            <i className="ri-information-line text-sm"></i>
            <span>Maks. 50 MB &bull; .xlsx .csv destekleniyor</span>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* Stat cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-white rounded-xl p-4 border border-gray-100">
            <p className="text-xs text-gray-400">Backend Durumu</p>
            <p className={`text-sm font-semibold mt-1 ${backendHealthy ? "text-green-600" : backendHealthy === false ? "text-red-600" : "text-gray-400"}`}>
              {backendHealthy === null ? "Kontrol ediliyor…" : backendHealthy ? "Bağlantı aktif" : "Erişilemiyor"}
            </p>
          </div>
          <div className="bg-white rounded-xl p-4 border border-gray-100">
            <p className="text-xs text-gray-400">Yüklenen Ham Kayıt</p>
            <p className="text-lg font-bold text-gray-900 mt-1">
              {result ? result.total_records : 0}
            </p>
          </div>
          <div className="bg-white rounded-xl p-4 border border-gray-100">
            <p className="text-xs text-gray-400">Upload ID</p>
            <p className="text-lg font-bold text-gray-900 mt-1">
              {result ? `#${result.upload_id}` : "—"}
            </p>
          </div>
        </div>

        {/* Info banner: this page does NOT run normalization */}
        <div className="flex items-start gap-3 rounded-xl border border-blue-100 bg-blue-50 p-4">
          <i className="ri-information-line text-lg text-blue-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-blue-800">Bu sayfa sadece ham veri yükler</p>
            <p className="text-xs text-blue-600 mt-0.5">
              Dosyanız <strong>uploads</strong> ve <strong>raw_records</strong> tablolarına kaydedilir.
              Normalizasyon ve duplicate detection bir sonraki adımlarda yapılır.
            </p>
          </div>
        </div>

        {statusMessage && (
          <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            {statusMessage}
          </div>
        )}
        {errorMessage && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {errorMessage}
          </div>
        )}

        {/* Source selector */}
        <div className="bg-white rounded-xl p-5 border border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900 mb-1">Veri Kaynağı Seçin</h3>
          <p className="text-xs text-gray-400 mb-4">Hangi kaynaktan veri yüklemek istediğinizi seçin</p>
          <SourceSelector selected={source} onChange={setSource} />
        </div>

        {/* File upload */}
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

        {/* API source: info banner */}
        {source === "api" && (
          <div className="bg-white rounded-xl p-5 border border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">API Kaynağı</h3>
            <div className="flex items-start gap-3 rounded-xl border border-blue-100 bg-blue-50 p-4">
              <i className="ri-information-line text-lg text-blue-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-blue-700">
                API kaynağından veri çekme özelliği şu an devre dışı. Lütfen Excel veya CSV
                seçeneğini kullanarak verilerinizi dışa aktarın ve yükleyin.
              </p>
            </div>
          </div>
        )}

        {/* Institution DB source */}
        {source === "institution" && (
          <div className="bg-white rounded-xl p-5 border border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Kurum Veritabanından İçeri Aktar</h3>
            <p className="text-xs text-gray-400 mb-3">Ayarlar sayfasında kaydettiğiniz bağlantıyı kullanarak kurum veritabanındaki bir tabloyu içe aktarabilirsiniz.</p>
            <div className="mb-3">
              <p className="text-xs text-gray-600">Kayıtlı Profil:</p>
              <div className="text-sm text-gray-800 mt-1">{connectorProfile ? connectorProfile.label || `${connectorProfile.host}:${connectorProfile.port}` : "Profil bulunamadı. Ayarlar > Kurum DB bölümünden profil oluşturun."}</div>
            </div>
            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-700 mb-1">Parola (geçici, tarayıcıda kaydedilmez)</label>
              <input
                type="password"
                ref={connectorPasswordRef}
                value={connectorPassword}
                onChange={(e) => setConnectorPassword(e.target.value)}
                placeholder="Kurum DB parolası"
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
              />
            </div>
            <div className="flex gap-2 mb-3">
              <button
                onClick={async () => {
                  if (!connectorProfile) { setInstError("Önce Ayarlar'da profil kaydedin"); return; }
                  const connectionPayload = { ...connectorProfile, password: connectorProfile.password || connectorPassword };
                  if (!connectionPayload.password) { setInstError("Parola eksik. Parolayı girin veya Ayarlar'da kaydedin."); return; }
                  setInstLoading(true); setInstError(""); setInstStatus("");
                  try {
                    const resp = await apiClient.post('/api/v1/connector/tables', connectionPayload);
                    setConnectorTables(resp.data.tables || []);
                    if (resp.data.tables?.length) setSelectedConnectorTable(`${resp.data.tables[0].table_schema}.${resp.data.tables[0].table_name}`);
                    setInstStatus(`Tablolar yüklendi: ${resp.data.tables.length}`);
                  } catch (e) {
                    setInstError(e instanceof Error ? e.message : String(e));
                  } finally { setInstLoading(false); }
                }}
                className="px-4 py-2 rounded-lg bg-gray-900 text-white text-sm font-medium"
              >
                Tabloları Listele
              </button>
              <button
                onClick={async () => {
                  if (!connectorProfile) { setInstError("Önce Ayarlar'da profil kaydedin"); return; }
                  const connectionPayload = { ...connectorProfile, password: connectorProfile.password || connectorPassword };
                  if (!connectionPayload.password) { setInstError("Parola eksik. Parolayı girin veya Ayarlar'da kaydedin."); return; }
                  if (!selectedConnectorTable) { setInstError("Bir tablo seçin"); return; }
                  setInstLoading(true); setInstError(""); setInstStatus("");
                  try {
                    const resp = await apiClient.post('/api/v1/uploads/from-institution-db', { connection: connectionPayload, table: selectedConnectorTable });
                    // mimic upload response
                    setResult({ upload_id: resp.data.upload_id, total_records: resp.data.total_records, source_columns: [], source_type: 'institution', file_name: resp.data.source } as any);
                    setStatusMessage(`İçe aktarma tamamlandı — ${resp.data.total_records} kayıt (Upload ID: ${resp.data.upload_id})`);
                  } catch (e) {
                    setInstError(e instanceof Error ? e.message : String(e));
                  } finally { setInstLoading(false); }
                }}
                className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium"
              >
                Kurumdan İçe Aktar
              </button>
            </div>

            {connectorTables.length > 0 && (
              <div className="mb-3">
                <label className="block text-xs text-gray-600 mb-1">Tablo Seçimi</label>
                <select value={selectedConnectorTable || ""} onChange={(e) => setSelectedConnectorTable(e.target.value)} className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm bg-white">
                  <option value="">Tablo seç</option>
                  {connectorTables.map((t) => (
                    <option key={`${t.table_schema}.${t.table_name}`} value={`${t.table_schema}.${t.table_name}`}>
                      {`${t.table_schema}.${t.table_name}`}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {(instStatus || instError) && (
              <div className={`mt-2 rounded-lg px-4 py-3 text-sm ${instError ? "bg-red-50 text-red-700 border border-red-100" : "bg-green-50 text-green-700 border border-green-100"}`}>
                {instError || instStatus}
              </div>
            )}
          </div>
        )}

        {/* Manuel source: info banner */}
        {source === "manuel" && (
          <div className="bg-white rounded-xl p-5 border border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Manuel Giriş</h3>
            <div className="flex items-start gap-3 rounded-xl border border-amber-100 bg-amber-50 p-4">
              <i className="ri-information-line text-lg text-amber-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-amber-700">
                Manuel kayıt girişi şu an bu sayfada desteklenmiyor. Lütfen verilerinizi
                Excel veya CSV dosyası olarak hazırlayıp yükleyin.
              </p>
            </div>
          </div>
        )}

        {/* Success actions */}
        {result && (
          <div className="bg-white rounded-xl p-5 border border-green-100">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Yükleme Başarılı — Sonraki Adım</h3>

            {/* Source columns */}
            {result.source_columns.length > 0 && (
              <div className="mb-4 p-3 bg-gray-50 rounded-lg">
                <p className="text-xs font-medium text-gray-600 mb-2">
                  Tespit edilen kolonlar ({result.source_columns.length}):
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
                { label: "Upload ID", value: String(result.upload_id) },
                { label: "Toplam Kayıt", value: String(result.total_records) },
                { label: "Kaynak Tip", value: result.source_type },
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
                className="flex items-center gap-2 bg-red-600 text-white text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-red-700 cursor-pointer transition-colors whitespace-nowrap"
              >
                <i className="ri-filter-3-line"></i> Normalizasyona Git
              </button>
              <button
                onClick={() => navigate(`/temiz-veri-seti?upload_id=${result.upload_id}`)}
                className="flex items-center gap-2 border border-gray-200 text-gray-700 text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors whitespace-nowrap"
              >
                <i className="ri-table-line"></i> Ham Veriyi İncele
              </button>
            </div>
          </div>
        )}

        <UploadHistoryTable />
      </div>
    </DashboardLayout>
  );
}
