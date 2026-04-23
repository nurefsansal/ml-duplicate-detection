import { useEffect, useRef, useState } from "react";

import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { mockDuplicateGroups } from "../../mocks/records";
import {
  detectDuplicatesFromFileWithOptions,
  type DetectDuplicateResponse,
} from "../../services/api";
import {
  finalDecisionTone,
  mapDetectPairToView,
  mapMockGroupToView,
  type UiDuplicatePair,
} from "../../utils/duplicatePairView";

const algorithms = [
  { id: "levenshtein", label: "Levenshtein", desc: "Karakter duzenleme mesafesi" },
  { id: "jaro", label: "Jaro-Winkler", desc: "Onek agirlikli benzerlik" },
  { id: "soundex", label: "Soundex", desc: "Fonetik eslestirme" },
];

export default function MukerrerTespit() {
  const [selectedAlgo, setSelectedAlgo] = useState<string[]>(["levenshtein", "jaro"]);
  const [threshold, setThreshold] = useState(75);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);
  const [onlySadeceMuhatap, setOnlySadeceMuhatap] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const [realResults, setRealResults] = useState<DetectDuplicateResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let mounted = true;
    import("../../services/api")
      .then(({ healthCheck }) => healthCheck())
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

  const toggleAlgo = (id: string) => {
    setSelectedAlgo((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setErrorMessage("");
      setStatusMessage("");
    }
  };

  const handleStart = async () => {
    if (!selectedFile) {
      setErrorMessage("Lutfen once bir dosya secin");
      return;
    }

    setRunning(true);
    setDone(false);
    setProgress(0);
    setErrorMessage("");
    setStatusMessage("");
    setRealResults(null);

    const progressInterval = window.setInterval(() => {
      setProgress((value) => Math.min(value + Math.floor(Math.random() * 8) + 3, 90));
    }, 150);

    try {
      const result = await detectDuplicatesFromFileWithOptions(selectedFile, {
        minRulesToMatch: Math.ceil((threshold / 100) * 4),
        saveToDb: true,
        algorithms: selectedAlgo,
        threshold,
      });

      if (typeof result.uploadId === "number") {
        localStorage.setItem("lastDetectUploadId", String(result.uploadId));
      }

      setRealResults(result);
      setProgress(100);
      setDone(true);
      setStatusMessage(
        `Tespit tamamlandi - ${result.duplicatePairs} aday bulundu${
          typeof result.uploadId === "number" ? ` (Upload ID: ${result.uploadId})` : ""
        }`,
      );
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Tespit sirasinda hata olustu",
      );
      setProgress(0);
    } finally {
      clearInterval(progressInterval);
      setRunning(false);
    }
  };

  const mockResults = mockDuplicateGroups.map(mapMockGroupToView);
  const realViews = (realResults?.duplicates || []).map(mapDetectPairToView);

  const results: UiDuplicatePair[] = done
    ? (onlySadeceMuhatap
        ? realViews.filter(
            (pair) =>
              pair.fieldComparisons.fullName?.exactMatch &&
              pair.fieldComparisons.tc?.exactMatch,
          )
        : realViews)
    : mockResults;

  return (
    <DashboardLayout>
      <Header
        title="Mukerrer Tespit"
        subtitle="Splink tabanli alan karsilastirmalari ile benzer kayitlari tespit edin"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="rounded bg-red-50 px-2 py-1 text-xs text-red-600">
                Backend: Erisilemiyor
              </span>
            )}
            <button
              onClick={handleStart}
              disabled={running || !selectedFile}
              className="flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-lg bg-red-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-60"
            >
              <i className={running ? "ri-loader-4-line animate-spin" : "ri-radar-line"} />
              {running ? `Taraniyor... %${progress}` : "Tespiti Baslat"}
            </button>
          </div>
        }
      />

      <div className="flex-1 space-y-5 overflow-y-auto p-6">
        <div className="rounded-xl border border-gray-100 bg-white p-5">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">
            Dosya Sec (Normalize Edilmis Veri)
          </h3>
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
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50"
            >
              <i className="ri-folder-open-line" />
              Dosya Sec
            </button>
            {selectedFile && (
              <span className="text-sm text-gray-600">
                Secilen: <span className="font-medium">{selectedFile.name}</span>
                <span className="ml-1 text-gray-400">
                  ({(selectedFile.size / 1024).toFixed(1)} KB)
                </span>
              </span>
            )}
          </div>
          <p className="mt-2 text-xs text-gray-400">
            Tespit sonucu artik Splink alan karsilastirmalari ve is kurallariyla
            birlikte degerlendiriliyor.
          </p>
        </div>

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

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <div className="rounded-xl border border-gray-100 bg-white p-5 lg:col-span-2">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Algoritma Secimi</h3>
            <div className="grid grid-cols-3 gap-3">
              {algorithms.map((algorithm) => {
                const active = selectedAlgo.includes(algorithm.id);
                return (
                  <button
                    key={algorithm.id}
                    onClick={() => toggleAlgo(algorithm.id)}
                    className={`cursor-pointer rounded-xl border-2 p-4 text-left transition-all ${
                      active
                        ? "border-red-500 bg-red-50"
                        : "border-gray-100 hover:border-gray-200"
                    }`}
                  >
                    <div
                      className={`mb-2 flex h-8 w-8 items-center justify-center rounded-lg ${
                        active ? "bg-red-100" : "bg-gray-100"
                      }`}
                    >
                      <i
                        className={`ri-cpu-line text-base ${
                          active ? "text-red-600" : "text-gray-400"
                        }`}
                      />
                    </div>
                    <p
                      className={`text-sm font-semibold ${
                        active ? "text-red-700" : "text-gray-700"
                      }`}
                    >
                      {algorithm.label}
                    </p>
                    <p className="mt-0.5 text-xs text-gray-400">{algorithm.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="rounded-xl border border-gray-100 bg-white p-5">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Benzerlik Esigi</h3>
            <div className="mb-4 text-center">
              <span className="text-4xl font-bold text-red-600">%{threshold}</span>
              <p className="mt-1 text-xs text-gray-400">
                ve uzeri olasiliklar one cikarilacak
              </p>
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
              <span>%50 Genis</span>
              <span>%100 Tam</span>
            </div>
          </div>
        </div>

        {(running || done) && (
          <div
            className={`flex items-center gap-4 rounded-xl border p-4 ${
              done ? "border-green-100 bg-green-50" : "border-red-100 bg-red-50"
            }`}
          >
            <div
              className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg ${
                done ? "bg-green-100" : "bg-red-100"
              }`}
            >
              <i
                className={`text-lg ${
                  done
                    ? "ri-checkbox-circle-fill text-green-600"
                    : "ri-loader-4-line animate-spin text-red-600"
                }`}
              />
            </div>
            <div className="flex-1">
              <p
                className={`text-sm font-semibold ${
                  done ? "text-green-700" : "text-red-700"
                }`}
              >
                {done
                  ? statusMessage || `Tespit tamamlandi - ${results.length} aday bulundu`
                  : `${realResults?.totalRecords || "Veri"} taraniyor... %${progress}`}
              </p>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/70">
                <div
                  className={`h-1.5 rounded-full transition-all duration-150 ${
                    done ? "bg-green-500" : "bg-red-500"
                  }`}
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {done && (
          <div className="rounded-xl border border-gray-100 bg-white">
            <div className="flex items-center justify-between border-b border-gray-50 px-5 py-4">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Tespit Sonuclari</h3>
                <p className="mt-0.5 text-xs text-gray-400">
                  {results.length} aday cift
                </p>
              </div>
              <label className="flex cursor-pointer items-center gap-2">
                <span className="whitespace-nowrap text-xs text-gray-600">
                  Sadece ad ve TC tam eslesenler
                </span>
                <button
                  onClick={() => setOnlySadeceMuhatap((value) => !value)}
                  className={`relative flex h-5 w-11 min-w-[44px] cursor-pointer items-center overflow-hidden rounded-full transition-colors ${
                    onlySadeceMuhatap ? "bg-red-500" : "bg-gray-200"
                  }`}
                >
                  <span
                    className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${
                      onlySadeceMuhatap ? "translate-x-6" : "translate-x-0"
                    }`}
                  />
                </button>
              </label>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50/70">
                    <th className="px-5 py-3 text-left font-medium text-gray-400">Grup</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Kayit 1</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Kayit 2</th>
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
                            {pair.records[0].telefon || "-"} - {pair.records[0].email || "-"}
                          </p>
                        </td>
                        <td className="px-4 py-3.5">
                          <p className="font-medium text-gray-800">{pair.records[1].adSoyad}</p>
                          <p className="text-gray-400">
                            {pair.records[1].telefon || "-"} - {pair.records[1].email || "-"}
                          </p>
                        </td>
                        <td className="px-4 py-3.5 text-center">
                          <span
                            className={`inline-block rounded-full px-2.5 py-1 text-sm font-bold ${scoreColor}`}
                          >
                            %{pair.score.toFixed(1)}
                          </span>
                        </td>
                        <td className="px-4 py-3.5">
                          <span
                            className={`inline-block rounded-full px-2.5 py-1 text-[11px] font-medium ${finalDecisionTone(pair.finalDecision)}`}
                          >
                            {pair.finalDecisionLabel}
                          </span>
                          <p className="mt-1 text-[11px] text-gray-400">
                            {pair.ruleReasons[0] || "Ek aciklama yok"}
                          </p>
                        </td>
                        <td className="px-4 py-3.5 text-gray-500">
                          {pair.decisionSource === "splink_plus_rules"
                            ? "Splink + kurallar"
                            : pair.decisionSource}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {results.length === 0 && (
                <div className="py-10 text-center text-sm text-gray-400">
                  Bu filtreyle eslesen kayit bulunamadi.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
