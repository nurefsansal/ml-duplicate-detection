import axios from "axios";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  downloadMlGroundTruthCsv,
  getDuplicateGroups,
  getMatches,
  listUploads,
  partialApproveGroup,
  resetMatchDecision,
  updateGoldenRecord,
  type DuplicateGroup,
  type DuplicateGroupRecord,
  type AdminPendingMatch,
  type UploadItem,
} from "../../services/api";
import { MatchReviewModal } from "../../components/feature/MatchReviewModal";
import { DuplicateGroupReviewModal } from "../../components/feature/DuplicateGroupReviewModal";
import { FlowNav } from "../../components/feature/FlowNav";
import { useRequireUploadId } from "../../hooks/useRequireUploadId";

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
    ? "bg-gradient-to-r from-primary-600 to-primary-700 text-white shadow-sm"
    : "border border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50";
}

function muhatapConflictFilterClass(active: boolean): string {
  return active
    ? "bg-gradient-to-r from-violet-600 to-indigo-700 text-white shadow-sm"
    : "border border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50";
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

export default function YoneticiOnayi() {
  const [searchParams, setSearchParams] = useSearchParams();
  const uploadId = useRequireUploadId();
  const decisionParam = searchParams.get("decision");
  const viewParam = searchParams.get("view");
  const pageParam = searchParams.get("page");
  const pageSizeParam = searchParams.get("page_size");
  const page = Number(pageParam ?? "1");
  const parsedPageSize = pageSizeParam ? Number(pageSizeParam) : 50;
  const pageSize = [25, 50, 100].includes(parsedPageSize) ? parsedPageSize : 50;
  const viewMode: "groups" | "candidates" =
    viewParam === "candidates" ? "candidates" : "groups";

  const [decisionFilter, setDecisionFilter] = useState<
    "pending" | "approved" | "rejected"
  >(
    decisionParam === "pending" || decisionParam === "rejected" || decisionParam === "approved"
      ? decisionParam
      : "pending",
  );
  const [search, setSearch] = useState("");
  const [groundTruthBusy, setGroundTruthBusy] = useState(false);
  const [filterMuhatapConflict, setFilterMuhatapConflict] = useState(false);
  const [detailGroup, setDetailGroup] = useState<DuplicateGroup | null>(null);
  const [loading, setLoading] = useState(false);
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [matches, setMatches] = useState<AdminPendingMatch[]>([]);
  const [matchesTotal, setMatchesTotal] = useState(0);
  const [matchesTotalPages, setMatchesTotalPages] = useState(1);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewIndex, setReviewIndex] = useState(0);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
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
  const [resettingMatchId, setResettingMatchId] = useState<number | null>(null);
  const isMountedRef = useRef(true);

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
        uploadId: uploadId ?? undefined,
        limit: 5000,
        page,
        pageSize,
        differentMuhatapCode: filterMuhatapConflict,
      });
      if (!isMountedRef.current) return;
      setGroups(response.groups || []);
      setTotal(Number(response.total ?? 0));
      setTotalPages(Number(response.total_pages ?? 1));
    } catch (error) {
      if (!isMountedRef.current) return;
      setApiError(
        error instanceof Error ? error.message : "Duplicate group verisi alınamadı.",
      );
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [decisionFilter, filterMuhatapConflict, uploadId, page, pageSize]);

  const fetchMatches = useCallback(async () => {
    setLoading(true);
    setApiError("");
    try {
      const response = await getMatches({
        decision: decisionFilter,
        uploadId: uploadId ?? undefined,
        limit: pageSize,
        page,
        pageSize,
      });
      if (!isMountedRef.current) return;
      setMatches(response.matches || []);
      setMatchesTotal(Number(response.total ?? 0));
      setMatchesTotalPages(Number(response.total_pages ?? 1));
    } catch (error) {
      if (!isMountedRef.current) return;
      setApiError(
        error instanceof Error ? error.message : "Aday eşleşmeler alınamadı.",
      );
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [decisionFilter, uploadId, page, pageSize]);

  useEffect(() => {
    isMountedRef.current = true;
    if (uploadId === null) {
      return () => {
        isMountedRef.current = false;
      };
    }
    if (viewMode === "candidates") fetchMatches();
    else fetchGroups();
    return () => {
      isMountedRef.current = false;
    };
  }, [fetchGroups, fetchMatches, viewMode, uploadId]);

  const goPage = (p: number) => {
    setSearchParams((prev) => {
      prev.set("page", String(p));
      return prev;
    });
  };

  const setViewMode = (mode: "groups" | "candidates") => {
    setSearchParams((prev) => {
      prev.set("page", "1");
      prev.set("view", mode);
      return prev;
    });
  };

  const openReviewAt = (idx: number) => {
    setReviewError(null);
    setReviewIndex(Math.max(0, Math.min(matches.length - 1, idx)));
    setReviewOpen(true);
  };

  const closeReview = () => setReviewOpen(false);

  const reviewPrev = () => {
    setReviewIndex((i) => Math.max(0, i - 1));
  };

  const reviewNext = () => {
    setReviewIndex((i) => Math.min(matches.length - 1, i + 1));
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
        uploadId: uploadId ?? detailGroup.records[0]?.upload_id,
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

  const handleResetMatch = async (matchId: number) => {
    setResettingMatchId(matchId);
    setApiError("");
    try {
      await resetMatchDecision({
        matchId,
        reason: "Yönetici kararı geri alındı",
      });
      setDetailGroup(null);
      await fetchGroups();
    } catch (error) {
      setApiError(getErrorMessage(error, "Karar geri alınamadı."));
    } finally {
      setResettingMatchId(null);
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

  if (uploadId === null) {
    return (
      <DashboardLayout>
        <Header
          title="Yönetici Onayı"
          subtitle="Grup bazlı inceleme: kayıtları onaylayın veya hariç tutun; golden record düzenleyin"
        />
        <div className="flex-1 p-6 text-sm text-gray-600">
          Yükleme seçilmedi; Veri Yükleme sayfasına yönlendiriliyorsunuz…
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <Header
        title="Yönetici Onayı"
        subtitle="Grup bazlı inceleme: kayıtları onaylayın veya hariç tutun; golden record düzenleyin"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={async () => {
                setGroundTruthBusy(true);
                setApiError("");
                try {
                  await downloadMlGroundTruthCsv();
                } catch (error) {
                  setApiError(getErrorMessage(error, "Ground truth CSV indirilemedi."));
                } finally {
                  setGroundTruthBusy(false);
                }
              }}
              disabled={groundTruthBusy}
              title="Onaylanan ve reddedilen eşleşmeler + ML eğitimiyle aynı 6 özellik"
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-60"
            >
              <i
                className={
                  groundTruthBusy ? "ri-loader-4-line animate-spin" : "ri-download-2-line"
                }
              />
              Ground truth CSV
            </button>
            <button
              onClick={() => fetchGroups()}
              disabled={loading}
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-60"
            >
              <i className={loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"} />
              Yenile
            </button>
          </div>
        }
      />

      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        <FlowNav step="detect" uploadId={uploadId} />

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-gray-100 bg-white p-4">
            <p className="text-xs text-gray-400">
              {viewMode === "candidates" ? "Toplam Aday" : "Toplam Grup"}
            </p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {(viewMode === "candidates" ? matchesTotal : total).toLocaleString(
                "tr-TR",
              )}
            </p>
          </div>
          <div className="rounded-xl border border-gray-100 bg-white p-4">
            <p className="text-xs text-gray-400">Sayfa</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {page} / {viewMode === "candidates" ? matchesTotalPages : totalPages}
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
              className="ui-focus-ring mt-2 cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
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
              className="ui-focus-ring min-w-[280px] cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              {uploads.map((u) => (
                <option key={u.id} value={u.id}>
                  #{u.id} — {u.file_name} ({u.total_records} kayıt,{" "}
                  {formatUploadDate(u.created_at)})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">
              Görünüm
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setViewMode("groups")}
                className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                  viewMode === "groups"
                    ? "bg-gradient-to-r from-primary-600 to-primary-700 text-white shadow-sm"
                    : "border border-gray-200 text-gray-600 hover:bg-gray-50"
                }`}
              >
                Gruplar
              </button>
              <button
                type="button"
                onClick={() => setViewMode("candidates")}
                className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                  viewMode === "candidates"
                    ? "bg-gradient-to-r from-primary-600 to-primary-700 text-white shadow-sm"
                    : "border border-gray-200 text-gray-600 hover:bg-gray-50"
                }`}
              >
                Aday Eşleşmeler
              </button>
            </div>
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
          <button
            onClick={() => {
              setDecisionFilter("rejected");
              setSearchParams((p) => {
                p.set("page", "1");
                p.set("decision", "rejected");
                return p;
              });
            }}
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
            className="ui-focus-ring w-full rounded-lg border border-slate-200 py-2.5 pl-9 pr-4 text-sm"
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
            disabled={
              page >= (viewMode === "candidates" ? matchesTotalPages : totalPages)
            }
            onClick={() =>
              goPage(
                Math.min(
                  viewMode === "candidates" ? matchesTotalPages : totalPages,
                  page + 1,
                ),
              )
            }
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 disabled:opacity-50"
          >
            Sonraki
          </button>
        </div>

        {apiError && (
          <div className="rounded-2xl border border-danger-200 bg-danger-50 p-4 text-sm font-medium text-danger-700 shadow-sm">
            {apiError}
          </div>
        )}

        <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
          <div className="border-b border-gray-50 px-5 py-4">
            <h3 className="text-sm font-semibold text-gray-900">
              {viewMode === "candidates"
                ? `Aday eşleşmeler — ${
                    decisionFilter === "pending"
                      ? "bekleyen"
                      : decisionFilter === "approved"
                        ? "onaylanan"
                        : "reddedilen"
                  }`
                : `Duplicate gruplar — ${
                    decisionFilter === "pending"
                      ? "bekleyen"
                      : decisionFilter === "approved"
                        ? "onaylanan"
                        : "reddedilen"
                  }`}
            </h3>
            <p className="mt-1 text-xs text-gray-400">
              {viewMode === "candidates"
                ? "Bu görünüm büyük veride daha ölçekli: aday eşleşmeler sayfa sayfa yüklenir."
                : "Çift bazlı eski akış kaldırıldı; tüm kararlar grup üzerinden verilir."}
            </p>
          </div>
          <div className="overflow-x-auto">
            {viewMode === "candidates" ? (
              <table className="w-full min-w-[1040px] text-xs">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50/70">
                    <th className="px-4 py-3 text-left font-medium text-gray-400">
                      ID
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">
                      Skor
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">
                      Sol
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">
                      Sağ
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">
                      Kaynak
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {matches.map((m, idx) => (
                    <tr
                      key={m.id}
                      className="transition-colors hover:bg-gray-50/50"
                    >
                      <td className="px-4 py-3.5 font-medium text-gray-800">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => openReviewAt(idx)}
                            className="cursor-pointer text-xs font-semibold text-primary-700 hover:text-primary-600 hover:underline"
                            title="Bu adayı incele"
                          >
                            İncele
                          </button>
                          <span>#{m.id}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-gray-600">
                        {typeof m.final_score === "number"
                          ? `${m.final_score.toFixed(1)}%`
                          : pct(m.ml_score)}
                      </td>
                      <td className="px-4 py-3.5 text-gray-700">
                        <div className="font-medium text-gray-800">
                          {m.donor1_name}
                        </div>
                        <div className="text-gray-500">
                          {m.donor1_tc ||
                            m.donor1_phone ||
                            m.donor1_email ||
                            "—"}
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-gray-700">
                        <div className="font-medium text-gray-800">
                          {m.donor2_name}
                        </div>
                        <div className="text-gray-500">
                          {m.donor2_tc ||
                            m.donor2_phone ||
                            m.donor2_email ||
                            "—"}
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-gray-500">
                        {m.decisionSource || m.match_type || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
                          className="cursor-pointer text-xs font-medium text-primary-700 hover:text-primary-600 hover:underline"
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
            {viewMode === "candidates" ? (
              matches.length === 0 &&
              !loading && (
                <div className="py-10 text-center text-sm text-gray-400">
                  Bu filtre için aday eşleşme bulunmuyor.
                </div>
              )
            ) : (
              filtered.length === 0 &&
              !loading && (
                <div className="py-10 text-center text-sm text-gray-400">
                  Bu filtre için duplicate group bulunmuyor.
                </div>
              )
            )}
          </div>
        </div>
      </div>

      <DuplicateGroupReviewModal
        open={viewMode !== "candidates" && Boolean(detailGroup)}
        group={detailGroup}
        decisionFilter={decisionFilter}
        recordDecisions={recordDecisions}
        onSetRecordDecision={setRecordDecision}
        onClose={() => setDetailGroup(null)}
        onSave={savePartialDecisions}
        saving={savingPartial}
        confirmedCount={confirmedCount}
        excludedCount={excludedCount}
        getRecordMuhatapNoDisplay={getRecordMuhatapNoDisplay}
        leftExtra={
          <div>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-xs font-semibold text-gray-700">
                Golden Record düzenle
              </div>
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
                <i
                  className={
                    savingGolden
                      ? "ri-loader-4-line animate-spin"
                      : "ri-save-line"
                  }
                />
                Güncelle
              </button>
            </div>
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

      <MatchReviewModal
        open={viewMode === "candidates" && reviewOpen}
        match={viewMode === "candidates" ? matches[reviewIndex] ?? null : null}
        index={reviewIndex}
        total={matches.length}
        canReset={decisionFilter !== "pending"}
        busy={reviewBusy}
        error={reviewError}
        onClose={closeReview}
        onPrev={reviewPrev}
        onNext={reviewNext}
        onBusyChange={setReviewBusy}
        onError={setReviewError}
        onAfterAction={() => {
          void fetchMatches();
        }}
      />
    </DashboardLayout>
  );
}
