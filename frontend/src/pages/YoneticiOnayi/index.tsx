import { useState, useEffect, useRef } from "react";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { mockDuplicateGroups, type DuplicateGroup } from "../../mocks/records";
import { auditLog, yoneticiler, type AuditLogItem } from "../../mocks/approval";
import {
  approvePendingMatch,
  getPendingMatches,
  rejectPendingMatch,
  type AdminPendingMatch,
} from "../../services/api";

type TabType = "bekleyen" | "onaylandi" | "reddedildi";
type UiDuplicateGroup = DuplicateGroup & {
  backendMatchId?: number;
  decisionReason?: string;
};

function scoreFromFraction(value: unknown, fallback = 0): number {
  const num = Number(value);
  if (Number.isNaN(num)) {
    return fallback;
  }
  return Math.max(0, Math.min(100, Math.round(num * 100)));
}

function formatPendingToGroup(match: AdminPendingMatch, index: number): UiDuplicateGroup {
  const details = {
    adSoyad: scoreFromFraction(match.features?.name_similarity, 0),
    telefon: Number(match.features?.phone_exact_match) === 1 ? 100 : 0,
    email: Number(match.features?.email_similarity ?? 0),
    sehir: Number(match.features?.city_exact_match) === 1 ? 100 : 0,
  };

  return {
    id: `MG-${String(index + 1).padStart(3, "0")}`,
    backendMatchId: match.id,
    decisionReason: match.decision_reason ?? undefined,
    records: [
      {
        adSoyad: String(match.donor1_name || ""),
        tcKimlikNo: "",
        telefon: String(match.donor1_phone || ""),
        email: String(match.donor1_email || ""),
        sehir: "",
        muhatapNo: String(match.donor1_id),
      },
      {
        adSoyad: String(match.donor2_name || ""),
        tcKimlikNo: "",
        telefon: String(match.donor2_phone || ""),
        email: String(match.donor2_email || ""),
        sehir: "",
        muhatapNo: String(match.donor2_id),
      },
    ],
    score: scoreFromFraction(match.ml_score, 85),
    decision: "bekleyen",
    matchDetails: details,
  };
}

