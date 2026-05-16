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
const defaultAlgorithms = ["levenshtein", "jaro"];

type Settings = {
  weights: typeof defaultWeights;
  thresholds: typeof defaultThresholds;
  algorithms: string[];
  mukerrer_merge_min_reviewers: number;
};

export default function Ayarlar() {
  const [weights, setWeights] = useState(defaultWeights);
  const [thresholds, setThresholds] = useState(defaultThresholds);
  const [algorithms, setAlgorithms] = useState<string[]>(defaultAlgorithms);
  const [saved, setSaved] = useState(false);
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
        setAlgorithms(
          Array.isArray(parsed.algorithms) ? parsed.algorithms : defaultAlgorithms,
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
  const weightsValid = totalWeight === 100;

  const handleSave = async () => {
    setLoading(true);
    setSaveError(false);
    const settings: Settings = {
      weights,
      thresholds,
      algorithms,
      mukerrer_merge_min_reviewers: 1,
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

  const handleResetWeights = () => setWeights(defaultWeights);

  return (
    <DashboardLayout>
      <Header
        title="Ayarlar"
        subtitle="Eşleştirme kurallarını ve sistem tercihlerini buradan yönetin"
        actions={
          <button
            type="button"
            onClick={handleSave}
            disabled={initialLoading || loading || !weightsValid}
            className={`ui-btn-primary ui-focus-ring whitespace-nowrap disabled:opacity-50 ${
              saved
                ? "!bg-emerald-600 !from-emerald-600 !to-emerald-700 hover:!from-emerald-500 hover:!to-emerald-600"
                : ""
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
            />
            {saved ? "Kaydedildi" : loading ? "Kaydediliyor..." : "Değişiklikleri Kaydet"}
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto bg-surface p-6 lg:p-8">
        <div className="mx-auto max-w-2xl space-y-4">
          {initialLoading && (
            <div className="ui-card p-10 text-center text-sm text-slate-500">
              <i className="ri-loader-4-line mb-3 block animate-spin text-2xl text-primary-600" />
              Ayarlar yükleniyor...
            </div>
          )}

          {saveError && (
            <div className="flex items-center gap-3 rounded-xl border border-danger-200 bg-danger-50 p-4">
              <i className="ri-error-warning-fill text-lg text-danger-600" />
              <p className="text-sm text-danger-700">
                Değişiklikler kaydedilemedi. Lütfen tekrar deneyin.
              </p>
            </div>
          )}

          {!initialLoading && !weightsValid && (
            <div className="flex items-start gap-3 rounded-xl border border-amber-200/80 bg-amber-50/90 p-4">
              <i className="ri-alert-line mt-0.5 text-lg text-amber-600" />
              <p className="text-sm text-amber-900">
                Alan ağırlıklarının toplamı %100 olmalı. Şu an:{" "}
                <span className="font-semibold tabular-nums">%{totalWeight}</span>
              </p>
            </div>
          )}

          {!initialLoading && (
            <section className="ui-card overflow-hidden shadow-card-lg">
              <div className="border-b border-slate-100 bg-gradient-to-r from-primary-50/80 via-white to-white px-6 py-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-sm">
                      <i className="ri-scales-3-line text-lg" />
                    </div>
                    <div>
                      <h2 className="text-base font-semibold text-slate-900">Alan Ağırlıkları</h2>
                      <p className="mt-0.5 text-sm text-slate-500">
                        Mükerrer tespitte alanların göreli önemi
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`rounded-lg px-2.5 py-1 text-xs font-semibold tabular-nums ${
                        weightsValid
                          ? "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200/80"
                          : "bg-amber-50 text-amber-900 ring-1 ring-amber-200/80"
                      }`}
                    >
                      Toplam %{totalWeight}
                    </span>
                    <button
                      type="button"
                      onClick={handleResetWeights}
                      className="text-xs font-medium text-primary-700 transition-colors hover:text-primary-800"
                    >
                      Varsayılana dön
                    </button>
                  </div>
                </div>
              </div>

              <div className="border-b border-slate-100 bg-slate-50/60 px-6 py-3">
                <p className="text-xs leading-relaxed text-slate-600">
                  Kaydettiğinizde değerler veritabanına yazılır ve{" "}
                  <strong className="font-medium text-slate-800">sonraki tespit işlerinde</strong>{" "}
                  kullanılır. Mevcut tespit sonuçları otomatik güncellenmez.
                </p>
              </div>

              <div className="space-y-5 px-6 py-6">
                {Object.entries(weights).map(([key, val]) => (
                  <div key={key}>
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <label className="text-sm font-medium text-slate-800">
                        {weightLabels[key] ?? key}
                      </label>
                      <span
                        className={`text-sm font-semibold tabular-nums ${
                          weightsValid ? "text-primary-700" : "text-amber-700"
                        }`}
                      >
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
                      className="h-2 w-full cursor-pointer accent-primary-600"
                      aria-label={`${weightLabels[key] ?? key} ağırlığı`}
                    />
                    <div className="mt-1 flex justify-between text-[11px] font-medium text-slate-400">
                      <span>0</span>
                      <span>60</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
