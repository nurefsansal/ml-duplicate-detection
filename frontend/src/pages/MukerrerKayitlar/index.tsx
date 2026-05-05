import axios from "axios";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  getDuplicateGroups,
  listUploads,
  partialApproveGroup,
  updateGoldenRecord,
  type DuplicateGroup,
  type DuplicateGroupRecord,
  type UploadItem,
} from "../../services/api";

type RecordDecision = "confirmed" | "pending" | "excluded";
type GoldenField =
  | "clean_name"
  | "clean_tc"
  | "clean_phone"
  | "clean_email"
  | "clean_city"
  | "clean_address"
  | "clean_muhatap_no";

const goldenFields: Array<{ key: GoldenField; label: string }> = [
  { key: "clean_name", label: "Ad Soyad" },
  { key: "clean_tc", label: "TC" },
  { key: "clean_phone", label: "Telefon" },
  { key: "clean_email", label: "E-posta" },
  { key: "clean_city", label: "Şehir" },
  { key: "clean_address", label: "Adres" },
  { key: "clean_muhatap_no", label: "Muhatap Kodu" },
];

function pct(value: number): string {
  return `%${(Number(value || 0) * 100).toFixed(1)}`;
}

function filterClass(active: boolean): string {
  return active
    ? "bg-red-600 text-white"
    : "border border-gray-200 text-gray-600 hover:bg-gray-50";
}

function muhatapConflictFilterClass(active: boolean): string {
  return active
    ? "bg-purple-600 text-white shadow-sm"
    : "border border-gray-200 text-gray-600 hover:bg-gray-50";
}

function pickMuhatapScalar(v: unknown): string {
  if (v == null) return "";
  return String(v).trim();
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail ?? error.response?.data?.error;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return error instanceof Error ? error.message : fallback;
}

/** Çakışma filtresi: backend'in group.muhatap_codes alanıyla aynı önceliği izler. */
function getRecordMuhatapNoForConflict(record: DuplicateGroupRecord): string {
  const clean = pickMuhatapScalar(record.clean_muhatap_no);
  const normalizedClean = pickMuhatapScalar(record.normalized_payload?.clean_muhatap_no);
  const normalizedSnake = pickMuhatapScalar(record.normalized_payload?.muhatap_no);
  const normalizedTitle = pickMuhatapScalar(record.normalized_payload?.["Muhatap No"]);
  return clean || normalizedClean || normalizedSnake || normalizedTitle;
}

/** Tablo ve detay gösterimi: üstteki kaynaklar + raw payload yedeği. */
function getRecordMuhatapNoDisplay(record: DuplicateGroupRecord): string {
  const fromPayload = getRecordMuhatapNoForConflict(record);
  if (fromPayload) return fromPayload;
  return pickMuhatapScalar(record.raw_payload?.muhatap_no);
}

function formatUploadDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("tr-TR", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function groupDistinctMuhatapValues(
  group: DuplicateGroup,
  getter: (r: DuplicateGroupRecord) => string,
): string[] {
  const set = new Set<string>();
  for (const r of group.records) {
    const m = getter(r);
    if (m) set.add(m);
  }
  return [...set].sort();
}

function groupHasDistinctMuhatapConflict(group: DuplicateGroup): boolean {
  if (typeof group.different_muhatap_code === "boolean") {
    return group.different_muhatap_code;
  }
  if (group.muhatap_codes && group.muhatap_codes.length > 0) {
    return group.muhatap_codes.length > 1;
  }
  return groupDistinctMuhatapValues(group, getRecordMuhatapNoForConflict).length > 1;
}

export default function MukerrerKayitlar() {
  const [searchParams, setSearchParams] = useSearchParams();
  const uploadIdParam = searchParams.get("upload_id");
  const decisionParam = searchParams.get("decision");

  const [decisionFilter, setDecisionFilter] = useState<
    "pending" | "approved" | "rejected"
  >(
    decisionParam === "pending" || decisionParam === "rejected" || decisionParam === "approved"
      ? decisionParam
      : "approved",
  );
  const [search, setSearch] = useState("");
  const [filterMuhatapConflict, setFilterMuhatapConflict] = useState(false);
  const [detailGroup, setDetailGroup] = useState<DuplicateGroup | null>(null);
  const [loading, setLoading] = useState(false);
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [apiError, setApiError] = useState("");
  const [recordDecisions, setRecordDecisions] = useState<Record<number, RecordDecision>>({});
  const [goldenDraft, setGoldenDraft] = useState<Record<GoldenField, string>>({
    clean_name: "",
    clean_tc: "",
    clean_phone: "",
    clean_email: "",
    clean_city: "",
    clean_address: "",
    clean_muhatap_no: "",
  });
  const [editingGoldenField, setEditingGoldenField] = useState<GoldenField | null>(null);
  const [savingPartial, setSavingPartial] = useState(false);
  const [savingGolden, setSavingGolden] = useState(false);
  const isMountedRef = useRef(true);

  const [selectedUploadId, setSelectedUploadId] = useState<number | undefined>(
    () => {
      if (uploadIdParam && !Number.isNaN(Number(uploadIdParam))) {
        return Number(uploadIdParam);
      }
      const ls = localStorage.getItem("lastDetectUploadId");
      if (ls && !Number.isNaN(Number(ls))) return Number(ls);
      return undefined;
    },
  );

  useEffect(() => {
    if (uploadIdParam && !Number.isNaN(Number(uploadIdParam))) {
      setSelectedUploadId(Number(uploadIdParam));
    }
  }, [uploadIdParam]);

  useEffect(() => {
    if (decisionParam === "pending" || decisionParam === "approved" || decisionParam === "rejected") {
      setDecisionFilter(decisionParam);
    }
  }, [decisionParam]);

  useEffect(() => {
    listUploads(100)
      .then((d) => setUploads(d.uploads ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!detailGroup) return;

    const nextDecisions: Record<number, RecordDecision> = {};
    for (const record of detailGroup.records) {
      nextDecisions[record.record_id] = record.membership_status ?? "pending";
    }
    setRecordDecisions(nextDecisions);
    setGoldenDraft({
      clean_name: detailGroup.golden_record.clean_name ?? "",
      clean_tc: detailGroup.golden_record.clean_tc ?? "",
      clean_phone: detailGroup.golden_record.clean_phone ?? "",
      clean_email: detailGroup.golden_record.clean_email ?? "",
      clean_city: detailGroup.golden_record.clean_city ?? "",
      clean_address: detailGroup.golden_record.clean_address ?? "",
      clean_muhatap_no: detailGroup.golden_record.clean_muhatap_no ?? "",
    });
    setEditingGoldenField(null);
  }, [detailGroup]);

  const fetchGroups = useCallback(async () => {
    setLoading(true);
    setApiError("");
    try {
      const response = await getDuplicateGroups({
        decision: decisionFilter,
        uploadId: selectedUploadId,
        limit: 5000,
        differentMuhatapCode: filterMuhatapConflict,
      });
      if (!isMountedRef.current) return;
      setGroups(response.groups || []);
    } catch (error) {
      if (!isMountedRef.current) return;
      setApiError(
        error instanceof Error ? error.message : "Duplicate group verisi alınamadı.",
      );
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [decisionFilter, filterMuhatapConflict, selectedUploadId]);

  useEffect(() => {
    isMountedRef.current = true;
    fetchGroups();
    return () => {
      isMountedRef.current = false;
    };
  }, [fetchGroups]);

  const filtered = useMemo(() => {
    let list = groups;
    if (search) {
      const text = search.toLowerCase();
      list = list.filter((group) => {
        if (group.group_id.toLowerCase().includes(text)) return true;
        return group.records.some(
          (record) =>
            record.clean_name.toLowerCase().includes(text) ||
            record.clean_tc.includes(search) ||
            record.clean_phone.includes(search) ||
            record.clean_email.toLowerCase().includes(text),
        );
      });
    }
    return list;
  }, [groups, search]);

  const selectUpload = (raw: string) => {
    if (raw === "") {
      setSelectedUploadId(undefined);
      localStorage.removeItem("lastDetectUploadId");
      setSearchParams((p) => {
        p.delete("upload_id");
        return p;
      });
      return;
    }
    const id = Number(raw);
    if (Number.isNaN(id)) return;
    setSelectedUploadId(id);
    localStorage.setItem("lastDetectUploadId", String(id));
    setSearchParams((p) => {
      p.set("upload_id", String(id));
      return p;
    });
  };

  const confirmedCount = useMemo(
    () => Object.values(recordDecisions).filter((decision) => decision === "confirmed").length,
    [recordDecisions],
  );

  const excludedCount = useMemo(
    () => Object.values(recordDecisions).filter((decision) => decision === "excluded").length,
    [recordDecisions],
  );

  const entityIdForDetail = useMemo(() => {
    if (!detailGroup) return null;
    return (
      detailGroup.entity_id ??
      detailGroup.records.find((record) => record.entity_id != null)?.entity_id ??
      null
    );
  }, [detailGroup]);

  const changedGoldenFields = useMemo(() => {
    if (!detailGroup) return [];
    return goldenFields
      .filter(({ key }) => goldenDraft[key] !== (detailGroup.golden_record[key] ?? ""))
      .map(({ key }) => key);
  }, [detailGroup, goldenDraft]);

  const setRecordDecision = (recordId: number, decision: RecordDecision) => {
    setRecordDecisions((prev) => ({ ...prev, [recordId]: decision }));
  };

  const savePartialDecisions = async () => {
    if (!detailGroup) return;
    setSavingPartial(true);
    setApiError("");
    try {
      const approvedRecordIds = Object.entries(recordDecisions)
        .filter(([, decision]) => decision === "confirmed")
        .map(([recordId]) => Number(recordId));
      const rejectedRecordIds = Object.entries(recordDecisions)
        .filter(([, decision]) => decision === "excluded")
        .map(([recordId]) => Number(recordId));

      await partialApproveGroup({
        groupId: detailGroup.group_id,
        recordIds: detailGroup.record_ids,
        approvedRecordIds,
        rejectedRecordIds,
        uploadId: selectedUploadId ?? detailGroup.records[0]?.upload_id,
        decision: decisionFilter,
      });
      setDetailGroup(null);
      await fetchGroups();
    } catch (error) {
      setApiError(getErrorMessage(error, "Kısmi onay kaydedilemedi."));
    } finally {
      setSavingPartial(false);
    }
  };

  const saveGoldenRecord = async () => {
    if (!entityIdForDetail || changedGoldenFields.length === 0) return;
    setSavingGolden(true);
    setApiError("");
    try {
      const fields = changedGoldenFields.reduce<DuplicateGroup["golden_record"]>(
        (acc, key) => {
          acc[key] = goldenDraft[key];
          return acc;
        },
        {},
      );
      await updateGoldenRecord({ entityId: entityIdForDetail, fields });
      setDetailGroup((prev) =>
        prev
          ? {
              ...prev,
              golden_record: {
                ...prev.golden_record,
                ...fields,
              },
            }
          : prev,
      );
      await fetchGroups();
    } catch (error) {
      setApiError(
        error instanceof Error ? error.message : "Golden record güncellenemedi.",
      );
    } finally {
      setSavingGolden(false);
    }
  };

  return (
    <DashboardLayout>
      <Header
        title="Mükerrer Kayıtlar"
        subtitle="Pair yerine duplicate group ve golden record görünümü"
        actions={
          <button
            onClick={() => fetchGroups()}
            disabled={loading}
            className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-60"
          >
            <i className={loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"} />
            Yenile
          </button>
        }
      />

      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">
              Yükleme Seçin
            </label>
            <select
              value={selectedUploadId ?? ""}
              onChange={(e) => selectUpload(e.target.value)}
              className="min-w-[280px] cursor-pointer rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-100"
            >
              <option value="">Tüm yüklemeler</option>
              {uploads.map((u) => (
                <option key={u.id} value={u.id}>
                  #{u.id} — {u.file_name} ({u.total_records} kayıt,{" "}
                  {formatUploadDate(u.created_at)})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setDecisionFilter("pending")}
            className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-medium transition-colors ${filterClass(
              decisionFilter === "pending",
            )}`}
          >
            Bekliyor
          </button>
          <button
            onClick={() => setDecisionFilter("approved")}
            className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-medium transition-colors ${filterClass(
              decisionFilter === "approved",
            )}`}
          >
            Onaylandı
          </button>
          <button
            onClick={() => setDecisionFilter("rejected")}
            className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-medium transition-colors ${filterClass(
              decisionFilter === "rejected",
            )}`}
          >
            Reddedildi
          </button>
          <button
            type="button"
            onClick={() => setFilterMuhatapConflict((prev) => !prev)}
            className={`flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${muhatapConflictFilterClass(
              filterMuhatapConflict,
            )}`}
          >
            <i className="ri-git-branch-line" />
            Farklı Muhatap Kodlu
          </button>
        </div>

        <div className="relative w-full">
          <i className="ri-search-line absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Group ID, ad, tc, telefon, email ara..."
            className="w-full rounded-lg border border-gray-200 py-2.5 pl-9 pr-4 text-sm focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-100"
          />
        </div>

        {apiError && (
          <div className="rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-700">
            {apiError}
          </div>
        )}

        <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
          <div className="border-b border-gray-50 px-5 py-4">
            <h3 className="text-sm font-semibold text-gray-900">
              Duplicate Groups ({decisionFilter})
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1040px] text-xs">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/70">
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Group ID</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Kayıt Sayısı</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Eşleşme</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Skor</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Golden Record</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Muhatap Kodları</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-400">İşlem</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((group) => {
                  const displayVals =
                    group.muhatap_codes && group.muhatap_codes.length > 0
                      ? group.muhatap_codes
                      : groupDistinctMuhatapValues(group, getRecordMuhatapNoDisplay);
                  const line = displayVals.join(", ");
                  const distinctNonEmpty = displayVals.length;
                  const showConflictBadge = groupHasDistinctMuhatapConflict(group);
                  const muhatapCellClass = filterMuhatapConflict
                    ? "bg-amber-100/90 text-gray-800"
                    : "";

                  return (
                    <tr key={group.group_id} className="transition-colors hover:bg-gray-50/50">
                      <td className="px-4 py-3.5 font-medium text-gray-800">{group.group_id}</td>
                      <td className="px-4 py-3.5 text-gray-600">{group.record_ids.length}</td>
                      <td className="px-4 py-3.5 text-gray-600">{group.match_count}</td>
                      <td className="px-4 py-3.5 text-gray-600">{pct(group.group_score)}</td>
                      <td className="px-4 py-3.5 text-gray-700">
                        {group.golden_record.clean_name || "-"}
                      </td>
                      <td className={`px-4 py-3.5 ${muhatapCellClass}`}>
                        <div className="flex flex-wrap items-center gap-2">
                          {showConflictBadge && (
                            <span className="inline-flex items-center rounded-md bg-amber-200 px-2 py-0.5 text-[11px] font-semibold text-amber-900">
                              ⚠ {distinctNonEmpty} farklı
                            </span>
                          )}
                          <span
                            className={
                              showConflictBadge
                                ? "text-gray-700"
                                : "text-gray-400"
                            }
                          >
                            {line || "—"}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-center">
                        <button
                          onClick={() => setDetailGroup(group)}
                          className="cursor-pointer text-xs font-medium text-red-600 hover:underline"
                        >
                          Detay
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filtered.length === 0 && !loading && (
              <div className="py-10 text-center text-sm text-gray-400">
                Bu filtre için duplicate group bulunmuyor.
              </div>
            )}
          </div>
        </div>
      </div>

      {detailGroup && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
          onClick={() => setDetailGroup(null)}
        >
          <div
            className="flex max-h-[85vh] w-full max-w-5xl flex-col rounded-2xl bg-white"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
              <div>
                <h2 className="text-base font-bold text-gray-900">
                  Duplicate Group: {detailGroup.group_id}
                </h2>
                <p className="mt-0.5 text-xs text-gray-400">
                  Bu gruba ait tum kayitlar ve golden record
                </p>
              </div>
              <button
                onClick={() => setDetailGroup(null)}
                className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg hover:bg-gray-100"
              >
                <i className="ri-close-line text-lg text-gray-500" />
              </button>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto p-6">
              <div className="rounded-xl border border-green-100 bg-green-50 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-green-800">Golden Record</h3>
                  <button
                    type="button"
                    onClick={saveGoldenRecord}
                    disabled={
                      savingGolden ||
                      changedGoldenFields.length === 0 ||
                      !entityIdForDetail
                    }
                    className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-green-700 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-green-800 disabled:cursor-not-allowed disabled:bg-gray-300"
                  >
                    <i className={savingGolden ? "ri-loader-4-line animate-spin" : "ri-save-line"} />
                    Golden Record'u Güncelle
                  </button>
                </div>
                <div className="grid grid-cols-1 gap-3 text-xs md:grid-cols-2">
                  {goldenFields.map(({ key, label }) => {
                    const changed =
                      goldenDraft[key] !== (detailGroup.golden_record[key] ?? "");
                    const isEditing = editingGoldenField === key;
                    return (
                      <div
                        key={key}
                        className={`rounded-lg border bg-white px-3 py-2 ${
                          changed ? "border-yellow-300" : "border-green-100"
                        }`}
                      >
                        <div className="mb-1 flex items-center justify-between gap-2">
                          <span className="font-medium text-gray-500">{label}</span>
                          <button
                            type="button"
                            onClick={() => setEditingGoldenField(isEditing ? null : key)}
                            className="flex h-6 w-6 cursor-pointer items-center justify-center rounded-md text-green-700 hover:bg-green-50"
                            title={`${label} düzenle`}
                          >
                            <i className="ri-pencil-line" />
                          </button>
                        </div>
                        {isEditing ? (
                          <input
                            value={goldenDraft[key]}
                            onChange={(event) =>
                              setGoldenDraft((prev) => ({
                                ...prev,
                                [key]: event.target.value,
                              }))
                            }
                            className={`w-full rounded-md border bg-white px-2 py-1 text-xs text-gray-800 focus:border-green-500 focus:outline-none ${
                              changed ? "border-yellow-300" : "border-gray-200"
                            }`}
                            autoFocus
                          />
                        ) : (
                          <div className="min-h-6 break-words text-gray-800">
                            {goldenDraft[key] || "-"}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
                <div className="hidden">
                  <div>
                    <span className="text-gray-500">Ad Soyad:</span>{" "}
                    {detailGroup.golden_record.clean_name || "-"}
                  </div>
                  <div>
                    <span className="text-gray-500">TC:</span>{" "}
                    {detailGroup.golden_record.clean_tc || "-"}
                  </div>
                  <div>
                    <span className="text-gray-500">Telefon:</span>{" "}
                    {detailGroup.golden_record.clean_phone || "-"}
                  </div>
                  <div>
                    <span className="text-gray-500">E-posta:</span>{" "}
                    {detailGroup.golden_record.clean_email || "-"}
                  </div>
                  <div>
                    <span className="text-gray-500">Şehir:</span>{" "}
                    {detailGroup.golden_record.clean_city || "-"}
                  </div>
                  <div>
                    <span className="text-gray-500">Adres:</span>{" "}
                    {detailGroup.golden_record.clean_address || "-"}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {detailGroup.records.map((record) => (
                  <div key={record.record_id} className="rounded-xl border border-gray-200 p-4">
                    <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <span className="mb-1 inline-flex rounded-md bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">
                          Yükleme #{record.upload_id}
                        </span>
                        <div className="text-xs font-semibold text-gray-700">
                          Record #{record.record_id}
                        </div>
                      </div>
                      <div className="inline-flex overflow-hidden rounded-lg border border-gray-200 bg-white text-[11px]">
                        {[
                          { value: "confirmed", label: "✓ Onayla" },
                          { value: "pending", label: "— Beklet" },
                          { value: "excluded", label: "✗ Reddet" },
                        ].map((option) => {
                          const active = recordDecisions[record.record_id] === option.value;
                          return (
                            <button
                              key={option.value}
                              type="button"
                              onClick={() =>
                                setRecordDecision(record.record_id, option.value as RecordDecision)
                              }
                              className={`cursor-pointer px-2.5 py-1 font-medium transition-colors ${
                                active
                                  ? option.value === "confirmed"
                                    ? "bg-green-600 text-white"
                                    : option.value === "excluded"
                                      ? "bg-red-600 text-white"
                                      : "bg-gray-700 text-white"
                                  : "text-gray-500 hover:bg-gray-50"
                              }`}
                            >
                              {option.label}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                    <div className="space-y-1 text-xs text-gray-700">
                      <div>
                        <span className="text-gray-500">Yükleme:</span> #{record.upload_id}
                      </div>
                      <div>
                        <span className="text-gray-500">Muhatap kodu:</span>{" "}
                        {getRecordMuhatapNoDisplay(record) || "—"}
                      </div>
                      <div>
                        <span className="text-gray-500">Ad Soyad:</span> {record.clean_name || "-"}
                      </div>
                      <div>
                        <span className="text-gray-500">TC:</span> {record.clean_tc || "-"}
                      </div>
                      <div>
                        <span className="text-gray-500">Telefon:</span> {record.clean_phone || "-"}
                      </div>
                      <div>
                        <span className="text-gray-500">E-posta:</span> {record.clean_email || "-"}
                      </div>
                      <div>
                        <span className="text-gray-500">Şehir:</span> {record.clean_city || "-"}
                      </div>
                      <div>
                        <span className="text-gray-500">Adres:</span> {record.clean_address || "-"}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 bg-white px-6 py-4">
              <div className="text-sm font-medium text-gray-700">
                {confirmedCount} kayıt onaylandı, {excludedCount} kayıt reddedildi
              </div>
              <button
                type="button"
                onClick={savePartialDecisions}
                disabled={savingPartial}
                className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <i className={savingPartial ? "ri-loader-4-line animate-spin" : "ri-save-line"} />
                Kaydet
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
