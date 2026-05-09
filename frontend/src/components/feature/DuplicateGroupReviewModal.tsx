import { useEffect, useMemo, useState } from "react";
import type { DuplicateGroup, DuplicateGroupRecord } from "../../services/api";

type RecordDecision = "confirmed" | "pending" | "excluded";

function pickScalar(v: unknown): string {
  if (v == null) return "";
  return String(v).trim();
}

function valueOrDash(v: unknown): string {
  const s = pickScalar(v);
  return s ? s : "—";
}

export function DuplicateGroupReviewModal(props: {
  open: boolean;
  group: DuplicateGroup | null;
  decisionFilter: "pending" | "approved" | "rejected";
  recordDecisions: Record<number, RecordDecision>;
  onSetRecordDecision: (recordId: number, decision: RecordDecision) => void;
  onClose: () => void;
  onSave: () => void;
  saving: boolean;
  confirmedCount: number;
  excludedCount: number;
  getRecordMuhatapNoDisplay: (record: DuplicateGroupRecord) => string;
  // Golden record edit block (optional, kept as-is from pages)
  leftExtra?: React.ReactNode;
}) {
  const { open, group } = props;
  const [idx, setIdx] = useState(0);

  const records = group?.records ?? [];
  const current = records[idx] ?? null;

  useEffect(() => {
    if (!open) return;
    setIdx(0);
  }, [open, group?.group_id]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") props.onClose();
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(0, i - 1));
      if (e.key === "ArrowRight") setIdx((i) => Math.min(records.length - 1, i + 1));
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, records.length, props]);

  const golden = group?.golden_record ?? {};

  const rightDecision: RecordDecision = useMemo(() => {
    if (!current) return "pending";
    return props.recordDecisions[current.record_id] ?? "pending";
  }, [current, props.recordDecisions]);

  if (!open || !group) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onClick={props.onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl bg-white"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <div>
            <div className="text-sm font-semibold text-gray-900">
              Duplicate Group: {group.group_id}
            </div>
            <div className="mt-1 text-xs text-gray-500">
              Golden solda sabit • Sağda kayıt: {idx + 1}/{records.length} • Oklarla gez (←/→)
            </div>
          </div>
          <button
            type="button"
            onClick={props.onClose}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-50 hover:text-gray-700"
            title="Kapat"
          >
            <i className="ri-close-line text-lg" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.15fr_1fr]">
            {/* Left: Golden record (fixed) */}
            <div className="rounded-xl border border-green-100 bg-green-50 p-4">
              <div className="mb-2 text-sm font-semibold text-green-800">
                Golden Record (sabit)
              </div>
              <div className="grid grid-cols-1 gap-2 text-xs md:grid-cols-2">
                <div>
                  <span className="text-gray-500">Ad Soyad:</span>{" "}
                  {valueOrDash(golden.clean_name)}
                </div>
                <div>
                  <span className="text-gray-500">TC:</span>{" "}
                  {valueOrDash(golden.clean_tc)}
                </div>
                <div>
                  <span className="text-gray-500">Telefon:</span>{" "}
                  {valueOrDash(golden.clean_phone)}
                </div>
                <div>
                  <span className="text-gray-500">E-posta:</span>{" "}
                  {valueOrDash(golden.clean_email)}
                </div>
                <div>
                  <span className="text-gray-500">Şehir:</span>{" "}
                  {valueOrDash(golden.clean_city)}
                </div>
                <div>
                  <span className="text-gray-500">Muhatap:</span>{" "}
                  {valueOrDash(golden.clean_muhatap_no)}
                </div>
                <div className="md:col-span-2">
                  <span className="text-gray-500">Adres:</span>{" "}
                  {valueOrDash(golden.clean_address)}
                </div>
              </div>

              {props.leftExtra ? (
                <div className="mt-4">{props.leftExtra}</div>
              ) : null}
            </div>

            {/* Right: One record at a time */}
            <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
              <div className="flex flex-wrap items-start justify-between gap-3 px-6 py-5">
                <div>
                  <div className="text-xl font-bold text-gray-900">
                    Record #{current?.record_id ?? "—"}
                  </div>
                  <div className="mt-1 text-sm text-gray-500">
                    Yükleme #{current?.upload_id ?? "—"}
                    <span className="mx-2 text-gray-300">•</span>
                    Muhatap:{" "}
                    {current
                      ? props.getRecordMuhatapNoDisplay(current) || "—"
                      : "—"}
                  </div>
                </div>

                <div className="inline-flex overflow-hidden rounded-xl border border-gray-200 bg-white">
                  {[
                    { value: "confirmed", label: "Onayla", icon: "ri-check-line" },
                    { value: "pending", label: "Beklet", icon: "ri-subtract-line" },
                    { value: "excluded", label: "Reddet", icon: "ri-close-line" },
                  ].map((option) => {
                    const active = rightDecision === option.value;
                    const activeClass =
                      option.value === "confirmed"
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                        : option.value === "excluded"
                          ? "bg-red-50 text-red-700 border-red-200"
                          : "bg-gray-900 text-white border-gray-900";
                    const idleClass = "bg-white text-gray-600 border-transparent hover:bg-gray-50";
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() =>
                          current &&
                          props.onSetRecordDecision(
                            current.record_id,
                            option.value as RecordDecision,
                          )
                        }
                        className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold transition-colors ${
                          active ? activeClass : idleClass
                        }`}
                      >
                        <i className={option.icon} />
                        {option.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="grid grid-cols-1 gap-0 border-t border-gray-100 md:grid-cols-2">
                {[
                  {
                    label: "Ad Soyad",
                    value: current?.clean_name,
                    icon: "ri-user-3-line",
                    iconBg: "bg-blue-50 text-blue-600",
                  },
                  {
                    label: "TC",
                    value: current?.clean_tc,
                    icon: "ri-id-card-line",
                    iconBg: "bg-indigo-50 text-indigo-600",
                  },
                  {
                    label: "Telefon",
                    value: current?.clean_phone,
                    icon: "ri-phone-line",
                    iconBg: "bg-emerald-50 text-emerald-600",
                  },
                  {
                    label: "E-posta",
                    value: current?.clean_email,
                    icon: "ri-mail-line",
                    iconBg: "bg-teal-50 text-teal-600",
                  },
                  {
                    label: "Şehir",
                    value: current?.clean_city,
                    icon: "ri-map-pin-line",
                    iconBg: "bg-violet-50 text-violet-600",
                  },
                  {
                    label: "Adres",
                    value: current?.clean_address,
                    icon: "ri-map-2-line",
                    iconBg: "bg-amber-50 text-amber-700",
                    full: true,
                  },
                ].map((item) => (
                  <div
                    key={item.label}
                    className={`flex items-center gap-4 px-6 py-5 ${
                      item.full ? "md:col-span-2" : ""
                    } ${item.label === "Ad Soyad" ? "" : "border-t border-gray-100 md:border-t-0"} ${
                      item.label === "TC" || item.label === "E-posta" || item.label === "Adres"
                        ? "md:border-l md:border-gray-100"
                        : ""
                    }`}
                  >
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-full ${item.iconBg}`}
                    >
                      <i className={item.icon} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-semibold text-gray-500">
                        {item.label}
                      </div>
                      <div
                        className={`mt-0.5 text-sm font-semibold text-gray-900 ${
                          item.label === "E-posta" ? "break-all" : "break-words"
                        }`}
                      >
                        {valueOrDash(item.value)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between border-t border-gray-100 px-6 py-4">
                <button
                  type="button"
                  disabled={idx <= 0}
                  onClick={() => setIdx((i) => Math.max(0, i - 1))}
                  className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2 text-sm font-semibold text-gray-700 disabled:opacity-50"
                >
                  <i className="ri-arrow-left-line" />
                  Önceki kayıt
                </button>
                <button
                  type="button"
                  disabled={idx >= records.length - 1}
                  onClick={() => setIdx((i) => Math.min(records.length - 1, i + 1))}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Sonraki kayıt
                  <i className="ri-arrow-right-line" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 bg-white px-6 py-4">
          <div className="text-sm font-medium text-gray-700">
            {props.confirmedCount} kayıt onaylandı, {props.excludedCount} kayıt reddedildi
          </div>
          <button
            type="button"
            onClick={props.onSave}
            disabled={props.saving}
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <i className={props.saving ? "ri-loader-4-line animate-spin" : "ri-save-line"} />
            Kaydet
          </button>
        </div>
      </div>
    </div>
  );
}

