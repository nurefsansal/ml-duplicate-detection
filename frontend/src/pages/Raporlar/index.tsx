import { useState, useEffect } from "react";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  downloadApprovedMatchesCsv,
  downloadCleanDatasetCsv,
  downloadDuplicateGroupsCsv,
  downloadGoldenRecordsCsv,
  downloadMuhatapMergeDetailCsv,
  getMatches,
  getMuhatapMergeReport,
  getReportOverview,
  getReportDataQuality,
  getReportDetectionSummary,
  getReportReviewSummary,
  getReportUploadHistory,
  type MuhatapMergeReportGroup,
  type ReportOverview,
  type ReportDataQuality,
  type ReportDetectionSummary,
  type ReportReviewSummary,
  type ReportUploadHistoryItem,
  type DuplicateGroupRecord,
} from "../../services/api";

const reportTabs = [
  { id: "overview", icon: "ri-dashboard-3-line", label: "Genel Özet", desc: "Toplam kayıt, tespit ve onay istatistikleri" },
  { id: "data-quality", icon: "ri-shield-check-line", label: "Veri Kalitesi", desc: "Standardizasyon başarısı, geçerli/geçersiz kayıt oranları", badge: "Yeni" },
  { id: "detection", icon: "ri-search-eye-line", label: "Tespit Özeti", desc: "Tespit çalışmaları, mükerrer aday istatistikleri", badge: null },
  { id: "review", icon: "ri-checkbox-circle-line", label: "İnceleme Özeti", desc: "Onay/red kararları ve inceleme istatistikleri", badge: null },
  { id: "muhatap-merge", icon: "ri-git-merge-line", label: "Muhatap Birleştirme", desc: "Farklı muhatap kodlu onaylı gruplar, golden ve eski kayıt detayı", badge: null },
  { id: "upload-history", icon: "ri-upload-cloud-2-line", label: "Yükleme Geçmişi", desc: "Kaynak bazlı yükleme istatistikleri", badge: null },
];

