import { useState, useEffect } from "react";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
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
  /** 1 = tek onay (varsayılan); 2+ = Mükerrer Kayıtlar’da ek onay kutusu */
  mukerrer_merge_min_reviewers: number;
};

export default function Ayarlar() {
  const [weights, setWeights] = useState(defaultWeights);
  const [thresholds, setThresholds] = useState(defaultThresholds);
  const [algo, setAlgo] = useState<string[]>(["levenshtein", "jaro"]);
  const [saved, setSaved] = useState(false);
  const [mergeMinReviewers, setMergeMinReviewers] = useState(1);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [saveError, setSaveError] = useState(false);

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
        setMergeMinReviewers(
          Math.max(
            1,
            Math.min(10, Number(parsed.mukerrer_merge_min_reviewers ?? 1)),
          ),
        );
      })
      .catch((e) => {
        console.error("Error loading settings:", e);
      })
      .finally(() => {
        if (alive) setInitialLoading(false);
      });
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
      mukerrer_merge_min_reviewers: mergeMinReviewers,
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

  return (
    <DashboardLayout>
      <Header
        title="Ayarlar"
        subtitle="Eşleştirme kurallarını ve sistem tercihlerini buradan yönetin"
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
            {saved ? "Kaydedildi" : loading ? "Kaydediliyor..." : "Değişiklikleri Kaydet"}
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
            <p className="text-sm text-red-700">Değişiklikler kaydedilemedi</p>
          </div>
        )}

        {/* Warning if weights don't sum to 100 */}
        {!initialLoading && totalWeight !== 100 && (
          <div className="rounded-xl p-4 border bg-yellow-50 border-yellow-100 flex items-center gap-3">
            <i className="ri-alert-line text-yellow-600 text-lg"></i>
            <p className="text-sm text-yellow-700">
              Alan ağırlıklarının toplamı %100 olmalı. Şu an:{" "}
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
                    (toplam 100 olmalı)
                  </p>
                </div>
                <button
                  onClick={handleResetWeights}
                  className="text-xs text-red-600 hover:underline cursor-pointer whitespace-nowrap"
                >
                  Varsayılana Dön
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

            {/* Eşik değerleri kaldırıldı: tespit sonrası kararlar yalnızca manuel incelemede verilir */}
            {false && (
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
              <div className="mb-4 rounded-lg border border-blue-100 bg-blue-50/80 p-3 text-xs text-blue-900">
                <p className="font-medium text-blue-950">Yeni mükerrer tespit çalıştırmaları</p>
                <p className="mt-1 text-blue-900/90">
                  Buradaki olasılık eşikleri ve ağırlıklar, kaydettiğinizde veritabanına yazılır ve{" "}
                  <strong>sonraki tespit (detect) işlerinde</strong> Splink + kural motoru tarafından
                  kullanılır. Daha önce oluşturulmuş <code>match_candidates</code> satırlarını geriye
                  dönük değiştirmez; gerekirse tespiti aynı yükleme için yeniden çalıştırın.
                </p>
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
            )}

            {/* Algoritma */}
            {false && (
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
            )}

            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-1">
                Birleştirme İncelemesi
              </h3>
              <p className="text-xs text-gray-400 mb-4">
                Mükerrer kayıtlar ekranında birleştirme onayı kuralları
              </p>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">
                  Birleştirme için gereken en az onay
                </label>
                <input
                  type="number"
                  value={mergeMinReviewers}
                  onChange={(e) =>
                    setMergeMinReviewers(
                      Math.max(1, Math.min(10, Number(e.target.value) || 1)),
                    )
                  }
                  min={1}
                  max={10}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400"
                />
                <p className="mt-1 text-[11px] text-gray-500">
                  1 ise tek kullanıcı kaydedebilir. 2 ve üzeri olduğunda inceleme ekranında ek onay
                  kutusu ve <code className="text-[10px]">co_review_acknowledged</code> zorunluluğu.
                </p>
              </div>
            </div>

          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
