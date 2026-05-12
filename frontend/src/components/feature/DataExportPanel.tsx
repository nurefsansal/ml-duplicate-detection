import { useState } from "react";
import { Link } from "react-router-dom";
import { useI18n } from "../../i18n/I18nProvider";
import {
  buildNormalizedRecordsExportUrl,
  downloadApprovedMatchesCsv,
  downloadCleanDatasetCsv,
  downloadDuplicateGroupsCsv,
  downloadGoldenRecordsCsv,
  downloadMergeLineageReportCsv,
  downloadNarrativeReportTxt,
} from "../../services/api";

type Props = {
  uploadId: number | null;
  variant?: "default" | "compact";
  flowContext?: "default" | "post_duplicate_review";
};

function LangSegment({
  ariaLabel,
  trLabel,
  enLabel,
  value,
  onChange,
}: {
  ariaLabel: string;
  trLabel: string;
  enLabel: string;
  value: "tr" | "en";
  onChange: (v: "tr" | "en") => void;
}) {
  const seg =
    "inline-flex rounded-lg border border-slate-200/80 bg-slate-100/90 p-0.5 text-[11px] font-bold shadow-inner";
  const btn = (active: boolean) =>
    `min-w-[2.75rem] rounded-md px-2 py-1.5 transition-colors ${
      active
        ? "bg-white text-primary-700 shadow-sm"
        : "text-slate-500 hover:text-slate-800"
    }`;

  return (
    <div className="flex flex-col items-end gap-1">
      <span className="sr-only">{ariaLabel}</span>
      <div className={seg} role="group" aria-label={ariaLabel}>
        <button
          type="button"
          className={btn(value === "tr")}
          onClick={() => onChange("tr")}
          aria-pressed={value === "tr"}
        >
          {trLabel}
        </button>
        <button
          type="button"
          className={btn(value === "en")}
          onClick={() => onChange("en")}
          aria-pressed={value === "en"}
        >
          {enLabel}
        </button>
      </div>
    </div>
  );
}

/**
 * Yükleme bazlı dışa aktarma: okunaklı adımlar + TR/EN dil desteği.
 */
