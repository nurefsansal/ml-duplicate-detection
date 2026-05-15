import { useNavigate } from "react-router-dom";
import { useUploadPipelineStatus } from "../../hooks/useUploadPipelineStatus";

type FlowStep = "upload" | "standardize" | "detect" | "review" | "reports";

const STEP_META: Array<{
  id: FlowStep;
  label: string;
  stepNum: number;
  icon: string;
}> = [
  { id: "upload", label: "Yükle", stepNum: 1, icon: "ri-upload-cloud-2-line" },
  { id: "standardize", label: "Standardize Et", stepNum: 2, icon: "ri-filter-3-line" },
  { id: "detect", label: "Mükerrer Tespit", stepNum: 3, icon: "ri-search-eye-line" },
  { id: "review", label: "İncele & Birleştir", stepNum: 4, icon: "ri-file-copy-2-line" },
  { id: "reports", label: "Raporlar", stepNum: 5, icon: "ri-bar-chart-box-line" },
];

const STEP_ORDER: Record<FlowStep, number> = {
  upload: 0,
  standardize: 1,
  detect: 2,
  review: 3,
  reports: 4,
};

const NEXT_ACTION: Partial<Record<FlowStep, { label: string; target: FlowStep }>> = {
  upload: { label: "Sonraki: Standardizasyon", target: "standardize" },
  standardize: { label: "Sonraki: Mükerrer Tespit", target: "detect" },
  detect: { label: "Sonraki: İncele & Birleştir", target: "review" },
  review: { label: "Sonraki: Raporlar", target: "reports" },
};

export function FlowNav(props: {
  uploadId?: number | null;
  step: FlowStep;
  canGoNext?: boolean;
}) {
  const navigate = useNavigate();
  const uploadId = props.uploadId ?? null;
  const currentOrder = STEP_ORDER[props.step];
  const { canReview, loading: pipelineLoading } = useUploadPipelineStatus(uploadId);

  const go = (path: string) => navigate(path);

  const canNavigateTo = (target: FlowStep) => {
    if (target === "upload") return true;
    if (uploadId === null) return false;
    if (target === "review") return canReview;
    return true;
  };

  const pathFor = (target: FlowStep) => {
    if (target === "upload") return "/veri-yukleme";
    if (target === "standardize") {
      return uploadId ? `/veri-normalizasyon?upload_id=${uploadId}` : "/veri-normalizasyon";
    }
    if (target === "detect") {
      return uploadId ? `/mukerrer-tespit?upload_id=${uploadId}` : "/mukerrer-tespit";
    }
    if (target === "review") {
      return uploadId
        ? `/mukerrer-kayitlar?upload_id=${uploadId}&decision=pending`
        : "/mukerrer-kayitlar";
    }
    return uploadId ? `/raporlar?upload_id=${uploadId}` : "/raporlar";
  };

  const nextAction = NEXT_ACTION[props.step];
  const nextTarget = nextAction?.target;
  const nextEnabled =
    nextAction !== undefined &&
    uploadId !== null &&
    props.canGoNext !== false &&
    (nextTarget !== "review" || canReview);

  return (
    <div className="ui-card overflow-hidden p-5 shadow-card-lg">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-700">Pipeline</p>
          <p className="mt-0.5 text-sm font-medium text-slate-600">
            Ham veriden raporlamaya rehber akış
          </p>
        </div>
      </div>

      {uploadId !== null && !canReview && !pipelineLoading && props.step !== "detect" ? (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-900">
          <i className="ri-information-line mt-0.5 text-base" aria-hidden />
          <span>
            İnceleme adımı için önce bu dosyada{" "}
            <strong>Mükerrer Tespit</strong> çalıştırılmalıdır.
          </span>
        </div>
      ) : null}

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-1 flex-wrap items-stretch gap-2 md:gap-3">
          {STEP_META.map((s, idx) => {
            const active = s.id === props.step;
            const needsDetection = s.id === "review";
            const enabled = canNavigateTo(s.id);
            const done = STEP_ORDER[s.id] < currentOrder;

            return (
              <div key={s.id} className="flex min-w-[100px] flex-1 items-center gap-2 sm:min-w-[120px] md:min-w-[130px]">
                <button
                  type="button"
                  disabled={!enabled}
                  title={
                    needsDetection && !enabled && uploadId !== null
                      ? "Önce Mükerrer Tespit adımını tamamlayın"
                      : undefined
                  }
                  aria-current={active ? "step" : undefined}
                  aria-label={`${s.label}, adım ${s.stepNum}`}
                  onClick={() => enabled && go(pathFor(s.id))}
                  className={`flex w-full flex-col items-center gap-1.5 rounded-2xl px-2 py-3 text-center transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 md:gap-2 md:px-3 ${
                    active
                      ? "bg-gradient-to-br from-primary-600 to-indigo-700 text-white shadow-lg shadow-primary-900/15 ring-1 ring-primary-400/40"
                      : done
                        ? "border border-emerald-200 bg-emerald-50 text-emerald-900 hover:bg-emerald-100"
                        : enabled
                          ? "cursor-pointer border border-slate-200 bg-slate-50 text-slate-700 hover:border-primary-200 hover:bg-white hover:shadow-md"
                          : "cursor-not-allowed border border-slate-100 bg-slate-50 text-slate-400 opacity-75"
                  }`}
                >
                  <span
                    className={`flex h-9 w-9 items-center justify-center rounded-xl text-base ${
                      active
                        ? "bg-white/20"
                        : done
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-white text-slate-500 shadow-sm"
                    }`}
                  >
                    <i className={done && !active ? "ri-check-line" : s.icon} aria-hidden />
                  </span>
                  <span className="text-xs font-semibold leading-tight">{s.label}</span>
                  <span
                    className={`text-[10px] font-medium uppercase tracking-wide ${
                      active ? "text-primary-100" : done ? "text-emerald-700/90" : "text-slate-400"
                    }`}
                  >
                    Adım {s.stepNum}
                  </span>
                </button>
                {idx < STEP_META.length - 1 ? (
                  <div
                    className={`hidden h-0.5 w-4 flex-shrink-0 md:block lg:w-6 ${
                      STEP_ORDER[STEP_META[idx + 1].id] <= currentOrder
                        ? "bg-gradient-to-r from-primary-400 to-indigo-400 opacity-90"
                        : "bg-slate-200"
                    }`}
                    aria-hidden
                  />
                ) : null}
              </div>
            );
          })}
        </div>

        {nextAction ? (
          <div className="flex flex-shrink-0 flex-wrap items-center justify-end gap-2 border-t border-slate-100 pt-4 lg:border-t-0 lg:pt-0">
            <button
              type="button"
              disabled={!nextEnabled}
              title={
                nextTarget === "review" && !canReview
                  ? "Önce Mükerrer Tespit adımını tamamlayın"
                  : undefined
              }
              onClick={() => nextEnabled && go(pathFor(nextAction.target))}
              className="ui-btn-primary ui-focus-ring disabled:opacity-60"
            >
              {nextAction.label}
              <i className="ri-arrow-right-line text-lg" aria-hidden />
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