function formatDate(iso: string | null): string {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("tr-TR", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function StatCard({ label, value, color = "text-gray-900", bg = "bg-gray-50" }: { label: string; value: string | number; color?: string; bg?: string }) {
  return (
    <div className={`${bg} rounded-lg p-3 text-center`}>
      <p className={`text-lg font-bold ${color}`}>{value}</p>
      <p className="text-[10px] text-gray-400 mt-0.5">{label}</p>
    </div>
  );
}

export default function Raporlar() {
  const [selectedTab, setSelectedTab] = useState("overview");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [overview, setOverview] = useState<ReportOverview | null>(null);
  const [quality, setQuality] = useState<ReportDataQuality | null>(null);
  const [detection, setDetection] = useState<ReportDetectionSummary | null>(null);
  const [review, setReview] = useState<ReportReviewSummary | null>(null);
  const [uploadHistory, setUploadHistory] = useState<ReportUploadHistoryItem[]>([]);
  const [decisionCounts, setDecisionCounts] = useState({
    pending: 0,
    approved: 0,
    rejected: 0,
  });
  const [mergeReportGroups, setMergeReportGroups] = useState<MuhatapMergeReportGroup[]>([]);
  const [mergeReportMeta, setMergeReportMeta] = useState<{
    totalAll: number;
    withDetail: number;
  } | null>(null);
  const [mergeReportLoading, setMergeReportLoading] = useState(false);
  const [mergeReportError, setMergeReportError] = useState("");
  const [exporting, setExporting] = useState(false);

  const dateParams = {
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };

  const fetchAll = async () => {
    setLoading(true);
    setError("");
    try {
      const [ov, q, d, r, uh, pendingMatches, approvedMatches, rejectedMatches] =
        await Promise.all([
        getReportOverview(dateParams),
        getReportDataQuality(dateParams),
        getReportDetectionSummary(dateParams),
        getReportReviewSummary(dateParams),
        getReportUploadHistory({ ...dateParams, limit: 20 }),
        getMatches({ decision: "pending", limit: 1_000_000 }),
        getMatches({ decision: "approved", limit: 1_000_000 }),
        getMatches({ decision: "rejected", limit: 1_000_000 }),
      ]);
      setOverview(ov.success ? ov : null);
      setQuality(q.success ? q : null);
      setDetection(d.success ? d : null);
      setReview(r.success ? r : null);
      setUploadHistory(uh.success ? uh.uploads : []);
      setDecisionCounts({
        pending: pendingMatches.count ?? 0,
        approved: approvedMatches.count ?? 0,
        rejected: rejectedMatches.count ?? 0,
      });
    } catch {
      setError("Rapor verileri yüklenemedi. Backend bağlantısını kontrol edin.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  useEffect(() => {
    if (selectedTab !== "muhatap-merge") return;
    let cancelled = false;
    const load = async () => {
      setMergeReportLoading(true);
      setMergeReportError("");
      try {
        const raw = localStorage.getItem("lastDetectUploadId");
        const parsed = raw ? Number(raw) : NaN;
        const uploadId = Number.isFinite(parsed) ? parsed : undefined;
        const res = await getMuhatapMergeReport({
          uploadId,
          decision: "approved",
          page: 1,
          pageSize: 100,
        });
        if (cancelled) return;
        if (!res.success) {
          setMergeReportError(res.error || "Rapor alınamadı.");
          setMergeReportGroups([]);
          setMergeReportMeta(null);
          return;
        }
        setMergeReportGroups(res.groups || []);
        setMergeReportMeta({
          totalAll: res.total_all_groups ?? 0,
          withDetail: res.count_with_merge_detail ?? 0,
        });
      } catch {
        if (!cancelled) {
          setMergeReportError("Muhatap birleştirme raporu yüklenemedi.");
          setMergeReportGroups([]);
          setMergeReportMeta(null);
        }
      } finally {
        if (!cancelled) setMergeReportLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedTab]);

  const handleQuickDate = (range: string) => {
    const today = new Date();
    let from = new Date();
    switch (range) {
      case "Bu Hafta": from = new Date(today); from.setDate(today.getDate() - 7); break;
      case "Bu Ay": from = new Date(today); from.setMonth(today.getMonth() - 1); break;
      case "Son 3 Ay": from = new Date(today); from.setMonth(today.getMonth() - 3); break;
      case "Bu Yıl": from = new Date(today); from.setFullYear(today.getFullYear() - 1); break;
    }
    setDateFrom(from.toISOString().split("T")[0]);
    setDateTo(new Date().toISOString().split("T")[0]);
  };

  const handleExport = async (
    exportType:
      | "clean"
      | "duplicate_groups"
      | "approved_matches"
      | "golden_records"
      | "muhatap_merge",
  ) => {
    setExporting(true);
    setError("");
    try {
      const lastUploadIdRaw = localStorage.getItem("lastDetectUploadId");
      const parsedUploadId = lastUploadIdRaw ? Number(lastUploadIdRaw) : Number.NaN;
      const uploadId = Number.isFinite(parsedUploadId) ? parsedUploadId : undefined;

      if (exportType === "clean") {
        await downloadCleanDatasetCsv({ uploadId });
      } else if (exportType === "duplicate_groups") {
        await downloadDuplicateGroupsCsv({ uploadId, decision: "approved" });
      } else if (exportType === "approved_matches") {
        await downloadApprovedMatchesCsv({ uploadId });
      } else if (exportType === "golden_records") {
        await downloadGoldenRecordsCsv({ uploadId, decision: "approved" });
      } else {
        await downloadMuhatapMergeDetailCsv({ uploadId, decision: "approved" });
      }
    } catch {
      setError("Export dosyasi indirilemedi. Lütfen tekrar deneyin.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <DashboardLayout>
      <Header
        title="Raporlar"
        subtitle="Gerçek veritabanı verilerinden sistem istatistikleri"
        actions={
          <button
            onClick={fetchAll}
            disabled={loading}
            className="flex items-center gap-2 border border-gray-200 text-gray-600 text-sm px-4 py-2 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors whitespace-nowrap disabled:opacity-60"
          >
            <i className={loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"}></i>
            Yenile
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {error && (
          <div className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 p-4">
            <i className="ri-error-warning-fill text-red-600 text-lg" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Left: Tabs + Date + Content */}
          <div className="lg:col-span-2 space-y-5">
            {/* Report tabs */}
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">Rapor Türü</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {reportTabs.map((r) => {
                  const active = selectedTab === r.id;
                  return (
                    <button
                      key={r.id}
                      onClick={() => setSelectedTab(r.id)}
                      className={`relative text-left p-4 rounded-xl border-2 cursor-pointer transition-all ${active ? "border-red-500 bg-red-50/40" : "border-gray-100 hover:border-gray-200"}`}
                    >
                      {r.badge && (
                        <span className="absolute top-3 right-3 text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-100 text-red-600">
                          {r.badge}
                        </span>
                      )}
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2 ${active ? "bg-red-100" : "bg-gray-100"}`}>
                        <i className={`${r.icon} text-base ${active ? "text-red-600" : "text-gray-400"}`}></i>
                      </div>
                      <p className={`text-sm font-semibold ${active ? "text-red-700" : "text-gray-700"}`}>{r.label}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{r.desc}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Date Range */}
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">Tarih Aralığı</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">Başlangıç</label>
                  <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 cursor-pointer" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">Bitiş</label>
                  <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 cursor-pointer" />
                </div>
              </div>
              <div className="flex gap-2 mt-3 flex-wrap">
                {["Bu Hafta", "Bu Ay", "Son 3 Ay", "Bu Yıl"].map((p) => (
                  <button key={p} onClick={() => handleQuickDate(p)}
                    className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer text-gray-600 whitespace-nowrap transition-colors">
                    {p}
                  </button>
                ))}
                <button onClick={fetchAll} disabled={loading}
                  className="text-xs px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 cursor-pointer whitespace-nowrap transition-colors disabled:opacity-60">
                  Filtrele
                </button>
              </div>
            </div>

            {/* Content area */}
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">
                {reportTabs.find((r) => r.id === selectedTab)?.label ?? "Rapor"}
              </h3>

              {loading ? (
                <div className="py-10 text-center text-gray-400">
                  <i className="ri-loader-4-line animate-spin text-2xl block mb-2" />
                  Veriler yükleniyor…
                </div>
              ) : (
                <>
                  {/* Overview */}
                  {selectedTab === "overview" && overview && (
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                      <StatCard label="Toplam Yükleme" value={overview.total_uploads} />
                      <StatCard label="Normalize Kayıt" value={overview.total_normalized_records.toLocaleString("tr-TR")} />
                      <StatCard label="Aday Çift" value={overview.total_match_candidates} />
                      <StatCard label="Onaylanan" value={decisionCounts.approved} color="text-green-600" bg="bg-green-50" />
                      <StatCard label="Bekleyen" value={decisionCounts.pending} color="text-yellow-600" bg="bg-yellow-50" />
                      <StatCard label="Reddedilen" value={decisionCounts.rejected} color="text-red-600" bg="bg-red-50" />
                    </div>
                  )}

                  {/* Data Quality */}
                  {selectedTab === "data-quality" && quality && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        <StatCard label="Toplam Normalize" value={quality.total_normalized_records.toLocaleString("tr-TR")} />
                        <StatCard label="Geçerli" value={quality.valid_records.toLocaleString("tr-TR")} color="text-green-600" bg="bg-green-50" />
                        <StatCard label="Geçersiz" value={quality.invalid_records} color="text-red-600" bg="bg-red-50" />
                        <StatCard label="Geçerlilik Oranı" value={`%${quality.validity_rate}`} color="text-blue-600" bg="bg-blue-50" />
                      </div>
                      <div className="pt-4 border-t border-gray-100 grid grid-cols-2 sm:grid-cols-4 gap-4">
                        <StatCard label="Standardizasyon Çalışması" value={quality.normalization_runs} />
                        <StatCard label="İşlenen" value={quality.total_processed.toLocaleString("tr-TR")} />
                        <StatCard label="Başarılı" value={quality.total_success.toLocaleString("tr-TR")} color="text-green-600" bg="bg-green-50" />
                        <StatCard label="Hatalı" value={quality.total_failed} color="text-orange-600" bg="bg-orange-50" />
                      </div>
                    </div>
                  )}

                  {/* Detection */}
                  {selectedTab === "detection" && detection && (
                    <div className="space-y-4">
                      {/* Group-level metrics (primary — the meaningful numbers) */}
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                        <StatCard
                          label="Mükerrer Grup"
                          value={(detection.total_duplicate_groups ?? 0).toLocaleString("tr-TR")}
                          color="text-red-600"
                          bg="bg-red-50"
                        />
                        <StatCard
                          label="Mükerrer Çift"
                          value={(detection.total_duplicate_pairs ?? detection.total_match_candidates ?? 0).toLocaleString("tr-TR")}
                          color="text-orange-600"
                          bg="bg-orange-50"
                        />
                        <StatCard
                          label="Etkilenen Kayıt"
                          value={(detection.total_affected_records ?? 0).toLocaleString("tr-TR")}
                          color="text-amber-600"
                          bg="bg-amber-50"
                        />
                      </div>
                      {/* Run-level & decision stats */}
                      <div className="pt-4 border-t border-gray-100 grid grid-cols-2 sm:grid-cols-3 gap-4">
                        <StatCard label="Tespit Çalışması" value={detection.total_detection_runs} />
                        <StatCard label="Ort. Skor" value={`%${detection.avg_score_pct}`} color="text-blue-600" bg="bg-blue-50" />
                        <StatCard label="Onaylanan" value={decisionCounts.approved} color="text-green-600" bg="bg-green-50" />
                        <StatCard label="Bekleyen" value={decisionCounts.pending} color="text-yellow-600" bg="bg-yellow-50" />
                        <StatCard label="Reddedilen" value={decisionCounts.rejected} color="text-red-600" bg="bg-red-50" />
                      </div>
                    </div>
                  )}

                  {/* Review */}
                  {selectedTab === "review" && review && (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                      <StatCard
                        label="Toplam İnceleme"
                        value={decisionCounts.pending + decisionCounts.approved + decisionCounts.rejected}
                      />
                      <StatCard label="Onay" value={decisionCounts.approved} color="text-green-600" bg="bg-green-50" />
                      <StatCard label="Red" value={decisionCounts.rejected} color="text-red-600" bg="bg-red-50" />
                    </div>
                  )}

                  {selectedTab === "muhatap-merge" && (
                    <div className="space-y-4">
                      <p className="text-xs text-gray-500 leading-relaxed">
                        Son tespit yükleme ID&apos;si <code className="rounded bg-gray-100 px-1">localStorage.lastDetectUploadId</code> ile
                        filtrelenir. Liste: yalnızca <strong>farklı muhatap kodlu</strong> ve kayıt sırasında birleşim özeti oluşturulmuş
                        <strong> onaylı</strong> gruplar. CSV export: her grup için{" "}
                        <code className="rounded bg-gray-100 px-1">GOLDEN_RECORD</code> satırı, ardından her önceki üye için{" "}
                        <code className="rounded bg-gray-100 px-1">PRIOR_MATCHED_MEMBER</code> satırı (normalize ve ham JSON sütunlarıyla).
                      </p>
                      {mergeReportLoading ? (
                        <p className="text-sm text-gray-500 py-6 text-center">
                          <i className="ri-loader-4-line animate-spin mr-2" />
                          Rapor yükleniyor…
                        </p>
                      ) : mergeReportError ? (
                        <p className="text-sm text-red-600">{mergeReportError}</p>
                      ) : (
                        <>
                          {mergeReportMeta && (
                            <p className="text-xs text-gray-600">
                              Bu sayfada birleşim detayı olan grup:{" "}
                              <strong>{mergeReportMeta.withDetail}</strong>
                              {" · "}
                              Aynı filtrede toplam farklı-muhatap grup (sayfa başına):{" "}
                              <strong>{mergeReportMeta.totalAll}</strong>
                            </p>
                          )}
                          {mergeReportGroups.length === 0 ? (
                            <p className="text-sm text-gray-500 py-6">
                              Henüz kayıtlı birleşim detayı yok. Mükerrer kayıtlarda farklı muhatap kodlu bir grupta
                              golden kaydı &quot;Kaydet&quot; ile onayladığınızda burada ve CSV exportta görünür.
                            </p>
                          ) : (
                            <div className="space-y-8 max-h-[560px] overflow-y-auto pr-1">
                              {mergeReportGroups.map((g) => {
                                const gr = g.golden_record as {
                                  merged_muhatap_report_line?: string;
                                  merged_member_snapshots?: Array<
                                    DuplicateGroupRecord & { muhatap_no_effective?: string }
                                  >;
                                  clean_name?: string;
                                  clean_muhatap_no?: string;
                                };
                                const snaps = gr.merged_member_snapshots || [];
                                return (
                                  <div
                                    key={g.group_id}
                                    className="rounded-xl border border-gray-100 bg-slate-50/60 p-4"
                                  >
                                    <div className="flex flex-wrap items-start justify-between gap-2 border-b border-gray-100 pb-2 mb-3">
                                      <div>
                                        <p className="text-sm font-semibold text-gray-900">{g.group_id}</p>
                                        <p className="text-[11px] text-gray-500 mt-0.5">
                                          Entity #{g.entity_id ?? "—"} · Skor %{(Number(g.group_score || 0) * 100).toFixed(1)}
                                          {g.muhatap_codes?.length ? (
                                            <span> · Muhatap kodları: {g.muhatap_codes.join(", ")}</span>
                                          ) : null}
                                        </p>
                                      </div>
                                      <div className="text-right text-[11px] text-gray-500">
                                        Golden: {gr.clean_name || "—"} / {gr.clean_muhatap_no || "—"}
                                      </div>
                                    </div>
                                    {gr.merged_muhatap_report_line ? (
                                      <p className="text-xs text-gray-800 leading-relaxed mb-3">
                                        {gr.merged_muhatap_report_line}
                                      </p>
                                    ) : null}
                                    <p className="text-[11px] font-semibold text-gray-600 mb-2">
                                      Birleşmeden önceki kayıtlar (tam alanlar)
                                    </p>
                                    <div className="overflow-x-auto rounded-lg border border-gray-100 bg-white">
                                      <table className="w-full min-w-[720px] text-[10px]">
                                        <thead>
                                          <tr className="bg-gray-50 text-left text-gray-500">
                                            <th className="px-2 py-2">Kayıt</th>
                                            <th className="px-2 py-2">Muhatap</th>
                                            <th className="px-2 py-2">Ad</th>
                                            <th className="px-2 py-2">TC</th>
                                            <th className="px-2 py-2">Tel</th>
                                            <th className="px-2 py-2">E-posta</th>
                                            <th className="px-2 py-2">Şehir</th>
                                            <th className="px-2 py-2">Adres</th>
                                          </tr>
                                        </thead>
                                        <tbody className="divide-y divide-gray-50">
                                          {snaps.map((row) => (
                                            <tr key={row.record_id} className="text-gray-800">
                                              <td className="px-2 py-1.5 font-mono">{row.record_id}</td>
                                              <td className="px-2 py-1.5 font-medium">
                                                {row.muhatap_no_effective || row.clean_muhatap_no || "—"}
                                              </td>
                                              <td className="px-2 py-1.5">{row.clean_name || "—"}</td>
                                              <td className="px-2 py-1.5">{row.clean_tc || "—"}</td>
                                              <td className="px-2 py-1.5">{row.clean_phone || "—"}</td>
                                              <td className="px-2 py-1.5 break-all">{row.clean_email || "—"}</td>
                                              <td className="px-2 py-1.5">{row.clean_city || "—"}</td>
                                              <td className="px-2 py-1.5 max-w-[140px] truncate" title={row.clean_address}>
                                                {row.clean_address || "—"}
                                              </td>
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}

                  {/* Upload History */}
                  {selectedTab === "upload-history" && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-gray-50/70">
                            <th className="px-4 py-3 text-left font-medium text-gray-400">ID</th>
                            <th className="px-4 py-3 text-left font-medium text-gray-400">Dosya</th>
                            <th className="px-4 py-3 text-left font-medium text-gray-400">Kaynak</th>
                            <th className="px-4 py-3 text-right font-medium text-gray-400">Kayıt</th>
                            <th className="px-4 py-3 text-left font-medium text-gray-400">Durum</th>
                            <th className="px-4 py-3 text-left font-medium text-gray-400">Tarih</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                          {uploadHistory.length === 0 ? (
                            <tr>
                              <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                                Yükleme geçmişi bulunamadı.
                              </td>
                            </tr>
                          ) : (
                            uploadHistory.map((u) => (
                              <tr key={u.id} className="hover:bg-gray-50/50">
                                <td className="px-4 py-3 text-gray-500">#{u.id}</td>
                                <td className="px-4 py-3 text-gray-800 font-medium max-w-[180px] truncate">{u.file_name}</td>
                                <td className="px-4 py-3 text-gray-500 capitalize">{u.source_type}</td>
                                <td className="px-4 py-3 text-right text-gray-700 font-medium">{(u.total_records ?? 0).toLocaleString("tr-TR")}</td>
                                <td className="px-4 py-3">
                                  <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                                    u.status === "completed" ? "bg-green-50 text-green-700" : "bg-yellow-50 text-yellow-700"
                                  }`}>
                                    {u.status}
                                  </span>
                                </td>
                                <td className="px-4 py-3 text-gray-400">{formatDate(u.created_at)}</td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* No data fallback */}
                  {!loading && !error &&
                    ((selectedTab === "overview" && !overview) ||
                      (selectedTab === "data-quality" && !quality) ||
                      (selectedTab === "detection" && !detection) ||
                      (selectedTab === "review" && !review)) && (
                    <p className="text-sm text-gray-400 text-center py-8">
                      Backend bağlantısı yok veya veri bulunamadı.
                    </p>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Right: Info panel */}
          <div className="space-y-4">
            {/* Quick stats from overview */}
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">Hızlı Özet</h3>
              {overview ? (
                <div className="space-y-3 text-sm">
                  {[
                    { label: "Yüklemeler", value: overview.total_uploads, icon: "ri-upload-cloud-2-line", color: "text-blue-600" },
                    { label: "Normalize Kayıt", value: overview.total_normalized_records.toLocaleString("tr-TR"), icon: "ri-database-2-line", color: "text-gray-600" },
                    { label: "Bekleyen Onay", value: decisionCounts.pending, icon: "ri-time-line", color: "text-yellow-600" },
                    { label: "Onaylanan", value: decisionCounts.approved, icon: "ri-checkbox-circle-line", color: "text-green-600" },
                  ].map((s) => (
                    <div key={s.label} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <i className={`${s.icon} ${s.color} text-base`}></i>
                        <span className="text-gray-600">{s.label}</span>
                      </div>
                      <span className={`font-semibold ${s.color}`}>{s.value}</span>
                    </div>
                  ))}
                  <p className="text-[10px] text-gray-400 pt-2 border-t border-gray-100">
                    Bekleyen / onaylanan sayıları yalnızca <strong>farklı muhatap kodlu</strong> eşleşme çiftlerini içerir.
                  </p>
                </div>
              ) : (
                <p className="text-xs text-gray-400">Backend verisi bekleniyor…</p>
              )}
            </div>

            {/* Export info */}
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
              <p className="text-xs font-semibold text-gray-700 mb-2">Dışa Aktarma</p>
              <p className="text-xs text-gray-500 mb-3">
                Export dosyalari gerçek DB verilerinden üretilir.
              </p>
              <div className="space-y-2">
                <button
                  onClick={() => handleExport("clean")}
                  disabled={exporting}
                  className="w-full flex items-center justify-center gap-2 bg-white text-gray-700 text-sm font-semibold py-2.5 rounded-xl border border-gray-200 hover:bg-gray-50 disabled:opacity-60"
                >
                  <i className="ri-download-2-line"></i>
                  clean_dataset.csv
                </button>
                <button
                  onClick={() => handleExport("duplicate_groups")}
                  disabled={exporting}
                  className="w-full flex items-center justify-center gap-2 bg-white text-gray-700 text-sm font-semibold py-2.5 rounded-xl border border-gray-200 hover:bg-gray-50 disabled:opacity-60"
                >
                  <i className="ri-download-2-line"></i>
                  duplicate_groups.csv
                </button>
                <button
                  onClick={() => handleExport("approved_matches")}
                  disabled={exporting}
                  className="w-full flex items-center justify-center gap-2 bg-white text-gray-700 text-sm font-semibold py-2.5 rounded-xl border border-gray-200 hover:bg-gray-50 disabled:opacity-60"
                >
                  <i className="ri-download-2-line"></i>
                  approved_matches.csv
                </button>
                <button
                  onClick={() => handleExport("golden_records")}
                  disabled={exporting}
                  className="w-full flex items-center justify-center gap-2 bg-white text-gray-700 text-sm font-semibold py-2.5 rounded-xl border border-gray-200 hover:bg-gray-50 disabled:opacity-60"
                >
                  <i className="ri-download-2-line"></i>
                  golden_records.csv
                </button>
                <button
                  onClick={() => handleExport("muhatap_merge")}
                  disabled={exporting}
                  className="w-full flex items-center justify-center gap-2 bg-white text-gray-700 text-sm font-semibold py-2.5 rounded-xl border border-gray-200 hover:bg-gray-50 disabled:opacity-60"
                >
                  <i className="ri-download-2-line"></i>
                  muhatap_merge_detail.csv
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
