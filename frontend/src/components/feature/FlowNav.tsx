import { useNavigate } from "react-router-dom";



const STEP_META = [

  { id: "upload" as const, label: "Yükle", stepNum: 1, icon: "ri-upload-cloud-2-line", toKey: "upload" as const },

  {

    id: "standardize" as const,

    label: "Standardize Et",

    stepNum: 2,

    icon: "ri-filter-3-line",

    toKey: "standardize" as const,

  },

  { id: "detect" as const, label: "Mükerrer Tespit", stepNum: 3, icon: "ri-search-eye-line", toKey: "detect" as const },

];



export function FlowNav(props: {

  uploadId?: number | null;

  step: "upload" | "standardize" | "detect";

  canGoNext?: boolean;

}) {

  const navigate = useNavigate();

  const uploadId = props.uploadId ?? null;



  const go = (path: string) => navigate(path);



  const order: Record<typeof props.step, number> = {

    upload: 0,

    standardize: 1,

    detect: 2,

  };



  const canNavigateTo = (target: "upload" | "standardize" | "detect") => {

    if (order[target] <= order[props.step]) return true;

    if (props.canGoNext === false) return false;

    if (!uploadId) return false;

    return true;

  };



  const pathFor = (target: "upload" | "standardize" | "detect") => {

    if (target === "upload") return "/veri-yukleme";

    if (target === "standardize") {

      return uploadId ? `/veri-normalizasyon?upload_id=${uploadId}` : "/veri-normalizasyon";

    }

    return uploadId ? `/mukerrer-tespit?upload_id=${uploadId}` : "/mukerrer-tespit";

  };



  return (

    <div className="ui-card overflow-hidden p-5 shadow-card-lg">

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">

        <div>

          <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-700">Pipeline</p>

          <p className="mt-0.5 text-sm font-medium text-slate-600">

            Ham veriden mükerrer tespitine rehber akış

          </p>

        </div>

      </div>



      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">

        <div className="flex min-w-0 flex-1 flex-wrap items-stretch gap-2 md:gap-3">

          {STEP_META.map((s, idx) => {

            const active = s.id === props.step;

            const enabled = canNavigateTo(s.id);

            const done = order[s.id] < order[props.step];



            return (

              <div key={s.id} className="flex min-w-[120px] flex-1 items-center gap-2 md:min-w-[140px]">

                <button

                  type="button"

                  disabled={!enabled}

                  onClick={() => enabled && go(pathFor(s.id))}

                  className={`flex w-full flex-col items-center gap-1.5 rounded-2xl px-3 py-3 text-center transition-all duration-200 md:gap-2 ${

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

                      active ? "bg-white/20" : done ? "bg-emerald-100 text-emerald-700" : "bg-white text-slate-500 shadow-sm"

                    }`}

                  >

                    <i className={done && !active ? "ri-check-line" : s.icon} />

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

                    className={`hidden h-0.5 w-6 flex-shrink-0 md:block ${

                      order[STEP_META[idx + 1].id] <= order[props.step]

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



        <div className="flex flex-shrink-0 flex-wrap items-center justify-end gap-2 border-t border-slate-100 pt-4 lg:border-t-0 lg:pt-0">

          {props.step === "upload" ? (

            <button

              type="button"

              disabled={!uploadId || props.canGoNext === false}

              onClick={() => go(`/veri-normalizasyon?upload_id=${uploadId}`)}

              className="ui-btn-primary"

            >

              Sonraki: Standardizasyon

              <i className="ri-arrow-right-line text-lg" />

            </button>

          ) : props.step === "standardize" ? (

            <button

              type="button"

              disabled={!uploadId || props.canGoNext === false}

              onClick={() => go(`/mukerrer-tespit?upload_id=${uploadId}`)}

              className="ui-btn-primary"

            >

              Sonraki: Mükerrer Tespit

              <i className="ri-arrow-right-line text-lg" />

            </button>

          ) : null}

        </div>

      </div>

    </div>

  );

}

