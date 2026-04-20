import { useState, useEffect, useRef } from "react";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { mockDuplicateGroups, type DuplicateGroup } from "../../mocks/records";
import { detectDuplicatesFromFileWithOptions, type DetectDuplicateResponse } from "../../services/api";

const algorithms = [
  { id: "levenshtein", label: "Levenshtein", desc: "Karakter düzenleme mesafesi" },
  { id: "jaro", label: "Jaro-Winkler", desc: "Önek ağırlıklı benzerlik" },
  { id: "soundex", label: "Soundex", desc: "Fonetik eşleştirme" },
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

  const toggleAlgo = (id: string) => {
    setSelectedAlgo((prev) =>
      prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id]
    );
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setErrorMessage("");
      setStatusMessage("");
    }
  };

  const handleStart = async () => {
    if (!selectedFile) {
      setErrorMessage("Lütfen önce bir dosya seçin");
      return;
    }

    setRunning(true);
    setDone(false);
    setProgress(0);
    setErrorMessage("");
    setStatusMessage("");
    setRealResults(null);

    // Simulate progress
    const progressInterval = setInterval(() => {
      setProgress((p) => Math.min(p + Math.floor(Math.random() * 8) + 3, 90));
    }, 150);

    try {
      const result = await detectDuplicatesFromFileWithOptions(selectedFile, {
        minRulesToMatch: Math.ceil((threshold / 100) * 4),
        saveToDb: true,
        algorithms: selectedAlgo,
        threshold: threshold,
      });

      if (typeof result.uploadId === "number") {
        localStorage.setItem("lastDetectUploadId", String(result.uploadId));
      }
      
      setRealResults(result);
      setProgress(100);
      setDone(true);
      setStatusMessage(
        `Tespit tamamlandı — ${result.duplicatePairs} mükerrer grup bulundu${
          typeof result.uploadId === "number" ? ` (Upload ID: ${result.uploadId})` : ""
        }`,
      );
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Tespit sırasında hata oluştu");
      setProgress(0);
    } finally {
      clearInterval(progressInterval);
      setRunning(false);
    }
  };

  // Convert real results to display format
  const results: DuplicateGroup[] = done
    ? onlySadeceMuhatap
      ? (realResults?.duplicates
          ?.filter((d) => d["L_Ad Soyad"] === d["R_Ad Soyad"] && d["L_TC"] === d["R_TC"])
          .map((d, i) => ({
            id: `MG-${String(i + 1).padStart(3, "0")}`,
            records: [
              {
                adSoyad: String(d["L_Ad Soyad"] || ""),
                tcKimlikNo: String(d["L_TC"] || ""),
                telefon: String(d["L_Telefon"] || ""),
                email: String(d["L_E-mail"] || ""),
                sehir: String(d["L_Şehir"] || ""),
                muhatapNo: String(d["L_Telefon"] || "").slice(-4),
              },
              {
                adSoyad: String(d["R_Ad Soyad"] || ""),
                tcKimlikNo: String(d["R_TC"] || ""),
                telefon: String(d["R_Telefon"] || ""),
                email: String(d["R_E-mail"] || ""),
                sehir: String(d["R_Şehir"] || ""),
                muhatapNo: String(d["R_Telefon"] || "").slice(-4),
              },
            ],
            score: (d.score as number) || 85,
            decision: "bekleyen" as const,
          })) || [])
      : (realResults?.duplicates
          ?.map((d, i) => ({
            id: `MG-${String(i + 1).padStart(3, "0")}`,
            records: [
              {
                adSoyad: String(d["L_Ad Soyad"] || ""),
                tcKimlikNo: String(d["L_TC"] || ""),
                telefon: String(d["L_Telefon"] || ""),
                email: String(d["L_E-mail"] || ""),
                sehir: String(d["L_Şehir"] || ""),
                muhatapNo: String(d["L_Telefon"] || "").slice(-4),
              },
              {
                adSoyad: String(d["R_Ad Soyad"] || ""),
                tcKimlikNo: String(d["R_TC"] || ""),
                telefon: String(d["R_Telefon"] || ""),
                email: String(d["R_E-mail"] || ""),
                sehir: String(d["R_Şehir"] || ""),
                muhatapNo: String(d["R_Telefon"] || "").slice(-4),
              },
            ],
            score: (d.score as number) || 85,
            decision: "bekleyen" as const,
          })) || [])
    : mockDuplicateGroups;

  return (
    <DashboardLayout>
      <Header
        title="Mükerrer Tespit"
        subtitle="Fuzzy matching algoritmaları ile benzer kayıtları tespit edin"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded">
                Backend: Erişilemiyor
              </span>
            )}
            <button
              onClick={handleStart}
              disabled={running || !selectedFile}
              className="flex items-center gap-2 bg-red-600 text-white text-sm font-medium px-5 py-2 rounded-lg hover:bg-red-700 disabled:opacity-60 cursor-pointer transition-colors whitespace-nowrap"
            >
              <i className={running ? "ri-loader-4-line animate-spin" : "ri-radar-line"}></i>
              {running ? `Taranıyor... %${progress}` : "Tespiti Başlat"}
            </button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* File Upload */}
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Dosya Seç (Normalize Edilmiş Veri)</h3>
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
            Önce Veri Normalizasyon sayfasından verilerinizi normalize edin, sonra buraya yükleyin.
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

        {/* Config */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Algoritma */}
          <div className="bg-white rounded-xl p-5 border border-gray-100 lg:col-span-2">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">Algoritma Seçimi</h3>
            <div className="grid grid-cols-3 gap-3">
              {algorithms.map((a) => {
                const active = selectedAlgo.includes(a.id);
                return (
                  <button
                    key={a.id}
                    onClick={() => toggleAlgo(a.id)}
                    className={`p-4 rounded-xl border-2 text-left cursor-pointer transition-all ${
                      active ? "border-red-500 bg-red-50" : "border-gray-100 hover:border-gray-200"
                    }`}
                  >
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2 ${active ? "bg-red-100" : "bg-gray-100"}`}>
                      <i className={`ri-cpu-line text-base ${active ? "text-red-600" : "text-gray-400"}`}></i>
                    </div>
                    <p className={`text-sm font-semibold ${active ? "text-red-700" : "text-gray-700"}`}>{a.label}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{a.desc}</p>
                    {active && <div className="mt-2 w-2 h-2 rounded-full bg-red-500"></div>}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Eşik */}
          <div className="bg-white rounded-xl p-5 border border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">Benzerlik Eşiği</h3>
            <div className="text-center mb-4">
              <span className="text-4xl font-bold text-red-600">%{threshold}</span>
              <p className="text-xs text-gray-400 mt-1">ve üzeri benzerlik tespit edilecek</p>
            </div>
            <input
              type="range"
              min={50}
              max={100}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full accent-red-600 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-1">
              <span>%50 Geniş</span>
              <span>%100 Tam</span>
            </div>
            <div className="mt-4 p-3 bg-gray-50 rounded-lg">
              <p className="text-[11px] text-gray-500">
                <strong className="text-gray-700">Tahmini sonuç:</strong>{" "}
                {threshold < 65 ? "~8.200" : threshold < 80 ? "~3.247" : "~840"} mükerrer
              </p>
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        {(running || done) && (
          <div className={`rounded-xl p-4 border flex items-center gap-4 ${done ? "bg-green-50 border-green-100" : "bg-red-50 border-red-100"}`}>
            <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${done ? "bg-green-100" : "bg-red-100"}`}>
              <i className={`text-lg ${done ? "ri-checkbox-circle-fill text-green-600" : "ri-loader-4-line text-red-600 animate-spin"}`}></i>
            </div>
            <div className="flex-1">
              <p className={`text-sm font-semibold ${done ? "text-green-700" : "text-red-700"}`}>
                {done 
                  ? statusMessage || `Tespit tamamlandı — ${realResults?.duplicatePairs || mockDuplicateGroups.length} mükerrer grup bulundu`
                  : `${realResults?.totalRecords || "124.836"} kayıt taranıyor... %${progress}`}
              </p>
              <div className="mt-1.5 bg-white/70 rounded-full h-1.5 overflow-hidden">
                <div className={`h-1.5 rounded-full transition-all duration-150 ${done ? "bg-green-500" : "bg-red-500"}`} style={{ width: `${progress}%` }} />
              </div>
            </div>
          </div>
        )}

        {/* Results */}
        {done && (
          <div className="bg-white rounded-xl border border-gray-100">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-50">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Tespit Sonuçları</h3>
                <p className="text-xs text-gray-400 mt-0.5">{results.length} mükerrer grup</p>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <span className="text-xs text-gray-600 whitespace-nowrap">Sadece Muhatap No Farklı</span>
                <button
                  onClick={() => setOnlySadeceMuhatap((v) => !v)}
                  className={`relative w-11 min-w-[44px] h-5 rounded-full overflow-hidden flex items-center transition-colors cursor-pointer ${onlySadeceMuhatap ? "bg-red-500" : "bg-gray-200"}`}
                >
                  <span className={`absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow-sm transition-transform ${onlySadeceMuhatap ? "translate-x-6" : "translate-x-0"}`} />
                </button>
              </label>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50/70">
                    <th className="text-left text-gray-400 font-medium px-5 py-3">Grup</th>
                    <th className="text-left text-gray-400 font-medium px-4 py-3">Kayıt 1</th>
                    <th className="text-left text-gray-400 font-medium px-4 py-3">Kayıt 2</th>
                    <th className="text-center text-gray-400 font-medium px-4 py-3">Benzerlik</th>
                    <th className="text-left text-gray-400 font-medium px-4 py-3">Durum</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {results.map((g) => {
                    const scoreColor =
                      g.score >= 90 ? "text-red-600 bg-red-50" : g.score >= 80 ? "text-orange-500 bg-orange-50" : "text-yellow-600 bg-yellow-50";
                    const decisionMap: Record<string, string> = {
                      bekleyen: "bg-yellow-50 text-yellow-700",
                      onaylandi: "bg-green-50 text-green-700",
                      reddedildi: "bg-red-50 text-red-600",
                    };
                    const decisionLabel: Record<string, string> = {
                      bekleyen: "Bekleyen",
                      onaylandi: "Onaylandı",
                      reddedildi: "Reddedildi",
                    };
                    return (
                      <tr key={g.id} className="hover:bg-gray-50/50 transition-colors">
                        <td className="px-5 py-3.5 font-medium text-gray-700">{g.id}</td>
                        <td className="px-4 py-3.5">
                          <p className="font-medium text-gray-800">{g.records[0].adSoyad}</p>
                          <p className="text-gray-400">{g.records[0].muhatapNo}</p>
                        </td>
                        <td className="px-4 py-3.5">
                          <p className="font-medium text-gray-800">{g.records[1].adSoyad}</p>
                          <p className="text-gray-400">{g.records[1].muhatapNo}</p>
                        </td>
                        <td className="px-4 py-3.5 text-center">
                          <span className={`inline-block px-2.5 py-1 rounded-full font-bold text-sm ${scoreColor}`}>
                            %{g.score.toFixed(1)}
                          </span>
                        </td>
                        <td className="px-4 py-3.5">
                          <span className={`inline-block px-2.5 py-1 rounded-full text-[11px] font-medium ${decisionMap[g.decision]}`}>
                            {decisionLabel[g.decision]}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {results.length === 0 && (
                <div className="text-center py-10 text-gray-400 text-sm">
                  Bu filtreyle eşleşen kayıt bulunamadı.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}