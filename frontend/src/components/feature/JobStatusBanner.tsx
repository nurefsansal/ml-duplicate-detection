import type { JobStatusResponse } from "../../services/api";

export function JobStatusBanner(props: { job: JobStatusResponse["job"] | null }) {
  const job = props.job;
  if (!job) return null;

  const p = job.pipeline;
  const stage = p?.last_stage || null;
  const msg = p?.last_message || null;
  const warn = typeof p?.warning_count === "number" ? p.warning_count : null;
  const err = typeof p?.error_count === "number" ? p.error_count : null;

  const statusLabel =
    job.status === "completed"
      ? "Tamamlandı"
      : job.status === "failed"
        ? "Hata"
        : "Devam ediyor";

  const typeLabel =
    job.type === "upload"
      ? "Yükleme"
      : job.type === "normalization"
        ? "Standardizasyon"
        : job.type === "detection"
          ? "Tarama"
          : job.type;

  return (
    <div className="overflow-hidden rounded-2xl border border-primary-200/80 bg-gradient-to-r from-primary-50/95 via-white to-indigo-50/80 p-4 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="font-semibold text-slate-900">
          Arka plan işlemi <span className="tabular-nums text-primary-800">#{job.id}</span>
          <span className="mx-2 font-normal text-slate-400">•</span>
          <span className="text-slate-700">{typeLabel}</span>
          <span className="mx-2 font-normal text-slate-400">•</span>
          <span
            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${
              job.status === "completed"
                ? "bg-emerald-100 text-emerald-800"
                : job.status === "failed"
                  ? "bg-danger-100 text-danger-700"
                  : "bg-primary-100 text-primary-800"
            }`}
          >
            {statusLabel}
          </span>
        </div>

        <div className="text-xs font-medium text-slate-600">
          {stage ? (
            <span className="font-mono">
              aşama: <span className="font-semibold text-slate-800">{stage}</span>
            </span>
          ) : (
            <span className="text-slate-400">aşama: —</span>
          )}
          {warn != null || err != null ? (
            <>
              <span className="mx-2 text-slate-300">•</span>
              <span>
                uyarı: <strong className="text-amber-700">{warn ?? 0}</strong> / hata:{" "}
                <strong className="text-danger-700">{err ?? 0}</strong>
              </span>
            </>
          ) : null}
        </div>
      </div>

      {msg ? (
        <div className="mt-3 rounded-xl border border-slate-100 bg-white/70 px-3 py-2 text-xs leading-relaxed text-slate-700">
          <span className="font-semibold text-slate-800">Son durum:</span> {msg}
        </div>
      ) : null}
    </div>
  );
}
