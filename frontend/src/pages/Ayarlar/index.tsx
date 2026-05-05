import { useState, useEffect } from "react";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  apiClient,
  type ConnectorConnectionInput,
  type ConnectorPreviewResponse,
  type ConnectorTablesResponse,
} from "../../services/api";
import { getSettings, saveSettings } from "../../services/api";

const defaultWeights = {
  adSoyad: 30,
  tcKimlikNo: 35,
  telefon: 15,
  email: 10,
  muhatapNo: 10,
};
const weightLabels: Record<string, string> = {
  adSoyad: "Ad Soyad",
  tcKimlikNo: "TC Kimlik No",
  telefon: "Telefon",
  email: "E-posta",
  muhatapNo: "Muhatap Kodu",
};
const defaultThresholds = { otoOnayla: 97, bayrakla: 75, yoksay: 50 };

type Settings = {
  weights: typeof defaultWeights;
  thresholds: typeof defaultThresholds;
  algorithms: string[];
  autoDetectPeriod: string;
  maxFileSize: number;
  approvalLimitDays: number;
  emailNotification: string;
};

type SavedConnectorProfile = Omit<ConnectorConnectionInput, "password">;

const CONNECTOR_PROFILE_KEY = "institution-db-profile";
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

export default function Ayarlar() {
  const [weights, setWeights] = useState(defaultWeights);
  const [thresholds, setThresholds] = useState(defaultThresholds);
  const [algo, setAlgo] = useState<string[]>(["levenshtein", "jaro"]);
  const [saved, setSaved] = useState(false);
  const [autoDetectPeriod, setAutoDetectPeriod] = useState("Her hafta");
  const [maxFileSize, setMaxFileSize] = useState(50);
  const [approvalLimitDays, setApprovalLimitDays] = useState(7);
  const [emailNotification, setEmailNotification] = useState("Sadece kritik");
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [saveError, setSaveError] = useState(false);
  const [connectorProfile, setConnectorProfile] =
    useState<ConnectorConnectionInput>(DEFAULT_CONNECTOR_PROFILE);
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

  useEffect(() => {
    let alive = true;
    getSettings()
      .then((settings) => {
        if (!alive) return;
        const parsed = settings as Partial<Settings>;
        setWeights({ ...defaultWeights, ...(parsed.weights || {}) });
        setThresholds({ ...defaultThresholds, ...(parsed.thresholds || {}) });
        setAlgo(
          Array.isArray(parsed.algorithms)
            ? parsed.algorithms
            : ["levenshtein", "jaro"],
        );
        setAutoDetectPeriod(parsed.autoDetectPeriod || "Her hafta");
        setMaxFileSize(Number(parsed.maxFileSize || 50));
        setApprovalLimitDays(Number(parsed.approvalLimitDays || 7));
        setEmailNotification(parsed.emailNotification || "Sadece kritik");
      })
      .catch((e) => {
        console.error("Error loading settings:", e);
      })
      .finally(() => {
        if (alive) setInitialLoading(false);
      });
    // Load saved connector profile (if any) before setting up cleanup
    const savedConnectorProfile = localStorage.getItem(CONNECTOR_PROFILE_KEY);
    if (savedConnectorProfile) {
      try {
        const parsed: SavedConnectorProfile = JSON.parse(
          savedConnectorProfile as string,
        );
        setConnectorProfile((prev) => ({
          ...prev,
          ...parsed,
          password: "",
        }));
      } catch (e) {
        console.error("Error loading connector profile:", e);
      }
    }

    return () => {
      alive = false;
    };
  }, []);

  const totalWeight = Object.values(weights).reduce((a, b) => a + b, 0);

  const handleSave = async () => {
    setLoading(true);

    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 500));

    // Save to localStorage
    setSaveError(false);
    const settings: Settings = {
      weights,
      thresholds,
      algorithms: algo,
      autoDetectPeriod,
      maxFileSize,
      approvalLimitDays,
      emailNotification,
    };

    try {
      await saveSettings(settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      console.error("Error saving settings:", e);
      setSaveError(true);
      setTimeout(() => setSaveError(false), 3000);
    } finally {
      setLoading(false);
    }
  };

  const toggleAlgo = (id: string) =>
    setAlgo((prev) =>
      prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id],
    );

  const handleResetWeights = () => setWeights(defaultWeights);
  const handleResetThresholds = () => setThresholds(defaultThresholds);

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
    localStorage.setItem(CONNECTOR_PROFILE_KEY, JSON.stringify(profileToSave));
    setConnectorStatus(
      "Bağlantı profili kaydedildi. Parola tarayıcıda tutulmadı.",
    );
  };

  const loadTables = async () => {
    console.log("loadTables called");
    setConnectorBusy(true);
    setConnectorError("");
    setConnectorStatus("");
    try {
      console.log(
        "Sending request to /api/v1/connector/tables",
        connectorProfile,
      );
      const response = await apiClient.post<ConnectorTablesResponse>(
        "/api/v1/connector/tables",
        connectorProfile,
      );
      console.log("Response received:", response.data);
      setConnectorTables(response.data.tables || []);
      if (response.data.tables?.length) {
        const firstTable = `${response.data.tables[0].table_schema}.${response.data.tables[0].table_name}`;
        setSelectedConnectorTable(firstTable);
      }
      setConnectorStatus(`Tablolar yüklendi: ${response.data.tables.length}`);
    } catch (error) {
      console.error("Error in loadTables:", error);
      const message =
        error instanceof Error ? error.message : "Tablo listesi alınamadı";
      setConnectorError(message);
    } finally {
      setConnectorBusy(false);
    }
  };

  const testConnector = async () => {
    setConnectorBusy(true);
    setConnectorError("");
    setConnectorStatus("");
    try {
      const response = await apiClient.post(
        "/api/v1/connector/test",
        connectorProfile,
      );
      setConnectorStatus(
        `Bağlantı başarılı: ${response.data.health.database} (${response.data.health.host})`,
      );
      persistConnectorProfile();
      // Otomatik olarak tabloları yükle: UI düğmesi çalışmıyorsa bile arka planda tablo listesi alınır
      try {
        await loadTables();
      } catch (e) {
        // loadTables hatası kullanıcıyı engellemesin; sadece hata mesajını göster
        console.error("Otomatik tablo yükleme başarısız:", e);
      }
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
          connection: {
            ...connectorProfile,
            db_schema: schemaName,
          },
          limit: 10,
        },
      );
      setConnectorPreview(response.data.rows || []);
      setConnectorStatus(`Önizleme hazır: ${response.data.rows.length} satır`);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Tablo önizlemesi alınamadı";
      setConnectorError(message);
    } finally {
      setConnectorBusy(false);
    }
  };

  return (
    <DashboardLayout>
      <Header
        title="Ayarlar"
        subtitle="Sistem parametrelerini ve algoritma konfigürasyonunu yönetin"
        actions={
          <button
            onClick={handleSave}
            disabled={initialLoading || loading || totalWeight !== 100}
            className={`flex items-center gap-2 text-sm font-medium px-5 py-2 rounded-lg cursor-pointer transition-colors whitespace-nowrap disabled:opacity-50 ${
              saved
                ? "bg-green-600 text-white"
                : "bg-red-600 text-white hover:bg-red-700"
            }`}
          >
            <i
              className={
                saved
                  ? "ri-checkbox-circle-line"
                  : loading
                    ? "ri-loader-4-line animate-spin"
                    : "ri-save-line"
              }
            ></i>
            {saved ? "Kaydedildi!" : loading ? "Kaydediliyor..." : "Kaydet"}
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {initialLoading && (
          <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500">
            <i className="ri-loader-4-line mb-2 block animate-spin text-xl text-red-600" />
            Ayarlar yükleniyor...
          </div>
        )}

        {saveError && (
          <div className="rounded-xl border border-red-100 bg-red-50 p-4 flex items-center gap-3">
            <i className="ri-error-warning-fill text-red-600 text-lg" />
            <p className="text-sm text-red-700">Ayarlar kaydedilemedi</p>
          </div>
        )}

        {/* Warning if weights don't sum to 100 */}
        {!initialLoading && totalWeight !== 100 && (
          <div className="rounded-xl p-4 border bg-yellow-50 border-yellow-100 flex items-center gap-3">
            <i className="ri-alert-line text-yellow-600 text-lg"></i>
            <p className="text-sm text-yellow-700">
              Alan ağırlıkları toplamı %100 olmalı. Şu an:{" "}
              <span className="font-bold">%{totalWeight}</span>
            </p>
          </div>
        )}

        {!initialLoading && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Alan Ağırlıkları */}
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">
                    Alan Ağırlıkları
                  </h3>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Toplam:{" "}
                    <span
                      className={
                        totalWeight === 100
                          ? "text-green-600 font-bold"
                          : "text-red-600 font-bold"
                      }
                    >
                      %{totalWeight}
                    </span>{" "}
                    (100 olmalı)
                  </p>
                </div>
                <button
                  onClick={handleResetWeights}
                  className="text-xs text-red-600 hover:underline cursor-pointer whitespace-nowrap"
                >
                  Sıfırla
                </button>
              </div>
              <div className="space-y-4">
                {Object.entries(weights).map(([key, val]) => (
                  <div key={key}>
                    <div className="flex justify-between mb-1.5">
                      <label className="text-xs font-medium text-gray-700">
                        {weightLabels[key] ?? key}
                      </label>
                      <span className="text-xs font-bold text-red-600">
                        %{val}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={60}
                      value={val}
                      onChange={(e) =>
                        setWeights((w) => ({
                          ...w,
                          [key]: Number(e.target.value),
                        }))
                      }
                      className="w-full accent-red-600 cursor-pointer"
                    />
                    <div className="flex justify-between text-[10px] text-gray-300 mt-0.5">
                      <span>0</span>
                      <span>60</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Eşik Değerleri */}
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">
                    Eşik Değerleri
                  </h3>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Otomatik karar kuralları
                  </p>
                </div>
                <button
                  onClick={handleResetThresholds}
                  className="text-xs text-red-600 hover:underline cursor-pointer whitespace-nowrap"
                >
                  Sıfırla
                </button>
              </div>
              <div className="space-y-5">
                {[
                  {
                    key: "otoOnayla",
                    label: "Otomatik Onayla",
                    desc: "Bu eşiğin üzerindekiler otomatik onaylanır",
                    color: "text-green-600",
                    accent: "accent-green-600",
                  },
                  {
                    key: "bayrakla",
                    label: "Yönetici Onayına Sun",
                    desc: "Bu aralıktakiler incelemeye alınır",
                    color: "text-yellow-600",
                    accent: "accent-yellow-500",
                  },
                  {
                    key: "yoksay",
                    label: "Yoksay Eşiği",
                    desc: "Bu değerin altındakiler mükerrer sayılmaz",
                    color: "text-gray-500",
                    accent: "accent-gray-400",
                  },
                ].map((item) => (
                  <div key={item.key}>
                    <div className="flex justify-between mb-1">
                      <div>
                        <label className="text-xs font-medium text-gray-800">
                          {item.label}
                        </label>
                        <p className="text-[10px] text-gray-400">{item.desc}</p>
                      </div>
                      <span className={`text-sm font-bold ${item.color}`}>
                        %{thresholds[item.key as keyof typeof thresholds]}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={50}
                      max={100}
                      value={thresholds[item.key as keyof typeof thresholds]}
                      onChange={(e) =>
                        setThresholds((t) => ({
                          ...t,
                          [item.key]: Number(e.target.value),
                        }))
                      }
                      className={`w-full cursor-pointer ${item.accent}`}
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* Algoritma */}
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">
                Aktif Algoritmalar
              </h3>
              <div className="space-y-3">
                {[
                  {
                    id: "levenshtein",
                    label: "Levenshtein Mesafesi",
                    desc: "Karakter bazlı düzenleme mesafesi hesabı",
                  },
                  {
                    id: "jaro",
                    label: "Jaro-Winkler",
                    desc: "Önek ağırlıklı string benzerliği",
                  },
                  {
                    id: "soundex",
                    label: "Soundex",
                    desc: "Fonetik ses benzerliği algoritması",
                  },
                  {
                    id: "exact",
                    label: "Tam Eşleşme",
                    desc: "Birebir string karşılaştırması",
                  },
                ].map((a) => {
                  const active = algo.includes(a.id);
                  return (
                    <div
                      key={a.id}
                      className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-all ${active ? "border-red-200 bg-red-50/30" : "border-gray-100 hover:border-gray-200"}`}
                      onClick={() => toggleAlgo(a.id)}
                    >
                      <button
                        className={`relative w-11 min-w-[44px] h-5 rounded-full overflow-hidden flex items-center transition-colors flex-shrink-0 cursor-pointer ${active ? "bg-red-500" : "bg-gray-200"}`}
                        type="button"
                      >
                        <span
                          className={`absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow-sm transition-transform ${active ? "translate-x-6" : "translate-x-0"}`}
                        />
                      </button>
                      <div>
                        <p className="text-sm font-medium text-gray-800">
                          {a.label}
                        </p>
                        <p className="text-xs text-gray-400">{a.desc}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Sistem */}
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">
                Sistem Ayarları
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Otomatik Tespit Periyodu
                  </label>
                  <select
                    value={autoDetectPeriod}
                    onChange={(e) => setAutoDetectPeriod(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 bg-white cursor-pointer"
                  >
                    <option>Her gün</option>
                    <option>Her hafta</option>
                    <option>Her ay</option>
                    <option>Manuel</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Maksimum Dosya Boyutu (MB)
                  </label>
                  <input
                    type="number"
                    value={maxFileSize}
                    onChange={(e) => setMaxFileSize(Number(e.target.value))}
                    min={1}
                    max={500}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Onay Süresi Limiti (gün)
                  </label>
                  <input
                    type="number"
                    value={approvalLimitDays}
                    onChange={(e) =>
                      setApprovalLimitDays(Number(e.target.value))
                    }
                    min={1}
                    max={90}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    E-posta Bildirim
                  </label>
                  <select
                    value={emailNotification}
                    onChange={(e) => setEmailNotification(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 bg-white cursor-pointer"
                  >
                    <option>Açık</option>
                    <option>Kapalı</option>
                    <option>Sadece kritik</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-5 border border-gray-100 lg:col-span-2">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">
                    Kurum DB Bağlantısı
                  </h3>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Bu bölüm sadece kurum veritabanına API üzerinden bağlanır;
                    uygulamanın kendi PostgreSQL ayarlarını değiştirmez.
                  </p>
                </div>
                <button
                  onClick={persistConnectorProfile}
                  className="text-xs text-red-600 hover:underline cursor-pointer whitespace-nowrap"
                  type="button"
                >
                  Profili Kaydet
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Bağlantı Adı
                  </label>
                  <input
                    value={connectorProfile.label}
                    onChange={(e) =>
                      setConnectorProfile((prev) => ({
                        ...prev,
                        label: e.target.value,
                      }))
                    }
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
                    placeholder="kurum-db"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Schema
                  </label>
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
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Host
                  </label>
                  <input
                    value={connectorProfile.host}
                    onChange={(e) =>
                      setConnectorProfile((prev) => ({
                        ...prev,
                        host: e.target.value,
                      }))
                    }
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
                    placeholder="db.institution.local"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Port
                  </label>
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
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Database
                  </label>
                  <input
                    value={connectorProfile.database}
                    onChange={(e) =>
                      setConnectorProfile((prev) => ({
                        ...prev,
                        database: e.target.value,
                      }))
                    }
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
                    placeholder="kurum_veritabani"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    SSL Mode
                  </label>
                  <select
                    value={connectorProfile.sslmode || "prefer"}
                    onChange={(e) =>
                      setConnectorProfile((prev) => ({
                        ...prev,
                        sslmode: e.target.value,
                      }))
                    }
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 bg-white cursor-pointer"
                  >
                    <option value="prefer">prefer</option>
                    <option value="require">require</option>
                    <option value="disable">disable</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Kullanıcı
                  </label>
                  <input
                    value={connectorProfile.username}
                    onChange={(e) =>
                      setConnectorProfile((prev) => ({
                        ...prev,
                        username: e.target.value,
                      }))
                    }
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
                    placeholder="read_only_user"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">
                    Parola
                  </label>
                  <input
                    type="password"
                    value={connectorProfile.password}
                    onChange={(e) =>
                      setConnectorProfile((prev) => ({
                        ...prev,
                        password: e.target.value,
                      }))
                    }
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
                    placeholder="••••••••"
                  />
                </div>
              </div>

              <div className="flex flex-wrap gap-2 mt-4">
                <button
                  type="button"
                  onClick={testConnector}
                  disabled={connectorBusy}
                  className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium disabled:opacity-50 hover:bg-red-700 transition-colors"
                >
                  Bağlantıyı Test Et
                </button>
                <button
                  type="button"
                  onClick={loadTables}
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
                  Seçili Tabloyu Önizle
                </button>
              </div>

              {(connectorStatus || connectorError) && (
                <div
                  className={`mt-4 rounded-lg px-4 py-3 text-sm ${connectorError ? "bg-red-50 text-red-700 border border-red-100" : "bg-green-50 text-green-700 border border-green-100"}`}
                >
                  {connectorError || connectorStatus}
                </div>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-5">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Tablo Seçimi
                    </h4>
                    <span className="text-xs text-gray-400">
                      {connectorTables.length} tablo
                    </span>
                  </div>
                  <select
                    value={selectedConnectorTable}
                    onChange={(e) => setSelectedConnectorTable(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 bg-white cursor-pointer"
                  >
                    <option value="">Tablo seçin</option>
                    {connectorTables.map((table) => {
                      const value = `${table.table_schema}.${table.table_name}`;
                      return (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      );
                    })}
                  </select>
                  <p className="text-xs text-gray-400 mt-2">
                    Önce bağlantıyı test edin, sonra tablo listesinden kurum
                    kaynağını seçin. Tablo adı elle yazılmak zorunda değil.
                  </p>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Önizleme
                    </h4>
                    <span className="text-xs text-gray-400">İlk 10 satır</span>
                  </div>
                  <div className="border border-gray-200 rounded-xl overflow-hidden">
                    <div className="max-h-64 overflow-auto">
                      {connectorPreview.length === 0 ? (
                        <div className="p-4 text-sm text-gray-400">
                          Önizleme için tablo seçip butona basın.
                        </div>
                      ) : (
                        <table className="min-w-full text-left text-xs">
                          <thead className="bg-gray-50 sticky top-0">
                            <tr>
                              {Object.keys(connectorPreview[0] || {}).map(
                                (key) => (
                                  <th
                                    key={key}
                                    className="px-3 py-2 font-medium text-gray-500 border-b border-gray-200"
                                  >
                                    {key}
                                  </th>
                                ),
                              )}
                            </tr>
                          </thead>
                          <tbody>
                            {connectorPreview.map((row, index) => (
                              <tr
                                key={index}
                                className="odd:bg-white even:bg-gray-50"
                              >
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
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
