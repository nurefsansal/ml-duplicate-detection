import { useState, useEffect, useRef } from "react";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { mockDuplicateGroups, type DuplicateGroup } from "../../mocks/records";
import { detectDuplicatesFromFileWithOptions, type DetectDuplicateResponse } from "../../services/api";

export default function MukerrerKayitlar() {
  const [search, setSearch] = useState("");
  const [filterDecision, setFilterDecision] = useState("tumu");
  const [selected, setSelected] = useState<string[]>([]);
  const [detailGroup, setDetailGroup] = useState<DuplicateGroup | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [realData, setRealData] = useState<DuplicateGroup[]>([]);
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

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      loadDataFromFile(file);
    }
  };

  const loadDataFromFile = async (file: File) => {
    setLoading(true);
    try {
      const result = await detectDuplicatesFromFileWithOptions(file, {
        minRulesToMatch: 2,
        saveToDb: true,
      });

      if (typeof result.uploadId === "number") {
        localStorage.setItem("lastDetectUploadId", String(result.uploadId));
      }
      
      // Convert API response to DuplicateGroup format
      const groups: DuplicateGroup[] = (result.duplicates || []).map((d, i) => ({
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
        matchDetails: { adSoyad: 85, tcKimlikNo: 85, telefon: 85, email: 85, sehir: 85 },
      }));
      
      setRealData(groups);
    } catch (error) {
      console.error("Error loading data:", error);
    } finally {
      setLoading(false);
    }
  };

  // Use real data if available, otherwise mock
  const data = realData.length > 0 ? realData : mockDuplicateGroups;

  const filtered = data.filter((g) => {
    const matchSearch =
      !search ||
      g.records.some(
        (r) =>
          r.adSoyad.toLowerCase().includes(search.toLowerCase()) ||
          r.muhatapNo.toLowerCase().includes(search.toLowerCase()) ||
          r.tcKimlikNo.includes(search)
      );
    const matchDecision = filterDecision === "tumu" || g.decision === filterDecision;
    return matchSearch && matchDecision;
  });

  const toggleSelect = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  
  const toggleAll = () =>
    setSelected(selected.length === filtered.length ? [] : filtered.map((g) => g.id));

  const handleBulkApprove = () => {
    setRealData((prev) =>
      prev.map((g) => (selected.includes(g.id) ? { ...g, decision: "onaylandi" as const } : g))
    );
    setSelected([]);
  };

  const handleBulkReject = () => {
    setRealData((prev) =>
      prev.map((g) => (selected.includes(g.id) ? { ...g, decision: "reddedildi" as const } : g))
    );
    setSelected([]);
  };

  const decisionBadge: Record<string, string> = {
    bekleyen: "bg-yellow-50 text-yellow-700 border border-yellow-200",
    onaylandi: "bg-green-50 text-green-700 border border-green-200",
    reddedildi: "bg-red-50 text-red-600 border border-red-200",
  };
  const decisionLabel: Record<string, string> = {
    bekleyen: "Bekleyen", onaylandi: "Onaylandı", reddedildi: "Reddedildi",
  };

  return (
    <DashboardLayout>
      <Header
        title="Mükerrer Kayıtlar"
        subtitle="Tespit edilen mükerrer kayıtları yönetin"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded">
                Backend: Erişilemiyor
              </span>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={handleFileSelect}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-2 text-sm text-gray-600 border border-gray-200 px-4 py-2 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors"
            >
              <i className="ri-folder-open-line"></i>
              {selectedFile ? selectedFile.name : "Veri Yükle"}
            </button>
            {selected.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">{selected.length} seçildi</span>
                <button 
                  onClick={handleBulkApprove}
                  className="flex items-center gap-1.5 text-xs bg-green-600 text-white px-3 py-2 rounded-lg hover:bg-green-700 cursor-pointer whitespace-nowrap"
                >
                  <i className="ri-checkbox-circle-line"></i> Toplu Onayla
                </button>
                <button 
                  onClick={handleBulkReject}
                  className="flex items-center gap-1.5 text-xs bg-red-600 text-white px-3 py-2 rounded-lg hover:bg-red-700 cursor-pointer whitespace-nowrap"
                >
                  <i className="ri-close-circle-line"></i> Toplu Reddet
                </button>
              </div>
            )}
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {/* Loading indicator */}
        {loading && (
          <div className="rounded-xl p-4 border bg-blue-50 border-blue-100 flex items-center gap-3">
            <i className="ri-loader-4-line text-blue-600 text-lg animate-spin"></i>
            <p className="text-sm text-blue-700">Veriler yükleniyor...</p>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          <div className="relative flex-1 w-full">
            <i className="ri-search-line absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm"></i>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Ad soyad, muhatap no veya TC ile ara..."
              className="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-red-400 focus:ring-1 focus:ring-red-100"
            />
          </div>
          <div className="flex gap-2 flex-wrap">
            {["tumu", "bekleyen", "onaylandi", "reddedildi"].map((v) => (
              <button
                key={v}
                onClick={() => setFilterDecision(v)}
                className={`text-xs px-4 py-2 rounded-lg cursor-pointer transition-colors whitespace-nowrap ${
                  filterDecision === v ? "bg-red-600 text-white" : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
                }`}
              >
                {v === "tumu" ? "Tümü" : decisionLabel[v]}
              </button>
            ))}
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50/70 border-b border-gray-100">
                  <th className="px-5 py-3 w-10">
                    <input
                      type="checkbox"
                      checked={selected.length === filtered.length && filtered.length > 0}
                      onChange={toggleAll}
                      className="accent-red-600 cursor-pointer"
                    />
                  </th>
                  <th className="text-left text-gray-400 font-medium px-4 py-3">Skor</th>
                  <th className="text-left text-gray-400 font-medium px-4 py-3">Kayıt 1 — Ad Soyad / TC</th>
                  <th className="text-left text-gray-400 font-medium px-4 py-3">Kayıt 2 — Ad Soyad / TC</th>
                  <th className="text-left text-gray-400 font-medium px-4 py-3">Telefon</th>
                  <th className="text-left text-gray-400 font-medium px-4 py-3">Durum</th>
                  <th className="text-center text-gray-400 font-medium px-4 py-3">İşlem</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((g) => {
                  const scoreColor = g.score >= 90 ? "text-red-600 bg-red-50" : g.score >= 80 ? "text-orange-500 bg-orange-50" : "text-yellow-600 bg-yellow-50";
                  return (
                    <tr key={g.id} className={`hover:bg-gray-50/50 transition-colors ${selected.includes(g.id) ? "bg-red-50/30" : ""}`}>
                      <td className="px-5 py-3.5">
                        <input
                          type="checkbox"
                          checked={selected.includes(g.id)}
                          onChange={() => toggleSelect(g.id)}
                          className="accent-red-600 cursor-pointer"
                        />
                      </td>
                      <td className="px-4 py-3.5">
                        <span className={`inline-block px-2.5 py-1 rounded-full font-bold text-sm ${scoreColor}`}>
                          %{g.score.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-4 py-3.5">
                        <p className="font-medium text-gray-800">{g.records[0].adSoyad}</p>
                        <p className="text-gray-400">{g.records[0].tcKimlikNo} · {g.records[0].muhatapNo}</p>
                      </td>
                      <td className="px-4 py-3.5">
                        <p className="font-medium text-gray-800">{g.records[1].adSoyad}</p>
                        <p className="text-gray-400">{g.records[1].tcKimlikNo} · {g.records[1].muhatapNo}</p>
                      </td>
                      <td className="px-4 py-3.5 text-gray-500">{g.records[0].telefon}</td>
                      <td className="px-4 py-3.5">
                        <span className={`inline-block px-2.5 py-1 rounded-full text-[11px] font-medium ${decisionBadge[g.decision]}`}>
                          {decisionLabel[g.decision]}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-center">
                        <button
                          onClick={() => setDetailGroup(g)}
                          className="text-xs text-red-600 font-medium hover:underline cursor-pointer whitespace-nowrap"
                        >
                          Detay
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="text-center py-10 text-gray-400 text-sm">Kayıt bulunamadı.</div>
            )}
          </div>
        </div>
      </div>

      {/* Detail Modal */}
      {detailGroup && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setDetailGroup(null)}>
          <div className="bg-white rounded-2xl w-full max-w-3xl max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div>
                <h2 className="text-base font-bold text-gray-900">Kayıt Karşılaştırma — {detailGroup.id}</h2>
                <p className="text-xs text-gray-400 mt-0.5">Benzerlik skoru: %{detailGroup.score.toFixed(1)}</p>
              </div>
              <button onClick={() => setDetailGroup(null)} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-100 cursor-pointer text-gray-500">
                <i className="ri-close-line text-lg"></i>
              </button>
            </div>
            <div className="p-6">
              {/* Score breakdown */}
              <div className="mb-5 p-4 bg-gray-50 rounded-xl">
                <p className="text-xs font-semibold text-gray-600 mb-3">Alan Bazlı Skor Kırılımı</p>
                <div className="grid grid-cols-5 gap-2">
                  {Object.entries(detailGroup.matchDetails || {}).map(([field, score]) => (
                    <div key={field} className="text-center">
                      <div className={`text-sm font-bold ${score >= 90 ? "text-green-600" : score >= 70 ? "text-yellow-600" : "text-red-500"}`}>
                        %{score}
                      </div>
                      <div className="text-[10px] text-gray-400 mt-0.5 capitalize">{field}</div>
                    </div>
                  ))}
                </div>
              </div>
              {/* Side by side */}
              <div className="grid grid-cols-2 gap-4">
                {detailGroup.records.map((rec, i) => (
                  <div key={i} className={`rounded-xl p-4 border-2 ${i === 0 ? "border-gray-200" : "border-red-200 bg-red-50/20"}`}>
                    <div className="flex items-center gap-2 mb-3">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${i === 0 ? "bg-gray-100 text-gray-600" : "bg-red-100 text-red-600"}`}>
                        Kayıt {i + 1}
                      </span>
                      <span className="text-xs text-gray-500">{rec.muhatapNo}</span>
                    </div>
                    {[
                      ["Ad Soyad", rec.adSoyad],
                      ["TC Kimlik", rec.tcKimlikNo],
                      ["Telefon", rec.telefon],
                      ["E-posta", rec.email],
                      ["Şehir", rec.sehir],
                      ["Doğum Tarihi", rec.dogumTarihi || "-"],
                      ["Adres", rec.adres || "-"],
                    ].map(([label, val]) => (
                      <div key={label} className="mb-2">
                        <p className="text-[10px] text-gray-400">{label}</p>
                        <p className="text-xs font-medium text-gray-800 break-words">{val}</p>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
              <div className="flex gap-3 mt-5">
                <button 
                  onClick={() => {
                    setRealData((prev) =>
                      prev.map((g) => (g.id === detailGroup.id ? { ...g, decision: "onaylandi" as const } : g))
                    );
                    setDetailGroup(null);
                  }}
                  className="flex-1 bg-green-600 text-white text-sm font-medium py-2.5 rounded-lg hover:bg-green-700 cursor-pointer whitespace-nowrap"
                >
                  <i className="ri-checkbox-circle-line mr-1.5"></i>Mükerrer Onayla
                </button>
                <button 
                  onClick={() => {
                    setRealData((prev) =>
                      prev.map((g) => (g.id === detailGroup.id ? { ...g, decision: "reddedildi" as const } : g))
                    );
                    setDetailGroup(null);
                  }}
                  className="flex-1 border border-red-200 text-red-600 text-sm font-medium py-2.5 rounded-lg hover:bg-red-50 cursor-pointer whitespace-nowrap"
                >
                  <i className="ri-close-circle-line mr-1.5"></i>Reddet
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}