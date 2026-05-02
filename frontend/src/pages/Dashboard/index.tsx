import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  getMatches,
  getReportDataQuality,
  getReportOverview,
  getReportReviewSummary,
  listUploads,
  type AdminPendingMatch,
  type ReportDataQuality,
  type ReportOverview,
  type ReportReviewSummary,
  type UploadItem,
} from "../../services/api";

type LoadState<T> = {
  data: T | null;
  loading: boolean;
  error: boolean;
};

function initialState<T>(): LoadState<T> {
  return { data: null, loading: true, error: false };
}

function formatNumber(value: number | undefined | null): string {
  return Number(value || 0).toLocaleString("tr-TR");
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString("tr-TR", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return value;
  }
}

function SectionMessage({ loading, error }: { loading: boolean; error: boolean }) {
  if (loading) {
    return (
      <div className="py-8 text-center text-sm text-gray-400">
        <i className="ri-loader-4-line mb-2 block animate-spin text-xl" />
        Yükleniyor...
      </div>
    );
  }
  if (error) {
    return <div className="py-8 text-center text-sm text-red-500">Veri yüklenemedi</div>;
  }
  return null;
}

function SummaryCard({
  label,
  value,
  tone,
  icon,
  to,
}: {
  label: string;
  value: string;
  tone: "blue" | "yellow" | "green" | "purple";
  icon: string;
  to?: string;
}) {
  const toneClass = {
    blue: "bg-blue-50 text-blue-700 border-blue-100",
    yellow: "bg-yellow-50 text-yellow-700 border-yellow-100",
    green: "bg-green-50 text-green-700 border-green-100",
    purple: "bg-purple-50 text-purple-700 border-purple-100",
  }[tone];
  const content = (
    <div className={`rounded-xl border p-4 transition-colors ${toneClass} ${to ? "hover:bg-white" : ""}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium opacity-80">{label}</span>
        <i className={`${icon} text-lg`} />
      </div>
      <div className="mt-3 text-2xl font-bold">{value}</div>
    </div>
  );
  return to ? <Link to={to}>{content}</Link> : content;
}

function QualityBar({ label, value }: { label: string; value: number }) {
  const color = value < 60 ? "bg-red-500" : value <= 85 ? "bg-yellow-500" : "bg-green-600";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-medium text-gray-700">{label}</span>
        <span className="font-semibold text-gray-900">%{value.toFixed(1)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-gray-100">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
    </div>
  );
}

function scoreTone(score: number): string {
  if (score > 0.8) return "bg-green-50 text-green-700";
  if (score >= 0.55) return "bg-yellow-50 text-yellow-700";
  return "bg-gray-50 text-gray-600";
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<LoadState<ReportOverview>>(initialState);
  const [uploads, setUploads] = useState<LoadState<UploadItem[]>>(initialState);
  const [pending, setPending] = useState<LoadState<AdminPendingMatch[]>>(initialState);
  const [quality, setQuality] = useState<LoadState<ReportDataQuality>>(initialState);
  const [reviews, setReviews] = useState<LoadState<ReportReviewSummary>>(initialState);

  const loadOverview = useCallback(async () => {
    setOverview((prev) => ({ ...prev, loading: true, error: false }));
    try {
      const data = await getReportOverview();
      setOverview({ data, loading: false, error: !data.success });
    } catch {
      setOverview({ data: null, loading: false, error: true });
    }
  }, []);

  const loadUploads = useCallback(async () => {
    setUploads((prev) => ({ ...prev, loading: true, error: false }));
    try {
      const data = await listUploads(5);
      setUploads({ data: data.uploads || [], loading: false, error: false });
    } catch {
      setUploads({ data: null, loading: false, error: true });
    }
  }, []);

  const loadPending = useCallback(async () => {
    setPending((prev) => ({ ...prev, loading: true, error: false }));
    try {
      const data = await getMatches({ decision: "pending", limit: 5 });
      setPending({ data: data.matches || [], loading: false, error: false });
    } catch {
      setPending({ data: null, loading: false, error: true });
    }
  }, []);

  const loadQuality = useCallback(async () => {
    setQuality((prev) => ({ ...prev, loading: true, error: false }));
    try {
      const data = await getReportDataQuality();
      setQuality({ data, loading: false, error: !data.success });
    } catch {
      setQuality({ data: null, loading: false, error: true });
    }
  }, []);

  const loadReviews = useCallback(async () => {
    setReviews((prev) => ({ ...prev, loading: true, error: false }));
    try {
      const data = await getReportReviewSummary();
      setReviews({ data, loading: false, error: !data.success });
    } catch {
      setReviews({ data: null, loading: false, error: true });
    }
  }, []);

  useEffect(() => {
    loadOverview();
    const timer = window.setInterval(loadOverview, 60_000);
    return () => window.clearInterval(timer);
  }, [loadOverview]);

  useEffect(() => {
    loadUploads();
    loadPending();
    loadQuality();
    loadReviews();
  }, [loadPending, loadQuality, loadReviews, loadUploads]);

  const latestUpload = uploads.data?.[0] ?? null;
  const totalNormalized = overview.data?.total_normalized_records || 0;
  const totalCandidates = overview.data?.total_match_candidates || 0;
  const duplicateRate = totalNormalized > 0 ? (totalCandidates / totalNormalized) * 100 : 0;

  const pipeline = [
    { label: "Yükleme", to: "/veri-yukleme", count: latestUpload?.total_records || 0, date: latestUpload?.created_at },
    {
      label: "Normalizasyon",
      to: latestUpload ? `/veri-normalizasyon?upload_id=${latestUpload.id}` : "/veri-normalizasyon",
      count: latestUpload?.latest_normalization_run_id ? latestUpload.total_records : 0,
      date: latestUpload?.completed_at || latestUpload?.created_at,
    },
    {
      label: "Mükerrer Tespit",
      to: latestUpload ? `/mukerrer-tespit?upload_id=${latestUpload.id}` : "/mukerrer-tespit",
      count: totalCandidates,
      date: latestUpload?.created_at,
    },
    {
      label: "İnceleme",
      to: "/mukerrer-kayitlar?decision=pending",
      count: overview.data?.pending || 0,
      date: latestUpload?.created_at,
    },
    {
      label: "Temiz Export",
      to: "/temiz-veri-seti",
      count: totalNormalized,
      date: latestUpload?.completed_at || latestUpload?.created_at,
    },
  ];

  return (
    <DashboardLayout>
      <Header
        title="Dashboard"
        subtitle="Kayıt akışı, inceleme yükü ve veri kalitesi"
        actions={
          <button
            onClick={() => {
              loadOverview();
              loadUploads();
              loadPending();
              loadQuality();
              loadReviews();
            }}
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            <i className="ri-refresh-line" />
            Yenile
          </button>
        }
      />

      <div className="flex-1 space-y-5 overflow-y-auto p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {overview.error ? (
            <div className="col-span-full rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-600">
              Veri yüklenemedi
            </div>
          ) : (
            <>
              <SummaryCard label="Toplam Kayıt" value={overview.loading ? "..." : formatNumber(totalNormalized)} tone="blue" icon="ri-database-2-line" />
              <SummaryCard label="Bekleyen İnceleme" value={overview.loading ? "..." : formatNumber(overview.data?.pending)} tone="yellow" icon="ri-time-line" to="/mukerrer-kayitlar?decision=pending" />
              <SummaryCard label="Onaylanan" value={overview.loading ? "..." : formatNumber(overview.data?.approved)} tone="green" icon="ri-checkbox-circle-line" />
              <SummaryCard label="Mükerrer Oran" value={overview.loading ? "..." : `%${duplicateRate.toFixed(1)}`} tone="purple" icon="ri-percent-line" />
            </>
          )}
        </div>

        <div className="rounded-xl border border-gray-100 bg-white p-4">
          <div className="mb-3 text-sm font-semibold text-gray-900">Pipeline Durumu</div>
          <SectionMessage loading={uploads.loading || overview.loading} error={uploads.error || overview.error} />
          {!uploads.loading && !overview.loading && !uploads.error && !overview.error && (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
              {pipeline.map((step, index) => (
                <button
                  key={step.label}
                  onClick={() => navigate(step.to)}
                  className="cursor-pointer rounded-lg border border-gray-100 bg-gray-50 p-3 text-left transition-colors hover:border-red-100 hover:bg-red-50/40"
                >
                  <div className="flex items-center justify-between text-sm font-semibold text-gray-900">
                    <span>{step.label}</span>
                    {index < pipeline.length - 1 && <i className="ri-arrow-right-line text-gray-300" />}
                  </div>
                  <div className="mt-2 text-xs text-gray-500">{formatDate(step.date)}</div>
                  <div className="mt-1 text-xs font-medium text-gray-700">{formatNumber(step.count)} kayıt</div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
          <div className="overflow-hidden rounded-xl border border-gray-100 bg-white xl:col-span-3">
            <div className="border-b border-gray-50 px-5 py-4 text-sm font-semibold text-gray-900">Son Yüklemeler</div>
            <SectionMessage loading={uploads.loading} error={uploads.error} />
            {!uploads.loading && !uploads.error && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50/70">
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Dosya adı</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Kayıt</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Durum</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Tarih</th>
                      <th className="px-4 py-3 text-right font-medium text-gray-400">İşlem</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {(uploads.data || []).map((upload) => (
                      <tr key={upload.id} className="hover:bg-gray-50/50">
                        <td className="px-4 py-3 font-medium text-gray-800">{upload.file_name}</td>
                        <td className="px-4 py-3 text-gray-600">{formatNumber(upload.total_records)}</td>
                        <td className="px-4 py-3 text-gray-600">{upload.processing_stage || upload.status}</td>
                        <td className="px-4 py-3 text-gray-500">{formatDate(upload.created_at)}</td>
                        <td className="px-4 py-3 text-right">
                          <Link
                            to={
                              upload.latest_normalization_run_id
                                ? `/mukerrer-tespit?upload_id=${upload.id}`
                                : `/veri-normalizasyon?upload_id=${upload.id}`
                            }
                            className="inline-flex items-center gap-1 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
                          >
                            {upload.latest_normalization_run_id ? "Mükerrer Tespit" : "Normalize Et"}
                          </Link>
                        </td>
                      </tr>
                    ))}
                    {(uploads.data || []).length === 0 && (
                      <tr><td colSpan={5} className="px-5 py-8 text-center text-gray-400">Yükleme bulunamadı.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="rounded-xl border border-gray-100 bg-white xl:col-span-2">
            <div className="border-b border-gray-50 px-5 py-4 text-sm font-semibold text-gray-900">Bekleyen İncelemeler</div>
            <SectionMessage loading={pending.loading} error={pending.error} />
            {!pending.loading && !pending.error && (
              <div className="divide-y divide-gray-50">
                {(pending.data || []).map((match) => {
                  const score = Number(match.confidence ?? match.score ?? 0);
                  return (
                    <div key={match.id} className="space-y-3 px-5 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 text-xs font-medium text-gray-800">
                          <span className="block truncate">{match.donor1_name || "-"}</span>
                          <span className="text-gray-400">↔</span>
                          <span className="block truncate">{match.donor2_name || "-"}</span>
                        </div>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${scoreTone(score)}`}>%{(score * 100).toFixed(1)}</span>
                      </div>
                      <Link
                        to={`/mukerrer-kayitlar?group_id=match_${match.id}`}
                        className="inline-flex items-center gap-1 text-xs font-medium text-red-600 hover:underline"
                      >
                        İncele <i className="ri-arrow-right-line" />
                      </Link>
                    </div>
                  );
                })}
                {(pending.data || []).length === 0 && <div className="py-8 text-center text-sm text-gray-400">Bekleyen inceleme yok.</div>}
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div className="rounded-xl border border-gray-100 bg-white p-5">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Veri Kalitesi Özeti</h3>
            <SectionMessage loading={quality.loading} error={quality.error} />
            {!quality.loading && !quality.error && quality.data && (
              <div className="space-y-4">
                <QualityBar label="TC doluluğu" value={quality.data.tc_fill_rate ?? quality.data.validity_rate ?? 0} />
                <QualityBar label="Telefon doluluğu" value={quality.data.phone_fill_rate ?? 0} />
                <QualityBar label="E-mail doluluğu" value={quality.data.email_fill_rate ?? 0} />
              </div>
            )}
          </div>

          <div className="rounded-xl border border-gray-100 bg-white">
            <div className="border-b border-gray-50 px-5 py-4 text-sm font-semibold text-gray-900">Son Kararlar</div>
            <SectionMessage loading={reviews.loading} error={reviews.error} />
            {!reviews.loading && !reviews.error && (
              <div className="divide-y divide-gray-50">
                {(reviews.data?.recent_reviews || []).map((review) => {
                  const approved = review.decision === "approved";
                  return (
                    <div key={review.id} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 px-5 py-3 text-xs">
                      <div>
                        <div className="font-medium text-gray-800">{review.user || "system"}</div>
                        <div className="text-gray-400">{review.group_id}</div>
                      </div>
                      <span className={approved ? "font-semibold text-green-700" : "font-semibold text-red-600"}>
                        {approved ? "✓ Onay" : "✗ Red"}
                      </span>
                      <span className="text-gray-400">{formatDate(review.date)}</span>
                    </div>
                  );
                })}
                {(reviews.data?.recent_reviews || []).length === 0 && <div className="py-8 text-center text-sm text-gray-400">Karar bulunamadı.</div>}
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
