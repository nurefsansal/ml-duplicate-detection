import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { useI18n } from "../../i18n/I18nProvider";
import { withUploadContext } from "../../utils/uploadContextNav";
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
      <div className="py-10 text-center text-sm font-medium text-slate-500">
        <i className="ri-loader-4-line mb-3 block animate-spin text-2xl text-primary-500" />
        Yükleniyor...
      </div>
    );
  }
  if (error) {
    return (
      <div className="py-8 text-center text-sm font-medium text-danger-700">Veri yüklenemedi</div>
    );
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
    blue: "border-primary-200/80 bg-gradient-to-br from-primary-50 to-cyan-50/80 text-primary-900 shadow-sm",
    yellow: "border-amber-200/80 bg-gradient-to-br from-amber-50 to-orange-50/60 text-amber-950 shadow-sm",
    green: "border-emerald-200/80 bg-gradient-to-br from-emerald-50 to-teal-50/70 text-emerald-950 shadow-sm",
    purple: "border-violet-200/80 bg-gradient-to-br from-violet-50 to-indigo-50/70 text-violet-950 shadow-sm",
  }[tone];
  const content = (
    <div
      className={`rounded-2xl border p-5 transition-all duration-200 ${toneClass} ${to ? "hover:-translate-y-0.5 hover:shadow-card-lg" : ""}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide opacity-90">{label}</span>
        <i className={`${icon} text-xl opacity-90`} />
      </div>
      <div className="mt-3 text-3xl font-bold tabular-nums tracking-tight">{value}</div>
    </div>
  );
  return to ? <Link to={to}>{content}</Link> : content;
}

function QualityBar({ label, value }: { label: string; value: number }) {
  const color =
    value < 60 ? "bg-gradient-to-r from-rose-400 to-amber-400" : value <= 85 ? "bg-gradient-to-r from-amber-400 to-primary-400" : "bg-gradient-to-r from-emerald-400 to-teal-500";
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-semibold text-slate-700">{label}</span>
        <span className="font-bold tabular-nums text-slate-900">%{value.toFixed(1)}</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-slate-200/80 shadow-inner">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
    </div>
  );
}

function scoreTone(score: number): string {
  if (score > 0.8) return "border border-emerald-200 bg-emerald-50 text-emerald-900";
  if (score >= 0.55) return "border border-amber-200 bg-amber-50 text-amber-950";
  return "border border-slate-200 bg-slate-100 text-slate-700";
}

export default function Dashboard() {
  const { t, locale } = useI18n();
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
      label: "Standardizasyon",
      to: latestUpload
        ? `/veri-normalizasyon?upload_id=${latestUpload.id}`
        : withUploadContext("/veri-normalizasyon"),
      count: latestUpload?.latest_normalization_run_id ? latestUpload.total_records : 0,
      date: latestUpload?.completed_at || latestUpload?.created_at,
    },
    {
      label: "Mükerrer Tespit",
      to: latestUpload
        ? `/mukerrer-tespit?upload_id=${latestUpload.id}`
        : withUploadContext("/mukerrer-tespit"),
      count: totalCandidates,
      date: latestUpload?.created_at,
    },
    {
      label: "İnceleme",
      to: latestUpload
        ? `/mukerrer-kayitlar?upload_id=${latestUpload.id}&decision=pending`
        : withUploadContext("/mukerrer-kayitlar?decision=pending"),
      count: overview.data?.pending || 0,
      date: latestUpload?.created_at,
    },
    {
      label: "Temiz Export",
      to: latestUpload
        ? `/temiz-veri-seti?upload_id=${latestUpload.id}`
        : withUploadContext("/temiz-veri-seti"),
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
            className="ui-btn-secondary"
          >
            <i className="ri-refresh-line" />
            Yenile
          </button>
        }
      />

      <div className="flex-1 space-y-6 overflow-y-auto p-6 lg:p-8">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {overview.error ? (
            <div className="col-span-full rounded-2xl border border-danger-200 bg-danger-50 p-4 text-sm font-medium text-danger-700 shadow-sm">
              Veri yüklenemedi
            </div>
          ) : (
            <>
              <SummaryCard label="Toplam Kayıt" value={overview.loading ? "..." : formatNumber(totalNormalized)} tone="blue" icon="ri-database-2-line" />
              <SummaryCard
                label="Bekleyen İnceleme"
                value={overview.loading ? "..." : formatNumber(overview.data?.pending)}
                tone="yellow"
                icon="ri-time-line"
                to={
                  latestUpload
                    ? `/mukerrer-kayitlar?upload_id=${latestUpload.id}&decision=pending`
                    : withUploadContext("/mukerrer-kayitlar?decision=pending")
                }
              />
              <SummaryCard label="Onaylanan" value={overview.loading ? "..." : formatNumber(overview.data?.approved)} tone="green" icon="ri-checkbox-circle-line" />
              <SummaryCard label="Mükerrer Oran" value={overview.loading ? "..." : `%${duplicateRate.toFixed(1)}`} tone="purple" icon="ri-percent-line" />
            </>
          )}
        </div>

        <div className="ui-card p-6 shadow-card-lg">
          <div className="mb-4 text-sm font-semibold tracking-tight text-slate-900">Pipeline Durumu</div>
          <SectionMessage loading={uploads.loading || overview.loading} error={uploads.error || overview.error} />
          {!uploads.loading && !overview.loading && !uploads.error && !overview.error && (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
              {pipeline.map((step, index) => (
                <button
                  key={step.label}
                  onClick={() => navigate(step.to)}
                  className="cursor-pointer rounded-2xl border border-slate-200/90 bg-slate-50/80 p-4 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary-200 hover:bg-white hover:shadow-card"
                >
                  <div className="flex items-center justify-between text-sm font-semibold text-slate-900">
                    <span>{step.label}</span>
                    {index < pipeline.length - 1 && <i className="ri-arrow-right-line text-slate-300" />}
                  </div>
                  <div className="mt-2 text-xs font-medium text-slate-500">{formatDate(step.date)}</div>
                  <div className="mt-1 text-xs font-semibold text-slate-700">{formatNumber(step.count)} kayıt</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {latestUpload?.id != null && (
          <div
            className="rounded-2xl border border-slate-200/90 bg-slate-50/80 p-4 text-sm leading-relaxed text-slate-600 shadow-sm"
            lang={locale}
          >
            <span className="font-semibold text-slate-800">{t("dashboard.postApprovalLead")} </span>
            <Link
              to={`/mukerrer-kayitlar?upload_id=${latestUpload.id}`}
              className="font-semibold text-primary-700 hover:underline"
            >
              {t("dashboard.postApprovalLink")}
            </Link>
            {" "}
            {t("dashboard.postApprovalTrail")}
          </div>
        )}

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
          <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-card xl:col-span-3">
            <div className="border-b border-slate-100 bg-slate-50/50 px-5 py-4 text-sm font-semibold tracking-tight text-slate-900">
              Son Yüklemeler
            </div>
            <SectionMessage loading={uploads.loading} error={uploads.error} />
            {!uploads.loading && !uploads.error && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-100 bg-slate-50/90">
                      <th className="px-4 py-3.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Dosya adı
                      </th>
                      <th className="px-4 py-3.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Kayıt
                      </th>
                      <th className="px-4 py-3.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Durum
                      </th>
                      <th className="px-4 py-3.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Tarih
                      </th>
                      <th className="px-4 py-3.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">
                        İşlem
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {(uploads.data || []).map((upload) => (
                      <tr key={upload.id} className="transition-colors hover:bg-primary-50/40">
                        <td className="px-4 py-3.5 font-medium text-slate-900">{upload.file_name}</td>
                        <td className="px-4 py-3.5 tabular-nums text-slate-600">{formatNumber(upload.total_records)}</td>
                        <td className="px-4 py-3.5 text-slate-600">{upload.processing_stage || upload.status}</td>
                        <td className="px-4 py-3.5 text-slate-500">{formatDate(upload.created_at)}</td>
                        <td className="px-4 py-3 text-right">
                          <Link
                            to={
                              upload.latest_normalization_run_id
                                ? `/mukerrer-tespit?upload_id=${upload.id}`
                                : `/veri-normalizasyon?upload_id=${upload.id}`
                            }
                            className="inline-flex items-center gap-1 rounded-lg bg-gradient-to-r from-primary-600 to-primary-700 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:from-primary-500 hover:to-primary-600"
                          >
                            {upload.latest_normalization_run_id ? "Mükerrer Tespit" : "Normalize Et"}
                          </Link>
                        </td>
                      </tr>
                    ))}
                    {(uploads.data || []).length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-5 py-12 text-center text-sm font-medium text-slate-400">
                          Yükleme bulunamadı.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white shadow-card xl:col-span-2">
            <div className="border-b border-slate-100 bg-slate-50/50 px-5 py-4 text-sm font-semibold tracking-tight text-slate-900">
              Bekleyen İncelemeler
            </div>
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
                        to={withUploadContext(`/mukerrer-kayitlar?group_id=match_${match.id}`)}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-primary-700 hover:text-primary-600 hover:underline"
                      >
                        İncele <i className="ri-arrow-right-line" />
                      </Link>
                    </div>
                  );
                })}
                {(pending.data || []).length === 0 && (
                  <div className="py-10 text-center text-sm font-medium text-slate-400">Bekleyen inceleme yok.</div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div className="ui-card p-6 shadow-card-lg">
            <h3 className="mb-5 text-sm font-semibold tracking-tight text-slate-900">Veri Kalitesi Özeti</h3>
            <SectionMessage loading={quality.loading} error={quality.error} />
            {!quality.loading && !quality.error && quality.data && (
              <div className="space-y-4">
                <QualityBar label="TC doluluğu" value={quality.data.tc_fill_rate ?? quality.data.validity_rate ?? 0} />
                <QualityBar label="Telefon doluluğu" value={quality.data.phone_fill_rate ?? 0} />
                <QualityBar label="E-mail doluluğu" value={quality.data.email_fill_rate ?? 0} />
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white shadow-card">
            <div className="border-b border-slate-100 bg-slate-50/50 px-5 py-4 text-sm font-semibold tracking-tight text-slate-900">
              Son Kararlar
            </div>
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
                      <span className={approved ? "font-semibold text-emerald-700" : "font-semibold text-danger-700"}>
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
