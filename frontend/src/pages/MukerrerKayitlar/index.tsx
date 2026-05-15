import axios from "axios";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  downloadMuhatapMergePdf,
  getDuplicateGroups,
  listUploads,
  partialApproveGroup,
  type DuplicateGroup,
  type DuplicateGroupRecord,
  type UploadItem,
} from "../../services/api";
import { DuplicateGroupReviewModal } from "../../components/feature/DuplicateGroupReviewModal";
import { FlowNav } from "../../components/feature/FlowNav";
import { useRequireUploadId } from "../../hooks/useRequireUploadId";
import { useUploadPipelineStatus } from "../../hooks/useUploadPipelineStatus";

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
  const uploadId = useRequireUploadId();
  const { canReview, loading: pipelineLoading } = useUploadPipelineStatus(uploadId);
  const decisionParam = searchParams.get("decision");
  const navigate = useNavigate();
  const pageParam = searchParams.get("page");
  const pageSizeParam = searchParams.get("page_size");
  const page = Number(pageParam ?? "1");
  const parsedPageSize = pageSizeParam ? Number(pageSizeParam) : 50;
  const pageSize = [25, 50, 100].includes(parsedPageSize) ? parsedPageSize : 50;

  const [decisionFilter, setDecisionFilter] = useState<"pending" | "approved">(
    decisionParam === "approved" ? "approved" : "pending",
  );
  const [selectedRecordIds, setSelectedRecordIds] = useState<Set<number>>(new Set());
  const [search, setSearch] = useState("");
  const [detailGroup, setDetailGroup] = useState<DuplicateGroup | null>(null);
  const [loading, setLoading] = useState(false);
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [apiError, setApiError] = useState("");
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
  const [savingGroupFinalize, setSavingGroupFinalize] = useState(false);
  const [mergePdfBusy, setMergePdfBusy] = useState(false);
  const isMountedRef = useRef(true);

  useEffect(() => {
    if (decisionParam === "pending" || decisionParam === "approved") {
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
    setSelectedRecordIds(new Set());
  }, [detailGroup]);

  const toggleRecordSelection = (recordId: number) => {
    setSelectedRecordIds((prev) => {
      const next = new Set(prev);
      if (next.has(recordId)) next.delete(recordId);
      else next.add(recordId);
      return next;
    });
  };

  const selectAllInGroup = () => {
    if (!detailGroup) return;
    setSelectedRecordIds(new Set(detailGroup.record_ids));
  };

  const clearRecordSelection = () => setSelectedRecordIds(new Set());

  const groupsCacheRef = useRef<
    Map<string, { groups: DuplicateGroup[]; total: number; totalPages: number; ts: number }>
  >(new Map());

  const fetchGroups = useCallback(
    async (overrides?: { decision?: typeof decisionFilter; page?: number }) => {
      const d = overrides?.decision ?? decisionFilter;
      const p = overrides?.page ?? page;
      const cacheKey = `${uploadId ?? "none"}-${d}-${p}-${pageSize}`;
      const cached = groupsCacheRef.current.get(cacheKey);
      if (cached && Date.now() - cached.ts < 120_000) {
        setGroups(cached.groups);
        setTotal(cached.total);
        setTotalPages(cached.totalPages);
      }

      setLoading(true);
      setApiError("");
      try {
        const response = await getDuplicateGroups({
          decision: d,
          uploadId: uploadId ?? undefined,
          limit: 500,
          page: p,
          pageSize,
          differentMuhatapCode: true,
        });
        if (!isMountedRef.current) return;
        const nextGroups = response.groups || [];
        const nextTotal = Number(response.total ?? 0);
        const nextTotalPages = Number(response.total_pages ?? 1);
        setGroups(nextGroups);
        setTotal(nextTotal);
        setTotalPages(nextTotalPages);
        groupsCacheRef.current.set(cacheKey, {
          groups: nextGroups,
          total: nextTotal,
          totalPages: nextTotalPages,
          ts: Date.now(),
        });
      } catch (error) {
        if (!isMountedRef.current) return;
        setApiError(
          error instanceof Error ? error.message : "Duplicate group verisi alınamadı.",
        );
      } finally {
        if (isMountedRef.current) setLoading(false);
      }
    },
    [decisionFilter, uploadId, page, pageSize],
  );

  useEffect(() => {
    isMountedRef.current = true;
    if (uploadId === null || pipelineLoading || !canReview) {
      return () => {
        isMountedRef.current = false;
      };
    }
    fetchGroups();
    return () => {
      isMountedRef.current = false;
    };
  }, [fetchGroups, uploadId, canReview, pipelineLoading]);

  const goPage = (p: number) => {
    setSearchParams((prev) => {
      prev.set("page", String(p));
      return prev;
    });
  };

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
    const id = Number(raw);
    if (!Number.isFinite(id) || id <= 0) return;
    localStorage.setItem("lastDetectUploadId", String(id));
    localStorage.setItem("lastUploadId", String(id));
    setSearchParams((p) => {
      p.set("page", "1");
      p.set("upload_id", String(id));
      return p;
    });
  };

  const saveGroupGoldenFinalize = async () => {
    if (!detailGroup) return;
    const approvedRecordIds = [...selectedRecordIds];
    if (approvedRecordIds.length === 0) {
      setApiError("Kaydetmek için en az bir eşleşen kayıt seçin.");
      return;
    }
    setSavingGroupFinalize(true);
    setApiError("");
    try {
      const goldenRecordOverride = goldenFields.reduce<DuplicateGroup["golden_record"]>(
        (acc, { key }) => {
          acc[key] = goldenDraft[key];
          return acc;
        },
        {},
      );
      await partialApproveGroup({
        groupId: detailGroup.group_id,
        recordIds: detailGroup.record_ids,
        approvedRecordIds,
        rejectedRecordIds: [],
        uploadId: uploadId ?? detailGroup.records[0]?.upload_id,
        goldenRecordOverride,
      });
      setDetailGroup(null);
      setDecisionFilter("approved");
      setSearchParams((p) => {
        p.set("decision", "approved");
        p.set("page", "1");
        return p;
      });
      groupsCacheRef.current.clear();
      await fetchGroups({ decision: "approved", page: 1 });
    } catch (error) {
      setApiError(getErrorMessage(error, "Golden record ve grup kararı kaydedilemedi."));
    } finally {
      setSavingGroupFinalize(false);
    }
  };

  if (uploadId === null) {
    return (
      <DashboardLayout>
        <Header
          title="Mükerrer Kayıtlar"
          subtitle="Grupları inceleyin, seçerek birleştirin; kalan kayıtlar bekleyen grupta kalır"
        />
        <div className="flex-1 p-6 text-sm text-gray-600">
          Yükleme seçilmedi; Veri Yükleme sayfasına yönlendiriliyorsunuz…
        </div>
      </DashboardLayout>
    );
  }

  if (!pipelineLoading && !canReview) {
    return (
      <DashboardLayout>
        <Header
          title="Mükerrer Kayıtlar"
          subtitle="Önce mükerrer tespiti tamamlanmalı"
        />
        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          <FlowNav step="review" uploadId={uploadId} canGoNext={false} />
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-center">
            <i className="ri-radar-line mb-3 block text-3xl text-amber-600" />
            <p className="text-sm font-semibold text-amber-900">
              Bu dosya için henüz mükerrer tespiti yapılmamış
            </p>
            <p className="mt-2 text-xs text-amber-800">
              İnceleme ve birleştirme adımına geçmeden önce Mükerrer Tespit çalıştırın.
            </p>
            <button
              type="button"
              onClick={() => navigate(`/mukerrer-tespit?upload_id=${uploadId}`)}
              className="mt-4 inline-flex cursor-pointer items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700"
            >
              <i className="ri-play-line" />
              Mükerrer Tespit&apos;e git
            </button>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <Header
        title="Mükerrer Kayıtlar"
        subtitle="Grupları inceleyin, seçerek birleştirin; kalan kayıtlar bekleyen grupta kalır"
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
        <FlowNav step="review" uploadId={uploadId} />

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-100 bg-white p-4">
          <div className="text-sm text-gray-700">
            <span className="font-semibold text-gray-900">Birleştirme özeti</span>
            <span className="ml-2 text-xs text-gray-500">
              Bekleyen: {decisionFilter === "pending" ? total : "—"} · Onaylı kayıtlar raporda
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => navigate(`/raporlar?upload_id=${uploadId}&tab=muhatap-merge`)}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              <i className="ri-bar-chart-box-line" />
              Tam rapor
            </button>
            <button
              type="button"
              disabled={mergePdfBusy}
              onClick={async () => {
                if (uploadId === null) return;
                setMergePdfBusy(true);
                try {
                  await downloadMuhatapMergePdf({
                    uploadId,
                    decision: "approved",
                    filename: `muhatap_birlestirme_${uploadId}.pdf`,
                  });
                } catch (err) {
                  setApiError(
                    err instanceof Error ? err.message : "PDF raporu indirilemedi.",
                  );
                } finally {
                  setMergePdfBusy(false);
                }
              }}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-60"
            >
              <i className={mergePdfBusy ? "ri-loader-4-line animate-spin" : "ri-file-pdf-2-line"} />
              PDF indir
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-gray-100 bg-white p-4">
            <p className="text-xs text-gray-400">
              Toplam Grup
            </p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {total.toLocaleString("tr-TR")}
            </p>
          </div>
          <div className="rounded-xl border border-gray-100 bg-white p-4">
            <p className="text-xs text-gray-400">Sayfa</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {page} / {totalPages}
            </p>
          </div>
          <div className="rounded-xl border border-gray-100 bg-white p-4">
            <p className="text-xs text-gray-400">Önizleme</p>
            <select
              value={pageSize}
              onChange={(e) => {
                const v = e.target.value;
                setSearchParams((p) => {
                  p.set("page", "1");
                  p.set("page_size", v);
                  return p;
                });
              }}
              className="mt-2 cursor-pointer rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-100"
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">
              Yükleme Seçin
            </label>
            <select
              value={uploadId}
              onChange={(e) => selectUpload(e.target.value)}
              className="min-w-[280px] cursor-pointer rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-100"
            >
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
            onClick={() => {
              setDecisionFilter("pending");
              setSearchParams((p) => {
                p.set("page", "1");
                p.set("decision", "pending");
                return p;
              });
            }}
            className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-medium transition-colors ${filterClass(
              decisionFilter === "pending",
            )}`}
          >
            Bekliyor
          </button>
          <button
            onClick={() => {
              setDecisionFilter("approved");
              setSearchParams((p) => {
                p.set("page", "1");
                p.set("decision", "approved");
                return p;
              });
            }}
            className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-medium transition-colors ${filterClass(
              decisionFilter === "approved",
            )}`}
          >
            Onaylandı
          </button>
        </div>
        <p className="text-[11px] text-gray-500">
          Gruplar yalnızca <strong>farklı muhatap kodlu</strong> kayıtları kapsar.
        </p>

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

        <div className="flex items-center justify-between">
          <button
            disabled={page <= 1}
            onClick={() => goPage(Math.max(1, page - 1))}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 disabled:opacity-50"
          >
            Önceki
          </button>
          <button
            disabled={page >= totalPages}
            onClick={() => goPage(Math.min(totalPages, page + 1))}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 disabled:opacity-50"
          >
            Sonraki
          </button>
        </div>

        {apiError && (
          <div className="rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-700">
            {apiError}
          </div>
        )}

        <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
          <div className="border-b border-gray-50 px-5 py-4">
            <h3 className="text-sm font-semibold text-gray-900">
              Mükerrer gruplar ({decisionFilter === "pending" ? "bekliyor" : "onaylandı"})
            </h3>
          </div>
          <div className="overflow-x-auto">
            {filtered.length === 0 && !loading ? (
              <div className="py-10 text-center text-sm text-gray-400">
                Bu filtre için mükerrer grup bulunmuyor.
              </div>
            ) : (
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
                  const isApproved = decisionFilter === "approved";
                  const finalMuhatap = pickMuhatapScalar(
                    group.golden_record?.clean_muhatap_no,
                  );
                  const displayVals =
                    group.muhatap_codes && group.muhatap_codes.length > 0
                      ? group.muhatap_codes
                      : groupDistinctMuhatapValues(group, getRecordMuhatapNoDisplay);
                  const line = isApproved
                    ? finalMuhatap || "—"
                    : displayVals.join(", ");
                  const distinctNonEmpty = displayVals.length;
                  const showConflictBadge =
                    !isApproved && groupHasDistinctMuhatapConflict(group);
                  const muhatapCellClass = showConflictBadge
                    ? "bg-amber-50/80 text-gray-800"
                    : isApproved && finalMuhatap
                      ? "text-gray-800 font-medium"
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
            )}
          </div>
        </div>
      </div>

      <DuplicateGroupReviewModal
        open={Boolean(detailGroup)}
        group={detailGroup}
        goldenPreview={goldenDraft}
        selectedRecordIds={selectedRecordIds}
        onToggleRecord={toggleRecordSelection}
        onSelectAllRecords={selectAllInGroup}
        onClearAllRecords={clearRecordSelection}
        getRecordMuhatapNoDisplay={getRecordMuhatapNoDisplay}
        onClose={() => setDetailGroup(null)}
        onSave={() => void saveGroupGoldenFinalize()}
        saving={savingGroupFinalize}
        leftExtra={
          <div>
            <div className="mb-3 text-xs font-semibold text-gray-700">Golden Record düzenle</div>
            <div className="grid grid-cols-1 gap-2 text-[11px] md:grid-cols-2">
              {goldenFields.map(({ key, label }) => {
                const changed =
                  goldenDraft[key] !== (detailGroup?.golden_record[key] ?? "");
                const isEditing = editingGoldenField === key;
                return (
                  <div
                    key={key}
                    className={`rounded-lg border bg-white px-2 py-1.5 ${
                      changed ? "border-yellow-300" : "border-green-100"
                    }`}
                  >
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="font-medium text-gray-500">{label}</span>
                      <button
                        type="button"
                        onClick={() =>
                          setEditingGoldenField(isEditing ? null : key)
                        }
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
                        className={`w-full rounded-md border bg-white px-2 py-1 text-[11px] text-gray-800 focus:border-green-500 focus:outline-none ${
                          changed ? "border-yellow-300" : "border-gray-200"
                        }`}
                        autoFocus
                      />
                    ) : (
                      <div className="min-h-5 break-words text-gray-800">
                        {goldenDraft[key] || "-"}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        }
      />

    </DashboardLayout>
  );
}
