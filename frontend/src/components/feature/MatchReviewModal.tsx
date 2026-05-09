import { useEffect } from "react";

import {

  approvePendingMatch,

  rejectPendingMatch,

  resetMatchDecision,

  type AdminPendingMatch,

} from "../../services/api";



function valueOrDash(value: unknown): string {

  const s = value == null ? "" : String(value).trim();

  return s ? s : "—";

}



function scoreText(match: AdminPendingMatch): string {

  if (typeof match.final_score === "number") return `${match.final_score.toFixed(1)}%`;

  const ml = Number(match.ml_score || 0);

  return `%${(ml * 100).toFixed(1)}`;

}



const COMPONENT_LABELS: Record<string, string> = {

  adSoyad: "Ad Soyad",

  tcKimlikNo: "TC Kimlik",

  telefon: "Telefon",

  email: "E-posta",

  muhatapNo: "Muhatap",

};



function ScoreBreakdownPanel(props: {

  breakdown?: Record<string, unknown> | null;

}) {

  const { breakdown } = props;

  if (!breakdown || typeof breakdown !== "object") return null;

  const general =

    typeof breakdown.general_weighted_percent === "number"

      ? breakdown.general_weighted_percent

      : null;

  const raw = breakdown.components_percent;

  if (!raw || typeof raw !== "object") return null;

  const entries = Object.entries(raw as Record<string, unknown>).filter(

    ([, v]) => typeof v === "number",

  ) as [string, number][];

  if (entries.length === 0) return null;

  return (

    <div className="mx-5 mb-4 rounded-2xl border border-slate-200/90 bg-gradient-to-br from-slate-50 to-primary-50/40 p-5 shadow-inner">

      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">

        <div>

          <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-700">

            Skor kırılımı

          </p>

          <p className="text-xs font-medium text-slate-500">Ayarlar ağırlıklarına göre alan bazlı katkı</p>

        </div>

        {general != null ? (

          <span className="inline-flex items-center rounded-full border border-primary-200 bg-white px-3 py-1 text-sm font-semibold tabular-nums text-primary-800 shadow-sm">

            Genel {general.toFixed(1)}%

          </span>

        ) : null}

      </div>

      <div className="grid gap-4 sm:grid-cols-2">

        {entries.map(([key, pct]) => (

          <div

            key={key}

            className="rounded-xl border border-white/80 bg-white/70 p-3 shadow-sm backdrop-blur-sm"

          >

            <div className="mb-2 flex justify-between text-xs font-medium text-slate-600">

              <span>{COMPONENT_LABELS[key] ?? key}</span>

              <span className="tabular-nums text-slate-900">{pct.toFixed(1)}%</span>

            </div>

            <div className="h-2 overflow-hidden rounded-full bg-slate-200/80">

              <div

                className="h-full rounded-full bg-gradient-to-r from-primary-500 to-indigo-500 transition-[width] duration-500 ease-out"

                style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}

              />

            </div>

          </div>

        ))}

      </div>

    </div>

  );

}