export function DataExportPanel({
  uploadId,
  variant = "default",
  flowContext = "default",
}: Props) {
  const { locale, setLocale, t, ta } = useI18n();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState("");

  const pad = variant === "compact" ? "p-5" : "p-6";

  const run = async (key: string, fn: () => Promise<void>) => {
    setErr("");
    setBusy(key);
    try {
      await fn();
    } catch {
      setErr(t("exportPanel.downloadFailed"));
    } finally {
      setBusy(null);
    }
  };

  if (uploadId === null) {
    return (
      <div
        className={`ui-card ${pad} border-dashed border-slate-200 bg-slate-50/60 shadow-card`}
        lang={locale}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-800">{t("exportPanel.emptyTitle")}</p>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-slate-600">
              {t("exportPanel.emptyBody")}
            </p>
          </div>
          <LangSegment
            ariaLabel={t("exportPanel.langAria")}
            trLabel={t("exportPanel.toggleTr")}
            enLabel={t("exportPanel.toggleEn")}
            value={locale}
            onChange={setLocale}
          />
        </div>
      </div>
    );
  }

  const csvUrl = buildNormalizedRecordsExportUrl({ upload_id: uploadId, format: "csv" });
  const xlsxUrl = buildNormalizedRecordsExportUrl({ upload_id: uploadId, format: "xlsx" });
  const jsonUrl = buildNormalizedRecordsExportUrl({ upload_id: uploadId, format: "json" });

  const eyebrow =
    flowContext === "post_duplicate_review"
      ? t("exportPanel.eyebrowPostReview")
      : t("exportPanel.eyebrowDefault");
  const title =
    flowContext === "post_duplicate_review"
      ? t("exportPanel.titlePostReview", { uploadId })
      : t("exportPanel.titleDefault", { uploadId });
  const blurb =
    flowContext === "post_duplicate_review"
      ? t("exportPanel.blurbPostReview")
      : t("exportPanel.blurbDefault");

  const step2Title =
    flowContext === "post_duplicate_review"
      ? t("exportPanel.step2TitlePostReview")
      : t("exportPanel.step2TitleDefault");

  const bullets = ta("exportPanel.step1Bullets");

  const fmtCard =
    "flex flex-1 flex-col rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm transition-shadow hover:shadow-md min-w-[140px]";
  const fmtLink =
    "mt-3 inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-primary-200 bg-primary-50/80 px-3 py-2.5 text-xs font-semibold text-primary-800 hover:bg-primary-100/90";

  const reportCard =
    "flex h-full flex-col rounded-xl border border-slate-200/90 bg-slate-50/40 p-4 text-left shadow-sm";
  const reportBtn =
    "mt-auto inline-flex w-full items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-xs font-semibold transition-all disabled:opacity-55";
  const reportBtnPrimary = `${reportBtn} border-primary-200 bg-gradient-to-r from-primary-600 to-indigo-600 text-white shadow-sm hover:from-primary-500 hover:to-indigo-500`;
  const reportBtnNeutral = `${reportBtn} border-slate-200 bg-white text-slate-700 hover:border-primary-200 hover:bg-primary-50/50`;

  const reportDefs = [
    {
      key: "clean" as const,
      busyKey: "clean",
      icon: "ri-database-2-line",
      primary: true,
      onClick: () => run("clean", () => downloadCleanDatasetCsv({ uploadId })),
    },
    {
      key: "lineage" as const,
      busyKey: "lineage",
      icon: "ri-git-merge-line",
      primary: false,
      onClick: () => run("lineage", () => downloadMergeLineageReportCsv({ uploadId })),
    },
    {
      key: "narrative" as const,
      busyKey: "narrative",
      icon: "ri-article-line",
      primary: false,
      onClick: () =>
        run("narrative", () =>
          downloadNarrativeReportTxt({
            uploadId,
            lang: locale === "en" ? "en" : "tr",
          }),
        ),
    },
    {
      key: "groups" as const,
      busyKey: "groups",
      icon: "ri-group-line",
      primary: false,
      onClick: () =>
        run("groups", () => downloadDuplicateGroupsCsv({ uploadId, decision: "approved" })),
    },
    {
      key: "matches" as const,
      busyKey: "matches",
      icon: "ri-links-line",
      primary: false,
      onClick: () => run("matches", () => downloadApprovedMatchesCsv({ uploadId })),
    },
    {
      key: "golden" as const,
      busyKey: "golden",
      icon: "ri-vip-crown-line",
      primary: false,
      onClick: () =>
        run("golden", () => downloadGoldenRecordsCsv({ uploadId, decision: "approved" })),
    },
  ];

  return (
    <section
      className={`ui-card ${pad} shadow-card-lg`}
      lang={locale}
      aria-labelledby="export-panel-title"
    >
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-5">
        <div className="min-w-0 max-w-3xl space-y-2">
          <p className="text-[11px] font-bold uppercase tracking-wider text-primary-700">
            {eyebrow}
          </p>
          <h2 id="export-panel-title" className="text-base font-semibold leading-snug text-slate-900">
            {title}
          </h2>
          <p className="text-sm leading-relaxed text-slate-600">{blurb}</p>
        </div>
        <div className="flex flex-shrink-0 flex-col items-end gap-3 sm:flex-row sm:items-start">
          <LangSegment
            ariaLabel={t("exportPanel.langAria")}
            trLabel={t("exportPanel.toggleTr")}
            enLabel={t("exportPanel.toggleEn")}
            value={locale}
            onChange={setLocale}
          />
          <Link
            to={`/temiz-veri-seti?upload_id=${uploadId}`}
            className="flex flex-col items-end rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-right transition-colors hover:border-primary-200 hover:bg-primary-50/40"
          >
            <span className="text-xs font-semibold text-primary-700">{t("exportPanel.previewLink")}</span>
            <span className="text-[11px] text-slate-500">{t("exportPanel.previewHint")}</span>
          </Link>
        </div>
      </div>

      {err ? (
        <div
          className="mb-6 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-900"
          role="alert"
        >
          <i className="ri-error-warning-line mt-0.5 flex-shrink-0 text-base" aria-hidden />
          <span>{err}</span>
        </div>
      ) : null}

      <div className="space-y-8">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-primary-100 px-2 py-0.5 text-[11px] font-bold text-primary-800">
              {t("exportPanel.step1Badge")}
            </span>
            <h3 className="text-sm font-semibold text-slate-900">{t("exportPanel.step1Title")}</h3>
          </div>
          <ul className="mb-4 list-inside list-disc space-y-1.5 text-sm leading-relaxed text-slate-600">
            {bullets.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-3">
            <div className={fmtCard}>
              <div className="text-xs font-semibold text-slate-800">{t("exportPanel.formatCsv")}</div>
              <p className="mt-1 text-[11px] leading-snug text-slate-500">{t("exportPanel.formatCsvHint")}</p>
              <a href={csvUrl} target="_blank" rel="noreferrer" className={fmtLink}>
                <i className="ri-download-cloud-2-line" aria-hidden />
                {t("exportPanel.formatCsv")}
              </a>
            </div>
            <div className={fmtCard}>
              <div className="text-xs font-semibold text-slate-800">{t("exportPanel.formatXlsx")}</div>
              <p className="mt-1 text-[11px] leading-snug text-slate-500">{t("exportPanel.formatXlsxHint")}</p>
              <a href={xlsxUrl} target="_blank" rel="noreferrer" className={fmtLink}>
                <i className="ri-download-cloud-2-line" aria-hidden />
                {t("exportPanel.formatXlsx")}
              </a>
            </div>
            <div className={fmtCard}>
              <div className="text-xs font-semibold text-slate-800">{t("exportPanel.formatJson")}</div>
              <p className="mt-1 text-[11px] leading-snug text-slate-500">{t("exportPanel.formatJsonHint")}</p>
              <a href={jsonUrl} target="_blank" rel="noreferrer" className={fmtLink}>
                <i className="ri-download-cloud-2-line" aria-hidden />
                {t("exportPanel.formatJson")}
              </a>
            </div>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-slate-500">{t("exportPanel.step1TechNote")}</p>
        </div>

        <div className="border-t border-slate-100 pt-6">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-slate-200/90 px-2 py-0.5 text-[11px] font-bold text-slate-700">
              {t("exportPanel.step2Badge")}
            </span>
            <h3 className="text-sm font-semibold text-slate-900">{step2Title}</h3>
          </div>
          <p className="mb-4 text-sm leading-relaxed text-slate-600">{t("exportPanel.step2Intro")}</p>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {reportDefs.map((def) => {
              const copy = t(`exportPanel.actions.${def.key}.label`);
              const desc = t(`exportPanel.actions.${def.key}.desc`);
              const isBusy = busy === def.busyKey;
              return (
                <div key={def.key} className={reportCard}>
                  <div className="mb-2 flex items-start gap-2">
                    <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-white text-primary-600 shadow-sm ring-1 ring-slate-100">
                      <i className={`${def.icon} text-lg`} aria-hidden />
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-900">{copy}</p>
                      <p className="mt-1 text-xs leading-relaxed text-slate-600">{desc}</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={busy !== null}
                    className={def.primary ? reportBtnPrimary : reportBtnNeutral}
                    onClick={def.onClick}
                  >
                    {isBusy ? (
                      <i className="ri-loader-4-line animate-spin" aria-hidden />
                    ) : (
                      <i className="ri-file-download-line" aria-hidden />
                    )}
                    {copy}
                  </button>
                </div>
              );
            })}
          </div>
          <p className="mt-4 text-xs leading-relaxed text-slate-400">{t("exportPanel.step2TechNote")}</p>
        </div>
      </div>
    </section>
  );
}
