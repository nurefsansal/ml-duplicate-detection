import { useEffect, useState, type ReactNode } from "react";
import type { DuplicateGroup, DuplicateGroupRecord } from "../../services/api";

function pickScalar(v: unknown): string {
  if (v == null) return "";
  return String(v).trim();
}

function valueOrDash(v: unknown): string {
  const s = pickScalar(v);
  return s ? s : "—";
}

const GOLDEN_FIELD_ROWS: Array<{
  key: keyof DuplicateGroup["golden_record"];
  label: string;
}> = [
  { key: "clean_name", label: "Ad Soyad" },
  { key: "clean_tc", label: "TC" },
  { key: "clean_phone", label: "Telefon" },
  { key: "clean_email", label: "E-posta" },
  { key: "clean_city", label: "Şehir" },
  { key: "clean_muhatap_no", label: "Muhatap" },
  { key: "clean_address", label: "Adres" },
];

export function DuplicateGroupReviewModal(props: {
  open: boolean;
  group: DuplicateGroup | null;
  goldenPreview?: DuplicateGroup["golden_record"] | null;
  selectedRecordIds: Set<number>;
  onToggleRecord: (recordId: number) => void;
  onSelectAllRecords?: () => void;
  onClearAllRecords?: () => void;
  getRecordMuhatapNoDisplay: (record: DuplicateGroupRecord) => string;
  onClose: () => void;
  onSave: () => void;
  saving: boolean;
  leftExtra?: ReactNode;
}) {
  const { open, group, onClose, onSave, saving } = props;
  const [idx, setIdx] = useState(0);

  const records = group?.records ?? [];
  const current = records[idx] ?? null;
  const selectedCount = props.selectedRecordIds.size;
  const totalRecords = records.length;
  const currentSelected =
    current != null && props.selectedRecordIds.has(current.record_id);

  useEffect(() => {
    if (!open) return;
    setIdx(0);
  }, [open, group?.group_id]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(0, i - 1));
      if (e.key === "ArrowRight") {
        setIdx((i) => Math.min(records.length - 1, i + 1));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, records.length, onClose]);

  if (!open || !group) return null;

  const golden = props.goldenPreview ?? group.golden_record ?? {};
  const mergedReportLine = pickScalar(
    (props.goldenPreview ?? group.golden_record)?.merged_muhatap_report_line,
  );

  const canSave = !saving && selectedCount > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex max-h-[90vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="duplicate-group-review-title"
      >
        <div className="flex items-start justify-between gap-4 border-b border-gray-100 px-6 py-4">
          <div>
            <h2
              id="duplicate-group-review-title"
              className="text-base font-semibold text-gray-900"
            >
              Duplicate grup inceleme
            </h2>
            <p className="mt-1 text-xs text-gray-500">
              Grup {group.group_id}
              <span className="mx-1.5 text-gray-300">·</span>
              {totalRecords} kayıt
              <span className="mx-1.5 text-gray-300">·</span>
              {selectedCount} seçili
            </p>
            <p className="mt-1 text-[11px] text-gray-400">
              ← / → kayıt gez, Esc kapat
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 flex-shrink-0 cursor-pointer items-center justify-center rounded-lg text-gray-400 hover:bg-gray-50"
            title="Kapat"
          >
            <i className="ri-close-line text-lg" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
          <div className="min-h-0 flex-1 overflow-y-auto border-b border-gray-100 p-5 lg:border-b-0 lg:border-r">
            <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-green-800">
              Golden record
            </div>
            <div className="rounded-xl border border-green-200 bg-green-50/80 p-4">
              <div className="text-lg font-semibold text-gray-900">
                {valueOrDash(golden.clean_name)}
              </div>
              <dl className="mt-3 space-y-2 text-sm text-gray-700">
                {GOLDEN_FIELD_ROWS.filter((row) => row.key !== "clean_name").map(
                  ({ key, label }) => (
                    <div key={key} className="flex gap-2">
                      <dt className="w-24 flex-shrink-0 text-xs font-medium text-gray-500">
                        {label}
                      </dt>
                      <dd className="min-w-0 break-words">
                        {valueOrDash(golden[key])}
                      </dd>
                    </div>
                  ),
                )}
              </dl>
              {mergedReportLine ? (
                <div className="mt-4 rounded-lg border border-green-200 bg-white/80 px-3 py-2 text-xs text-gray-700">
                  <span className="font-medium text-green-800">
                    Muhatap birleşim özeti:{" "}
                  </span>
                  {mergedReportLine}
                </div>
              ) : null}
            </div>
            {props.leftExtra ? (
              <div className="mt-4 border-t border-green-100 pt-4">{props.leftExtra}</div>
            ) : null}
          </div>

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-600">
                Grup kayıtları
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                {props.onSelectAllRecords ? (
                  <button
                    type="button"
                    onClick={props.onSelectAllRecords}
                    className="inline-flex cursor-pointer items-center rounded-lg border border-gray-200 bg-white px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Hepsini seç
                  </button>
                ) : null}
                {props.onClearAllRecords ? (
                  <button
                    type="button"
                    onClick={props.onClearAllRecords}
                    className="inline-flex cursor-pointer items-center rounded-lg border border-gray-200 bg-white px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Seçimi kaldır
                  </button>
                ) : null}
                <button
                  type="button"
                  disabled={idx <= 0}
                  onClick={() => setIdx((i) => Math.max(0, i - 1))}
                  className="inline-flex cursor-pointer items-center rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  ← Önceki
                </button>
                <span className="text-xs tabular-nums text-gray-500">
                  {totalRecords === 0 ? 0 : idx + 1} / {totalRecords}
                </span>
                <button
                  type="button"
                  disabled={idx >= totalRecords - 1}
                  onClick={() => setIdx((i) => Math.min(totalRecords - 1, i + 1))}
                  className="inline-flex cursor-pointer items-center rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Sonraki →
                </button>
              </div>
            </div>

            {current ? (
              <div className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-gray-200 bg-gray-50/50 p-4">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold text-gray-900">
                      {valueOrDash(current.clean_name)}
                    </div>
                    <p className="mt-0.5 text-xs text-gray-500">
                      Kayıt #{current.record_id}
                      {current.membership_status ? (
                        <span className="ml-2 rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium uppercase text-gray-600">
                          {current.membership_status}
                        </span>
                      ) : null}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => props.onToggleRecord(current.record_id)}
                    className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                      currentSelected
                        ? "border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700"
                        : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    <i
                      className={
                        currentSelected ? "ri-checkbox-circle-fill" : "ri-checkbox-blank-circle-line"
                      }
                    />
                    Seç
                  </button>
                </div>
                <dl className="space-y-2 text-sm text-gray-700">
                  <div className="flex gap-2">
                    <dt className="w-24 flex-shrink-0 text-xs font-medium text-gray-500">TC</dt>
                    <dd className="min-w-0 break-words">{valueOrDash(current.clean_tc)}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-24 flex-shrink-0 text-xs font-medium text-gray-500">
                      Telefon
                    </dt>
                    <dd className="min-w-0 break-words">{valueOrDash(current.clean_phone)}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-24 flex-shrink-0 text-xs font-medium text-gray-500">
                      E-posta
                    </dt>
                    <dd className="min-w-0 break-words">{valueOrDash(current.clean_email)}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-24 flex-shrink-0 text-xs font-medium text-gray-500">Şehir</dt>
                    <dd className="min-w-0 break-words">{valueOrDash(current.clean_city)}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-24 flex-shrink-0 text-xs font-medium text-gray-500">
                      Muhatap
                    </dt>
                    <dd className="min-w-0 break-words">
                      {valueOrDash(props.getRecordMuhatapNoDisplay(current))}
                    </dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-24 flex-shrink-0 text-xs font-medium text-gray-500">Adres</dt>
                    <dd className="min-w-0 break-words">{valueOrDash(current.clean_address)}</dd>
                  </div>
                </dl>
              </div>
            ) : (
              <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-gray-200 py-12 text-sm text-gray-400">
                Bu grupta kayıt yok.
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-gray-100 bg-gray-50/80 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs leading-relaxed text-gray-600">
            Seçilmeyen kayıtlar birleştirilmeyecek; bekleyen grupta kalır ve yeniden
            inceleme için kullanılabilir.
          </p>
          <button
            type="button"
            disabled={!canSave}
            onClick={onSave}
            className="inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-green-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-800 disabled:cursor-not-allowed disabled:bg-gray-300"
          >
            <i className={saving ? "ri-loader-4-line animate-spin" : "ri-save-line"} />
            Kaydet
          </button>
        </div>
      </div>
    </div>
  );
}