export default function YoneticiOnayi() {
  const [tab, setTab] = useState<TabType>("bekleyen");
  const [detailGroup, setDetailGroup] = useState<UiDuplicateGroup | null>(null);
  const [searchAudit, setSearchAudit] = useState("");
  const [filterYonetici, setFilterYonetici] = useState("Tümü");
  const [loading, setLoading] = useState(false);
  const [realData, setRealData] = useState<UiDuplicateGroup[]>([]);
  const [realAuditLog, setRealAuditLog] = useState<AuditLogItem[]>([]);
  const [decisionNote, setDecisionNote] = useState("");
  const [apiError, setApiError] = useState("");
  const [lastUploadId, setLastUploadId] = useState<number | null>(null);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const isMountedRef = useRef(true);

  const refreshPendingMatches = async (uploadId?: number) => {
    setLoading(true);
    setApiError("");

    try {
      const response = await getPendingMatches({
        uploadId,
        limit: 100,
      });
      const mapped = (response.matches || []).map(formatPendingToGroup);

      if (!isMountedRef.current) {
        return;
      }

      setRealData(mapped);
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }
      setApiError(error instanceof Error ? error.message : "Pending kayıtlar alınamadı.");
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  // Backend health check
  useEffect(() => {
    isMountedRef.current = true;

    import("../../services/api")
      .then(({ healthCheck }) => healthCheck())
      .then(() => {
        if (!isMountedRef.current) {
          return;
        }
        setBackendHealthy(true);

        const storedUpload = localStorage.getItem("lastDetectUploadId");
        const parsedUpload = storedUpload ? Number(storedUpload) : NaN;
        const uploadId = Number.isFinite(parsedUpload) ? parsedUpload : undefined;
        setLastUploadId(uploadId ?? null);
        refreshPendingMatches(uploadId);
      })
      .catch(() => {
        if (isMountedRef.current) {
          setBackendHealthy(false);
        }
      });

    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Use real data if available, otherwise mock
  const data: UiDuplicateGroup[] =
    realData.length > 0 ? realData : (mockDuplicateGroups as UiDuplicateGroup[]);
  const logData = realAuditLog.length > 0 ? realAuditLog : auditLog;

  const bekleyen = data.filter((g) => g.decision === "bekleyen");
  const onaylandi = data.filter((g) => g.decision === "onaylandi");
  const reddedildi = data.filter((g) => g.decision === "reddedildi");

  const filteredLog = logData.filter((l) => {
    const matchSearch = !searchAudit || l.grup.toLowerCase().includes(searchAudit.toLowerCase()) || l.yonetici.toLowerCase().includes(searchAudit.toLowerCase());
    const matchYonetici = filterYonetici === "Tümü" || l.yonetici === filterYonetici;
    return matchSearch && matchYonetici;
  });

  const handleApprove = async (groupId: string) => {
    const target = data.find((g) => g.id === groupId);
    if (!target?.backendMatchId) {
      return;
    }

    setLoading(true);
    setApiError("");

    const now = new Date().toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

    try {
      await approvePendingMatch({
        matchId: target.backendMatchId,
        approvedBy: "Ahmet Yılmaz",
        mergeIntoEntity: true,
      });

      // Update local UI state
      setRealData((prev) => prev.filter((g) => g.id !== groupId));

      // Add to audit log
      const newLog: AuditLogItem = {
        id: `LOG-${String(realAuditLog.length + auditLog.length + 1).padStart(3, "0")}`,
        grup: groupId,
        yonetici: "Ahmet Yılmaz",
        islem: "Onaylandı",
        tarih: now,
        not: decisionNote || "Onaylandı",
      };
      setRealAuditLog((prev) => [newLog, ...prev]);

      setDetailGroup(null);
      setDecisionNote("");
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Onay işlemi başarısız.");
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async (groupId: string) => {
    const target = data.find((g) => g.id === groupId);
    if (!target?.backendMatchId) {
      return;
    }

    setLoading(true);
    setApiError("");

    const now = new Date().toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

    try {
      await rejectPendingMatch({
        matchId: target.backendMatchId,
        rejectedBy: "Ahmet Yılmaz",
        reason: decisionNote || "Reddedildi",
      });

      // Update local UI state
      setRealData((prev) => prev.filter((g) => g.id !== groupId));

      // Add to audit log
      const newLog: AuditLogItem = {
        id: `LOG-${String(realAuditLog.length + auditLog.length + 1).padStart(3, "0")}`,
        grup: groupId,
        yonetici: "Ahmet Yılmaz",
        islem: "Reddedildi",
        tarih: now,
        not: decisionNote || "Reddedildi",
      };
      setRealAuditLog((prev) => [newLog, ...prev]);

      setDetailGroup(null);
      setDecisionNote("");
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Reddetme işlemi başarısız.");
    } finally {
      setLoading(false);
    }
  };

  const refreshLabel = lastUploadId ? `Yenile (Upload ${lastUploadId})` : "Tümünü Yenile";

  const tabs: { key: TabType; label: string; count: number; color: string }[] = [
    { key: "bekleyen", label: "Bekleyen", count: bekleyen.length, color: "text-yellow-700 bg-yellow-50 border-yellow-200" },
    { key: "onaylandi", label: "Onaylanan", count: onaylandi.length, color: "text-green-700 bg-green-50 border-green-200" },
    { key: "reddedildi", label: "Reddedilen", count: reddedildi.length, color: "text-red-600 bg-red-50 border-red-200" },
  ];

  return (
    <DashboardLayout>
      <Header 
        title="Yönetici Onayı" 
        subtitle="Mükerrer kayıt kararlarını yönetin ve denetleyin"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded">
                Backend: Erişilemiyor
              </span>
            )}
            <button
              onClick={() => refreshPendingMatches(lastUploadId ?? undefined)}
              disabled={loading || backendHealthy === false}
              className="flex items-center gap-2 text-sm text-gray-600 border border-gray-200 px-4 py-2 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors"
            >
              <i className={loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"}></i>
              {refreshLabel}
            </button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {lastUploadId && (
          <div className="rounded-xl p-4 border bg-amber-50 border-amber-100 flex items-center gap-3">
            <i className="ri-information-line text-amber-600 text-lg"></i>
            <p className="text-sm text-amber-700">
              Yönetici onayı son detect çalışması üzerinden filtreleniyor. Upload ID: {lastUploadId}
            </p>
          </div>
        )}

        {apiError && (
          <div className="rounded-xl p-4 border bg-red-50 border-red-100 flex items-center gap-3">
            <i className="ri-error-warning-fill text-red-600 text-lg"></i>
            <p className="text-sm text-red-700">{apiError}</p>
          </div>
        )}

        {/* Loading indicator */}
        {loading && (
          <div className="rounded-xl p-4 border bg-blue-50 border-blue-100 flex items-center gap-3">
            <i className="ri-loader-4-line text-blue-600 text-lg animate-spin"></i>
            <p className="text-sm text-blue-700">Backend verileri yükleniyor...</p>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 bg-gray-100/60 p-1 rounded-xl w-fit">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium cursor-pointer transition-all whitespace-nowrap ${
                tab === t.key ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${t.color}`}>
                {t.count}
              </span>
            </button>
          ))}
        </div>

        {/* Bekleyen Tab */}
        {tab === "bekleyen" && (
          <div className="bg-white rounded-xl border border-gray-100">
            <div className="px-5 py-4 border-b border-gray-50">
              <h3 className="text-sm font-semibold text-gray-900">Onay Bekleyen Kayıtlar</h3>
              <p className="text-xs text-gray-400 mt-0.5">Kararınızı bildirmek için "Detay" butonuna tıklayın</p>
            </div>
            <div className="divide-y divide-gray-50">
              {bekleyen.map((g) => (
                <div key={g.id} className="flex items-center gap-4 px-5 py-4 hover:bg-gray-50/50 transition-colors">
                  <div className="w-10 h-10 rounded-lg bg-yellow-50 flex items-center justify-center flex-shrink-0">
                    <i className="ri-time-line text-yellow-600 text-lg"></i>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-gray-800">{g.id}</span>
                      <span className="text-xs text-gray-500">{g.records[0].adSoyad} / {g.records[1].adSoyad}</span>
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Match ID: {g.backendMatchId} · Skor: %{g.score.toFixed(1)}
                    </p>
                    {g.decisionReason && <p className="text-xs text-gray-500 mt-0.5">Karar nedeni: {g.decisionReason}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setDetailGroup(g)}
                      className="text-xs text-red-600 font-medium border border-red-200 px-3 py-1.5 rounded-lg hover:bg-red-50 cursor-pointer whitespace-nowrap transition-colors"
                    >
                      Detay &amp; Karar Ver
                    </button>
                  </div>
                </div>
              ))}
              {bekleyen.length === 0 && (
                <div className="text-center py-10 text-gray-400 text-sm">Bekleyen kayıt yok.</div>
              )}
            </div>
          </div>
        )}

        {/* Onaylanan / Reddedilen Tabs */}
        {(tab === "onaylandi" || tab === "reddedildi") && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <i className="ri-search-line absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm"></i>
                <input
                  type="text"
                  value={searchAudit}
                  onChange={(e) => setSearchAudit(e.target.value)}
                  placeholder="Grup ID veya yönetici ara..."
                  className="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-red-400"
                />
              </div>
              <select
                value={filterYonetici}
                onChange={(e) => setFilterYonetici(e.target.value)}
                className="border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 bg-white cursor-pointer"
              >
                <option>Tümü</option>
                {yoneticiler.map((y) => <option key={y}>{y}</option>)}
              </select>
            </div>

            <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50/70 border-b border-gray-100">
                      <th className="text-left text-gray-400 font-medium px-5 py-3">Grup</th>
                      <th className="text-left text-gray-400 font-medium px-4 py-3">Yönetici</th>
                      <th className="text-left text-gray-400 font-medium px-4 py-3">İşlem</th>
                      <th className="text-left text-gray-400 font-medium px-4 py-3">Tarih</th>
                      <th className="text-left text-gray-400 font-medium px-4 py-3">Not</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {filteredLog
                      .filter((l) =>
                        tab === "onaylandi" ? l.islem === "Onaylandı" : l.islem === "Reddedildi"
                      )
                      .map((l) => (
                        <tr key={l.id} className="hover:bg-gray-50/50 transition-colors">
                          <td className="px-5 py-3.5 font-medium text-gray-700">{l.grup}</td>
                          <td className="px-4 py-3.5">
                            <div className="flex items-center gap-2">
                              <div className="w-6 h-6 rounded-full bg-red-100 flex items-center justify-center text-[10px] font-bold text-red-600">
                                {l.yonetici.split(" ").map((n) => n[0]).join("")}
                              </div>
                              <span className="text-gray-700">{l.yonetici}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3.5">
                            <span className={`inline-block px-2.5 py-1 rounded-full text-[11px] font-medium ${l.islem === "Onaylandı" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
                              {l.islem}
                            </span>
                          </td>
                          <td className="px-4 py-3.5 text-gray-400">{l.tarih}</td>
                          <td className="px-4 py-3.5 text-gray-500 max-w-[200px] truncate">{l.not}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {detailGroup && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setDetailGroup(null)}>
          <div className="bg-white rounded-2xl w-full max-w-3xl max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div>
                <h2 className="text-base font-bold text-gray-900">Tam Alan Karşılaştırması — {detailGroup.id}</h2>
                <p className="text-xs text-gray-400 mt-0.5">Karar vermeden önce tüm alanları inceleyin</p>
              </div>
              <button onClick={() => setDetailGroup(null)} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-100 cursor-pointer">
                <i className="ri-close-line text-lg text-gray-500"></i>
              </button>
            </div>
            <div className="p-6">
              {/* Skor kırılımı */}
              <div className="mb-5 p-4 bg-gray-50 rounded-xl">
                <p className="text-xs font-semibold text-gray-600 mb-3">Skor Kırılımı</p>
                <div className="space-y-2">
                  {Object.entries(detailGroup.matchDetails || {}).map(([field, score]) => (
                    <div key={field} className="flex items-center gap-3">
                      <span className="text-xs text-gray-500 w-24 capitalize">{field}</span>
                      <div className="flex-1 bg-gray-200 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${score >= 90 ? "bg-green-500" : score >= 70 ? "bg-yellow-400" : "bg-red-400"}`}
                          style={{ width: `${score}%` }}
                        />
                      </div>
                      <span className={`text-xs font-bold w-10 text-right ${score >= 90 ? "text-green-600" : score >= 70 ? "text-yellow-600" : "text-red-500"}`}>
                        %{score}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 pt-3 border-t border-gray-200 flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-700">Genel Skor</span>
                  <span className="text-lg font-bold text-red-600">%{detailGroup.score.toFixed(1)}</span>
                </div>
              </div>
              {/* Yan yana */}
              <div className="grid grid-cols-2 gap-4 mb-5">
                {detailGroup.records.map((rec, i) => (
                  <div key={i} className={`rounded-xl p-4 border-2 ${i === 0 ? "border-gray-200" : "border-red-200 bg-red-50/20"}`}>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full mb-3 inline-block ${i === 0 ? "bg-gray-100 text-gray-600" : "bg-red-100 text-red-600"}`}>
                      Kayıt {i + 1} — {rec.muhatapNo}
                    </span>
                    {[["Ad Soyad", rec.adSoyad], ["TC Kimlik", rec.tcKimlikNo], ["Telefon", rec.telefon], ["E-posta", rec.email], ["Şehir", rec.sehir], ["Adres", rec.adres || "-"]].map(([l, v]) => (
                      <div key={l} className="mb-2">
                        <p className="text-[10px] text-gray-400">{l}</p>
                        <p className="text-xs font-medium text-gray-800 break-words">{v}</p>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Karar Notu (Opsiyonel)</label>
                <textarea 
                  rows={2} 
                  placeholder="Karar gerekçenizi yazın..." 
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 resize-none"
                  maxLength={500}
                  value={decisionNote}
                  onChange={(e) => setDecisionNote(e.target.value)}
                />
              </div>
              <div className="flex gap-3 mt-4">
                <button 
                  onClick={() => handleApprove(detailGroup.id)}
                  className="flex-1 bg-green-600 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-green-700 cursor-pointer whitespace-nowrap"
                >
                  <i className="ri-checkbox-circle-line mr-1.5"></i>Onayla
                </button>
                <button 
                  onClick={() => handleReject(detailGroup.id)}
                  className="flex-1 border-2 border-red-200 text-red-600 text-sm font-semibold py-2.5 rounded-lg hover:bg-red-50 cursor-pointer whitespace-nowrap"
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