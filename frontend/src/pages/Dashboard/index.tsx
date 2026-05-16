import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import DashboardLayout from "../../components/feature/DashboardLayout";
import { FlowNav } from "../../components/feature/FlowNav";
import Header from "../../components/feature/Header";
import { resolveActiveUploadId, useDashboardData } from "../../hooks/useDashboardData";
import { useUploadPipelineStatus } from "../../hooks/useUploadPipelineStatus";
import type { UploadPipelineStatus } from "../../services/api";
import { withUploadContext } from "../../utils/uploadContextNav";
import {
  formatUploadDate,
  formatUploadIdWithDate,
  formatUploadOptionLabel,
} from "../../utils/formatUploadDate";

type FlowStep = "upload" | "standardize" | "detect" | "review" | "reports";

function formatNumber(value: number | undefined | null): string {
  return Number(value || 0).toLocaleString("tr-TR");
}

function formatSyncTime(date: Date | null): string {
  if (!date) return "—";
  return date.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

function formatUploadStageLabel(
  stage: string | null | undefined,
  status: string | null | undefined,
): string {
  const value = (stage || status || "").toLowerCase();
  if (!value) return "Beklemede";
  if (value.includes("normalize")) return "Standardize edildi";
  if (value.includes("detect")) return "Tarama yapıldı";
  if (value.includes("review")) return "İnceleme";
  if (value.includes("export") || value.includes("complete")) return "Tamamlandı";
  if (value.includes("process")) return "İşleniyor";
  if (value.includes("fail") || value.includes("error")) return "Hata";
  if (value.includes("upload")) return "Yüklendi";
  return stage || status || "—";
}

function deriveFlowStep(
  pipeline: UploadPipelineStatus | null,
  pendingGroupCount: number,
): FlowStep {
  if (!pipeline) return "upload";
  if (!pipeline.has_normalized_records) return "standardize";
  if (!pipeline.has_detection_run) return "detect";
  if (pendingGroupCount > 0 || pipeline.can_review) return "review";
  return "reports";
}

function workflowStatusLabel(
  pipeline: UploadPipelineStatus | null,
  pendingTotal: number,
  ready: boolean,
): string | null {
  if (!ready || !pipeline) return null;
  if (!pipeline.has_normalized_records) return "Sıradaki adım: standardize";
  if (!pipeline.has_detection_run) return "Sıradaki adım: mükerrer tespit";
  if (pendingTotal > 0) return `${formatNumber(pendingTotal)} grup inceleme bekliyor`;
  return "İnceleme tamam — hazır veri kullanılabilir";
}

function parseUrlUploadId(raw: string | null): number | null {
  const parsed = raw ? Number(raw) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlUploadId = parseUrlUploadId(searchParams.get("upload_id"));
  const [dataUploadId, setDataUploadId] = useState<number | null>(urlUploadId);

  const { uploads, pendingTotal, pendingLoading, lastSyncedAt, refreshing, refresh } =
    useDashboardData(dataUploadId);

  const activeUploadId = useMemo(() => {
    if (!uploads.data?.length) return urlUploadId;
    return resolveActiveUploadId(uploads.data, urlUploadId);
  }, [uploads.data, urlUploadId]);

  useEffect(() => {
    if (activeUploadId !== dataUploadId) {
      setDataUploadId(activeUploadId);
    }
  }, [activeUploadId, dataUploadId]);

  const { status: pipeline, loading: pipelineLoading } = useUploadPipelineStatus(activeUploadId);

  useEffect(() => {
    if (uploads.loading || !uploads.data?.length || activeUploadId === null) return;
    if (urlUploadId === activeUploadId) return;
    setSearchParams(
      (p) => {
        p.set("upload_id", String(activeUploadId));
        return p;
      },
      { replace: true },
    );
  }, [
    activeUploadId,
    urlUploadId,
    uploads.loading,
    uploads.data,
    setSearchParams,
  ]);

  const activeUpload = useMemo(
    () => uploads.data?.find((u) => u.id === activeUploadId) ?? null,
    [uploads.data, activeUploadId],
  );

  const flowStep = deriveFlowStep(pipeline, pendingTotal);
  const pipelineReady = !pipelineLoading && !pendingLoading;
  const statusHint = workflowStatusLabel(pipeline, pendingTotal, pipelineReady);

  const reviewLink =
    activeUploadId !== null
      ? `/mukerrer-kayitlar?upload_id=${activeUploadId}&decision=pending`
      : withUploadContext("/mukerrer-kayitlar?decision=pending");

  const nextStepPath = useMemo(() => {
    if (activeUploadId === null) return "/veri-yukleme";
    if (!pipeline?.has_normalized_records) {
      return `/veri-normalizasyon?upload_id=${activeUploadId}`;
    }
    if (!pipeline?.has_detection_run) {
      return `/mukerrer-tespit?upload_id=${activeUploadId}`;
    }
    if (pendingTotal > 0) return reviewLink;
    return `/temiz-veri-seti?upload_id=${activeUploadId}`;
  }, [activeUploadId, pipeline, pendingTotal, reviewLink]);

  const nextStepLabel = useMemo(() => {
    if (activeUploadId === null) return "Veri yükle";
    if (!pipeline?.has_normalized_records) return "Standardize et";
    if (!pipeline?.has_detection_run) return "Mükerrer tespit çalıştır";
    if (pendingTotal > 0) return `${formatNumber(pendingTotal)} grup incele`;
    return "Hazır veriyi görüntüle";
  }, [activeUploadId, pipeline, pendingTotal]);

  const selectUpload = (raw: string) => {
    const id = Number(raw);
    if (!Number.isFinite(id) || id <= 0) return;
    localStorage.setItem("lastDetectUploadId", String(id));
    localStorage.setItem("lastUploadId", String(id));
    setSearchParams((p) => {
      p.set("upload_id", String(id));
      return p;
    });
  };

  return (
    <DashboardLayout>
      <Header
        title="Genel Bakış"
        subtitle="Aktif dosya ve iş akışı"
        actions={
          <div className="flex items-center gap-3">
            {lastSyncedAt ? (
              <span className="hidden text-xs text-slate-500 sm:inline">
                Güncellendi: {formatSyncTime(lastSyncedAt)}
              </span>
            ) : null}
            <button
              type="button"
              onClick={() => void refresh(activeUploadId)}
              disabled={refreshing}
              className="ui-btn-secondary"
            >
              <i className={`ri-refresh-line ${refreshing ? "animate-spin" : ""}`} aria-hidden />
              Yenile
            </button>
          </div>
        }
      />

      <div className="flex-1 space-y-6 overflow-y-auto p-6 lg:p-8">
        <section className="ui-card overflow-hidden shadow-card-lg">
          <div className="flex flex-col gap-4 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              {uploads.loading ? (
                <p className="text-sm text-slate-500">Yükleniyor…</p>
              ) : activeUpload ? (
                <>
                  <label
                    htmlFor="dashboard-upload-select"
                    className="mb-1.5 block text-xs font-medium text-slate-600"
                  >
                    Yükleme Seçin
                  </label>
                  <select
                    id="dashboard-upload-select"
                    value={activeUploadId ?? ""}
                    onChange={(e) => selectUpload(e.target.value)}
                    className="w-full max-w-md cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
                  >
                    {uploads.data!.map((u) => (
                      <option key={u.id} value={u.id}>
                        {formatUploadOptionLabel(u)}
                      </option>
                    ))}
                  </select>
                  <p className="mt-1.5 text-sm text-slate-500">
                    {formatNumber(activeUpload.total_records)} kayıt ·{" "}
                    {formatUploadStageLabel(activeUpload.processing_stage, activeUpload.status)} ·{" "}
                    {formatUploadDate(activeUpload.created_at)}
                  </p>
                  {statusHint ? (
                    <p className="mt-1 text-xs font-medium text-primary-700">{statusHint}</p>
                  ) : !pipelineReady ? (
                    <p className="mt-1 text-xs text-slate-400">Durum güncelleniyor…</p>
                  ) : null}
                </>
              ) : (
                <>
                  <h2 className="text-lg font-semibold text-slate-900">Henüz yükleme yok</h2>
                  <p className="mt-1 text-sm text-slate-500">Başlamak için veri dosyası yükleyin.</p>
                </>
              )}
            </div>

            <button
              type="button"
              onClick={() => navigate(activeUpload ? nextStepPath : "/veri-yukleme")}
              disabled={uploads.loading}
              className="ui-btn-primary w-full shrink-0 sm:w-auto"
            >
              {activeUpload ? nextStepLabel : "Veri yükle"}
              <i className="ri-arrow-right-line text-lg" aria-hidden />
            </button>
          </div>

          {activeUploadId !== null && !uploads.loading && (
            <div className="p-4 sm:p-5">
              <FlowNav uploadId={activeUploadId} step={flowStep} />
            </div>
          )}
        </section>

        <section className="ui-card overflow-hidden shadow-card">
          <div className="border-b border-slate-100 px-5 py-3">
            <h3 className="text-sm font-semibold text-slate-900">Son yüklemeler</h3>
          </div>

          {uploads.loading ? (
            <p className="py-10 text-center text-sm text-slate-500">Yükleniyor…</p>
          ) : uploads.error ? (
            <div className="py-10 text-center">
              <p className="text-sm text-danger-700">Yüklemeler alınamadı</p>
              <button
                type="button"
                onClick={() => void refresh(activeUploadId)}
                className="ui-btn-secondary mt-3 text-xs"
              >
                Tekrar dene
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <th className="px-5 py-3">Dosya</th>
                    <th className="px-4 py-3">Kayıt</th>
                    <th className="px-4 py-3">Durum</th>
                    <th className="px-4 py-3 text-right">Devam</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {(uploads.data || []).map((upload) => {
                    const isActive = upload.id === activeUploadId;
                    return (
                      <tr
                        key={upload.id}
                        className={isActive ? "bg-primary-50/60" : "hover:bg-slate-50/80"}
                      >
                        <td className="px-5 py-3">
                          <button
                            type="button"
                            onClick={() => selectUpload(String(upload.id))}
                            className={`max-w-[320px] truncate text-left font-medium ${
                              isActive
                                ? "text-primary-800"
                                : "text-slate-900 hover:text-primary-700"
                            }`}
                          >
                            {formatUploadIdWithDate(upload.id, upload.created_at)} —{" "}
                            {upload.file_name}
                            {isActive ? (
                              <span className="ml-2 text-[10px] font-semibold text-primary-600">
                                (aktif)
                              </span>
                            ) : null}
                          </button>
                        </td>
                        <td className="px-4 py-3 tabular-nums text-slate-600">
                          {formatNumber(upload.total_records)}
                        </td>
                        <td className="px-4 py-3 text-slate-600">
                          {formatUploadStageLabel(upload.processing_stage, upload.status)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Link
                            to={
                              upload.latest_normalization_run_id
                                ? `/mukerrer-tespit?upload_id=${upload.id}`
                                : `/veri-normalizasyon?upload_id=${upload.id}`
                            }
                            className="text-xs font-semibold text-primary-700 hover:underline"
                          >
                            {upload.latest_normalization_run_id ? "Tarama" : "Standardize"}
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                  {(uploads.data || []).length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-5 py-10 text-center text-slate-400">
                        <Link
                          to="/veri-yukleme"
                          className="font-semibold text-primary-700 hover:underline"
                        >
                          Veri yükle
                        </Link>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </DashboardLayout>
  );
}