export function MatchReviewModal(props: {

  open: boolean;

  match: AdminPendingMatch | null;

  index: number;

  total: number;

  canReset: boolean;

  busy: boolean;

  error: string | null;

  onClose: () => void;

  onPrev: () => void;

  onNext: () => void;

  onBusyChange: (busy: boolean) => void;

  onError: (message: string | null) => void;

  onAfterAction: () => void;

}) {

  const { open, match } = props;



  useEffect(() => {

    if (!open) return;

    const onKeyDown = (e: KeyboardEvent) => {

      if (!open) return;

      if (e.key === "Escape") props.onClose();

      if (e.key === "ArrowLeft") props.onPrev();

      if (e.key === "ArrowRight") props.onNext();

      if (e.key.toLowerCase() === "a") void handleApprove();

      if (e.key.toLowerCase() === "r") void handleReject();

      if (e.key.toLowerCase() === "u") void handleReset();

    };

    window.addEventListener("keydown", onKeyDown);

    return () => window.removeEventListener("keydown", onKeyDown);

    // eslint-disable-next-line react-hooks/exhaustive-deps

  }, [open, match, props.canReset, props.index, props.total]);



  if (!open || !match) return null;



  const handleApprove = async () => {

    props.onBusyChange(true);

    props.onError(null);

    try {

      await approvePendingMatch({ matchId: match.id });

      props.onAfterAction();

      props.onNext();

    } catch (e) {

      props.onError(e instanceof Error ? e.message : "Onay başarısız.");

    } finally {

      props.onBusyChange(false);

    }

  };



  const handleReject = async () => {

    props.onBusyChange(true);

    props.onError(null);

    try {

      await rejectPendingMatch({ matchId: match.id });

      props.onAfterAction();

      props.onNext();

    } catch (e) {

      props.onError(e instanceof Error ? e.message : "Red başarısız.");

    } finally {

      props.onBusyChange(false);

    }

  };



  const handleReset = async () => {

    if (!props.canReset) return;

    props.onBusyChange(true);

    props.onError(null);

    try {

      await resetMatchDecision({ matchId: match.id });

      props.onAfterAction();

    } catch (e) {

      props.onError(e instanceof Error ? e.message : "Reset başarısız.");

    } finally {

      props.onBusyChange(false);

    }

  };



  return (

    <div

      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-[2px]"

      onClick={props.onClose}

      role="presentation"

    >

      <div

        className="max-h-[min(92vh,900px)] w-full max-w-5xl overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-card-lg"

        onClick={(e) => e.stopPropagation()}

        role="dialog"

        aria-modal="true"

        aria-labelledby="match-review-title"

      >

        <div className="flex items-start justify-between gap-4 border-b border-slate-100 bg-gradient-to-r from-white to-slate-50/80 px-6 py-5">

          <div>

            <h2 id="match-review-title" className="text-base font-semibold tracking-tight text-slate-900">

              Aday eşleşme #{match.id}

              <span className="ml-2 text-sm font-normal text-slate-500">

                ({props.index + 1} / {props.total})

              </span>

            </h2>

            <p className="mt-1.5 text-xs font-medium text-slate-500">

              Kısayollar: ←/→ gez, <kbd className="rounded bg-slate-100 px-1 font-mono text-[11px]">A</kbd>{" "}

              onayla, <kbd className="rounded bg-slate-100 px-1 font-mono text-[11px]">R</kbd> reddet,{" "}

              <kbd className="rounded bg-slate-100 px-1 font-mono text-[11px]">U</kbd> geri al,{" "}

              <kbd className="rounded bg-slate-100 px-1 font-mono text-[11px]">Esc</kbd> kapat

            </p>

          </div>

          <div className="flex flex-shrink-0 items-center gap-2">

            <span className="inline-flex items-center rounded-full border border-primary-200 bg-primary-50 px-3 py-1.5 text-xs font-semibold tabular-nums text-primary-900">

              Skor {scoreText(match)}

            </span>

            <button

              type="button"

              onClick={props.onClose}

              className="ui-btn-secondary !py-2 !text-xs"

            >

              Kapat

            </button>

          </div>

        </div>



        {props.error ? (

          <div className="mx-6 mt-4 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">

            {props.error}

          </div>

        ) : null}



        <div className="grid grid-cols-1 gap-4 p-6 md:grid-cols-2">

          <div className="rounded-2xl border border-slate-200/90 bg-gradient-to-b from-white to-slate-50/50 p-5 shadow-sm transition-shadow hover:shadow-md">

            <div className="mb-3 flex items-center gap-2">

              <span className="rounded-lg bg-slate-900 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">

                Sol

              </span>

              <span className="text-xs font-medium text-slate-500">Kayıt A</span>

            </div>

            <div className="text-lg font-semibold tracking-tight text-slate-900">

              {valueOrDash(match.donor1_name)}

            </div>

            <dl className="mt-4 space-y-2 text-sm text-slate-700">

              {[

                ["TC", match.donor1_tc],

                ["Telefon", match.donor1_phone],

                ["E-posta", match.donor1_email],

                ["Şehir", match.donor1_city],

                ["Muhatap", match.donor1_muhatap_no],

              ].map(([label, val]) => (

                <div key={label} className="flex gap-2">

                  <dt className="w-20 flex-shrink-0 text-xs font-medium text-slate-400">{label}</dt>

                  <dd className="min-w-0 break-words">{valueOrDash(val)}</dd>

                </div>

              ))}

            </dl>

          </div>



          <div className="rounded-2xl border border-slate-200/90 bg-gradient-to-b from-white to-slate-50/50 p-5 shadow-sm transition-shadow hover:shadow-md">

            <div className="mb-3 flex items-center gap-2">

              <span className="rounded-lg bg-primary-700 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">

                Sağ

              </span>

              <span className="text-xs font-medium text-slate-500">Kayıt B</span>

            </div>

            <div className="text-lg font-semibold tracking-tight text-slate-900">

              {valueOrDash(match.donor2_name)}

            </div>

            <dl className="mt-4 space-y-2 text-sm text-slate-700">

              {[

                ["TC", match.donor2_tc],

                ["Telefon", match.donor2_phone],

                ["E-posta", match.donor2_email],

                ["Şehir", match.donor2_city],

                ["Muhatap", match.donor2_muhatap_no],

              ].map(([label, val]) => (

                <div key={label} className="flex gap-2">

                  <dt className="w-20 flex-shrink-0 text-xs font-medium text-slate-400">{label}</dt>

                  <dd className="min-w-0 break-words">{valueOrDash(val)}</dd>

                </div>

              ))}

            </dl>

          </div>

        </div>



        <ScoreBreakdownPanel breakdown={match.score_breakdown ?? null} />



        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/50 px-6 py-4">

          <div className="flex items-center gap-2">

            <button

              type="button"

              disabled={props.busy || props.index <= 0}

              onClick={props.onPrev}

              className="ui-btn-secondary !py-2 disabled:pointer-events-none disabled:opacity-40"

            >

              ← Önceki

            </button>

            <button

              type="button"

              disabled={props.busy || props.index >= props.total - 1}

              onClick={props.onNext}

              className="ui-btn-secondary !py-2 disabled:pointer-events-none disabled:opacity-40"

            >

              Sonraki →

            </button>

          </div>



          <div className="flex flex-wrap items-center gap-2">

            <button

              type="button"

              disabled={props.busy || !props.canReset}

              onClick={handleReset}

              className="inline-flex items-center rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-950 transition-colors hover:bg-amber-100 disabled:opacity-40"

            >

              Geri al

            </button>

            <button

              type="button"

              disabled={props.busy}

              onClick={handleReject}

              className="inline-flex items-center rounded-xl border border-danger-200 bg-danger-50 px-4 py-2 text-sm font-semibold text-danger-700 transition-colors hover:bg-danger-100 disabled:opacity-40"

            >

              Reddet

            </button>

            <button type="button" disabled={props.busy} onClick={handleApprove} className="ui-btn-primary">

              Onayla

            </button>

          </div>

        </div>

      </div>

    </div>

  );

}

