import { useEffect, useRef, useState } from "react";
import {
  apiClient,
  type ConnectorConnectionInput,
  type ConnectorPreviewResponse,
  type ConnectorTablesResponse,
} from "../../services/api";

export const INSTITUTION_DB_PROFILE_KEY = "institution-db-profile";

type SavedConnectorProfile = Omit<ConnectorConnectionInput, "password">;

const DEFAULT_CONNECTOR_PROFILE: ConnectorConnectionInput = {
  host: "",
  port: 5434,
  database: "",
  username: "",
  password: "",
  db_schema: "public",
  sslmode: "prefer",
  label: "kurum-db",
};

export type InstitutionImportResult = {
  upload_id: number;
  total_records: number;
  source?: string;
};

type Props = {
  /** Veri yükleme sayfasında içe aktarma düğmesini göster */
  showImport?: boolean;
  onImported?: (result: InstitutionImportResult) => void;
};

export default function InstitutionDbConnectorPanel({
  showImport = false,
  onImported,
}: Props) {
  const [connectorProfile, setConnectorProfile] =
    useState<ConnectorConnectionInput>(DEFAULT_CONNECTOR_PROFILE);
  const [sessionPassword, setSessionPassword] = useState("");
  const [connectorTables, setConnectorTables] = useState<
    ConnectorTablesResponse["tables"]
  >([]);
  const [selectedConnectorTable, setSelectedConnectorTable] = useState("");
  const [connectorPreview, setConnectorPreview] = useState<
    ConnectorPreviewResponse["rows"]
  >([]);
  const [connectorStatus, setConnectorStatus] = useState("");
  const [connectorBusy, setConnectorBusy] = useState(false);
  const [connectorError, setConnectorError] = useState("");
  const passwordRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem(INSTITUTION_DB_PROFILE_KEY);
    if (!saved) return;
    try {
      const parsed: SavedConnectorProfile = JSON.parse(saved);
      setConnectorProfile((prev) => ({
        ...prev,
        ...parsed,
        password: "",
      }));
    } catch (e) {
      console.error("Error loading connector profile:", e);
    }
  }, []);

  useEffect(() => {
    if (showImport) {
      setTimeout(() => passwordRef.current?.focus(), 50);
    }
  }, [showImport]);

  const persistConnectorProfile = () => {
    const profileToSave: SavedConnectorProfile = {
      host: connectorProfile.host,
      port: connectorProfile.port,
      database: connectorProfile.database,
      username: connectorProfile.username,
      db_schema: connectorProfile.db_schema,
      sslmode: connectorProfile.sslmode,
      label: connectorProfile.label,
    };
    localStorage.setItem(INSTITUTION_DB_PROFILE_KEY, JSON.stringify(profileToSave));
    setConnectorStatus("Bağlantı kaydedildi. Parola tarayıcıda saklanmadı.");
  };

  const buildConnectionPayload = (): ConnectorConnectionInput | null => {
    const password =
      connectorProfile.password?.trim() || sessionPassword.trim();
    if (!connectorProfile.host?.trim() || !connectorProfile.database?.trim()) {
      setConnectorError("Host ve veritabanı adı zorunludur.");
      return null;
    }
    if (!password) {
      setConnectorError("Parola eksik. Oturum parolasını girin veya formda girin.");
      return null;
    }
    return { ...connectorProfile, password };
  };

  const loadTables = async (connection?: ConnectorConnectionInput) => {
    const payload = connection ?? buildConnectionPayload();
    if (!payload) return;
    setConnectorBusy(true);
    setConnectorError("");
    setConnectorStatus("");
    try {
      const response = await apiClient.post<ConnectorTablesResponse>(
        "/api/v1/connector/tables",
        payload,
      );
      setConnectorTables(response.data.tables || []);
      if (response.data.tables?.length) {
        const first = response.data.tables[0];
        setSelectedConnectorTable(`${first.table_schema}.${first.table_name}`);
      }
      setConnectorStatus(`${response.data.tables.length} tablo listelendi.`);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Tablo listesi alınamadı";
      setConnectorError(message);
    } finally {
      setConnectorBusy(false);
    }
  };

  const testConnector = async () => {
    const payload = buildConnectionPayload();
    if (!payload) return;
    setConnectorBusy(true);
    setConnectorError("");
    setConnectorStatus("");
    try {
      const response = await apiClient.post("/api/v1/connector/test", payload);
      setConnectorStatus(
        `Bağlantı başarılı: ${response.data.health.database} (${response.data.health.host})`,
      );
      persistConnectorProfile();
      await loadTables(payload);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Bağlantı testi başarısız";
      setConnectorError(message);
    } finally {
      setConnectorBusy(false);
    }
  };

  const previewSelectedTable = async () => {
    if (!selectedConnectorTable) {
      setConnectorError("Önizlemek için bir tablo seçin.");
      return;
    }
    const payload = buildConnectionPayload();
    if (!payload) return;
    setConnectorBusy(true);
    setConnectorError("");
    setConnectorStatus("");
    try {
      const [schemaName, tableName] = selectedConnectorTable.includes(".")
        ? selectedConnectorTable.split(".", 2)
        : [connectorProfile.db_schema || "public", selectedConnectorTable];
      const response = await apiClient.post<ConnectorPreviewResponse>(
        `/api/v1/connector/tables/${encodeURIComponent(tableName)}/preview`,
        {
          connection: { ...payload, db_schema: schemaName },
          limit: 10,
        },
      );
      setConnectorPreview(response.data.rows || []);
      setConnectorStatus(`Önizleme hazır: ${response.data.rows.length} satır gösteriliyor.`);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Tablo önizlemesi alınamadı";
      setConnectorError(message);
    } finally {
      setConnectorBusy(false);
    }
  };

  const importFromInstitution = async () => {
    const payload = buildConnectionPayload();
    if (!payload) return;
    if (!selectedConnectorTable) {
      setConnectorError("Lütfen içeri alınacak tabloyu seçin.");
      return;
    }
    setConnectorBusy(true);
    setConnectorError("");
    setConnectorStatus("");
    try {
      const resp = await apiClient.post("/api/v1/uploads/from-institution-db", {
        connection: payload,
        table: selectedConnectorTable,
      });
      const data = resp.data as InstitutionImportResult;
      setConnectorStatus(
        `İçe aktarma tamamlandı. ${data.total_records} kayıt alındı (Yükleme No: ${data.upload_id}).`,
      );
      onImported?.(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "İçe aktarma başarısız";
      setConnectorError(message);
    } finally {
      setConnectorBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">
            Kurum Veritabanı Bağlantısı
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            Kurum PostgreSQL veritabanına bağlanır; uygulamanın kendi veritabanı ayarlarını
            değiştirmez. Bağlantı bilgileri (parola hariç) tarayıcıda saklanabilir.
          </p>
        </div>
        <button
          onClick={persistConnectorProfile}
          className="text-xs text-red-600 hover:underline cursor-pointer whitespace-nowrap"
          type="button"
        >
          Bağlantıyı Kaydet
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1.5">Bağlantı Adı</label>
          <input
            value={connectorProfile.label}
            onChange={(e) =>
              setConnectorProfile((prev) => ({ ...prev, label: e.target.value }))
            }
            className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
            placeholder="kurum-db"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1.5">Schema</label>
          <input
            value={connectorProfile.db_schema || ""}
            onChange={(e) =>
              setConnectorProfile((prev) => ({
                ...prev,
                db_schema: e.target.value || null,
              }))
            }
            className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
            placeholder="public"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1.5">Host</label>
          <input
            value={connectorProfile.host}
            onChange={(e) =>
              setConnectorProfile((prev) => ({ ...prev, host: e.target.value }))
            }
            className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
            placeholder="db.institution.local"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1.5">Port</label>
          <input
            type="number"
            value={connectorProfile.port}
            onChange={(e) =>
              setConnectorProfile((prev) => ({
                ...prev,
                port: Number(e.target.value),
              }))
            }
            className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
            min={1}
            max={65535}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1.5">Veritabanı Adı</label>
          <input
            value={connectorProfile.database}
            onChange={(e) =>
              setConnectorProfile((prev) => ({ ...prev, database: e.target.value }))
            }
            className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
            placeholder="kurum_veritabani"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1.5">SSL Mode</label>
          <select
            value={connectorProfile.sslmode || "prefer"}
            onChange={(e) =>
              setConnectorProfile((prev) => ({ ...prev, sslmode: e.target.value }))
            }
            className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 bg-white cursor-pointer"
          >
            <option value="prefer">prefer</option>
            <option value="require">require</option>
            <option value="disable">disable</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1.5">Kullanıcı Adı</label>
          <input
            value={connectorProfile.username}
            onChange={(e) =>
              setConnectorProfile((prev) => ({ ...prev, username: e.target.value }))
            }
            className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
            placeholder="read_only_user"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1.5">
            Parola {showImport ? "(oturum)" : ""}
          </label>
          <input
            type="password"
            ref={passwordRef}
            value={showImport ? sessionPassword : connectorProfile.password}
            onChange={(e) => {
              if (showImport) {
                setSessionPassword(e.target.value);
              } else {
                setConnectorProfile((prev) => ({
                  ...prev,
                  password: e.target.value,
                }));
              }
            }}
            className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
            placeholder="••••••••"
          />
          {showImport ? (
            <p className="mt-1 text-[11px] text-gray-500">
              Oturum parolası tarayıcıya kaydedilmez; her girişte yeniden girilir.
            </p>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={testConnector}
          disabled={connectorBusy}
          className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium disabled:opacity-50 hover:bg-red-700 transition-colors"
        >
          Bağlantıyı Kontrol Et
        </button>
        <button
          type="button"
          onClick={() => loadTables()}
          disabled={connectorBusy}
          className="px-4 py-2 rounded-lg bg-gray-900 text-white text-sm font-medium disabled:opacity-50 hover:bg-black transition-colors"
        >
          Tabloları Listele
        </button>
        <button
          type="button"
          onClick={previewSelectedTable}
          disabled={connectorBusy || !selectedConnectorTable}
          className="px-4 py-2 rounded-lg border border-gray-200 text-gray-800 text-sm font-medium disabled:opacity-50 hover:border-gray-300 transition-colors"
        >
          Seçili Tabloyu Göster
        </button>
        {showImport ? (
          <button
            type="button"
            onClick={importFromInstitution}
            disabled={connectorBusy || !selectedConnectorTable}
            className="rounded-lg bg-gradient-to-r from-primary-600 to-primary-700 px-4 py-2 text-sm font-semibold text-white shadow-sm disabled:opacity-50"
          >
            Kurumdan İçe Aktar
          </button>
        ) : null}
      </div>

      {(connectorStatus || connectorError) && (
        <div
          className={`rounded-lg px-4 py-3 text-sm ${
            connectorError
              ? "bg-red-50 text-red-700 border border-red-100"
              : "bg-green-50 text-green-700 border border-green-100"
          }`}
        >
          {connectorError || connectorStatus}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Tablo Listesi
            </h4>
            <span className="text-xs text-gray-400">{connectorTables.length} tablo</span>
          </div>
          <select
            value={selectedConnectorTable}
            onChange={(e) => setSelectedConnectorTable(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 bg-white cursor-pointer"
          >
            <option value="">Bir tablo seçin</option>
            {connectorTables.map((table) => {
              const value = `${table.table_schema}.${table.table_name}`;
              return (
                <option key={value} value={value}>
                  {value}
                </option>
              );
            })}
          </select>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Tablo Önizlemesi
            </h4>
            <span className="text-xs text-gray-400">İlk 10 satır</span>
          </div>
          <div className="border border-gray-200 rounded-xl overflow-hidden">
            <div className="max-h-64 overflow-auto">
              {connectorPreview.length === 0 ? (
                <div className="p-4 text-sm text-gray-400">
                  Tabloyu görmek için seçim yapıp önizleme düğmesine basın.
                </div>
              ) : (
                <table className="min-w-full text-left text-xs">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      {Object.keys(connectorPreview[0] || {}).map((key) => (
                        <th
                          key={key}
                          className="px-3 py-2 font-medium text-gray-500 border-b border-gray-200"
                        >
                          {key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {connectorPreview.map((row, index) => (
                      <tr key={index} className="odd:bg-white even:bg-gray-50">
                        {Object.values(row).map((value, cellIndex) => (
                          <td
                            key={cellIndex}
                            className="px-3 py-2 border-b border-gray-100 text-gray-700 whitespace-nowrap"
                          >
                            {value == null ? "-" : String(value)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
