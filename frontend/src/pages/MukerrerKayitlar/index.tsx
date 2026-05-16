import axios from "axios";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  downloadMuhatapMergePdf,
  getDuplicateGroups,
  getSettings,
  isMuhatapConflictDetail,
  listUploads,
  mergePendingIntoEntity,
  partialApproveGroup,
  removeMergeMember,
  updateGoldenRecord,
  type DuplicateGroup,
  type DuplicateGroupRecord,
  type MuhatapConflictDetail,
  type UploadItem,
} from "../../services/api";
import { DuplicateGroupReviewModal } from "../../components/feature/DuplicateGroupReviewModal";
import { FlowNav } from "../../components/feature/FlowNav";
import { useRequireUploadId } from "../../hooks/useRequireUploadId";
import { useUploadPipelineStatus } from "../../hooks/useUploadPipelineStatus";
import { formatUploadOptionLabel } from "../../utils/formatUploadDate";

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
    if (detail && typeof detail === "object" && "code" in detail) {
      const c = (detail as { code?: string }).code;
      if (c === "MUHATAP_CONFLICT") {
        return "Muhatap kodu başka onaylı bir grupla çakışıyor. Modalda düzenleyebilirsiniz.";
      }
    }
  }
  return error instanceof Error ? error.message : fallback;
}

function parseMuhatapConflict(error: unknown): MuhatapConflictDetail | null {
  if (!axios.isAxiosError(error)) return null;
  const raw = error.response?.data?.detail;
  if (isMuhatapConflictDetail(raw)) return raw;
  return null;
}

const MERGE_ENTITY_ONBOARD_KEY = "mukerrer_merge_entity_onboarding_v1";

function parseMergeMinReviewers(raw: unknown): number {
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return Math.max(1, Math.min(20, Math.trunc(raw)));
  }
  if (raw && typeof raw === "object" && "value" in raw) {
    const v = Number((raw as { value: unknown }).value);
    if (Number.isFinite(v)) return Math.max(1, Math.min(20, Math.trunc(v)));
  }
  if (typeof raw === "string") {
    const v = Number(raw);
    if (Number.isFinite(v)) return Math.max(1, Math.min(20, Math.trunc(v)));
  }
  return 1;
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
  const [savingGolden, setSavingGolden] = useState(false);
  const [removeBusyId, setRemoveBusyId] = useState<number | null>(null);
  const [muhatapConflict, setMuhatapConflict] = useState<MuhatapConflictDetail | null>(null);
  const [mergeModalOpen, setMergeModalOpen] = useState(false);
  const [mergeApprovedGroups, setMergeApprovedGroups] = useState<DuplicateGroup[]>([]);
  const [mergeTargetEntityId, setMergeTargetEntityId] = useState<number | "">("");
  const [mergeLoading, setMergeLoading] = useState(false);
  const [mergeSubmitting, setMergeSubmitting] = useState(false);
  const [mergeOnboardingDismissed, setMergeOnboardingDismissed] = useState(
    () => typeof localStorage !== "undefined" && localStorage.getItem(MERGE_ENTITY_ONBOARD_KEY) === "1",
  );
  const [mergeMinReviewers, setMergeMinReviewers] = useState(1);
  const [coReviewAcknowledged, setCoReviewAcknowledged] = useState(false);
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
    getSettings()
      .then((s) => {
        const raw = (s as Record<string, unknown>).mukerrer_merge_min_reviewers;
        setMergeMinReviewers(parseMergeMinReviewers(raw));
      })
      .catch(() => setMergeMinReviewers(1));
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
    setCoReviewAcknowledged(false);
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

  const goldenDirtyApproved = useMemo(() => {
    if (!detailGroup) return false;
    return goldenFields.some(
      ({ key }) =>
        goldenDraft[key] !== (detailGroup.golden_record[key] ?? ""),
    );
  }, [detailGroup, goldenDraft]);

  const buildGoldenOverride = useCallback(
    () =>
      goldenFields.reduce<DuplicateGroup["golden_record"]>((acc, { key }) => {
        acc[key] = goldenDraft[key];
        return acc;
      }, {}),
    [goldenDraft],
  );

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
    if (approvedRecordIds.length < 2) {
      setApiError("Yeni birleşik grup oluşturmak için en az iki kayıt seçmelisiniz.");
      return;
    }
    setSavingGroupFinalize(true);
    setApiError("");
    setMuhatapConflict(null);
    try {
      const goldenRecordOverride = buildGoldenOverride();
      await partialApproveGroup({
        groupId: detailGroup.group_id,
        recordIds: detailGroup.record_ids,
        approvedRecordIds,
        rejectedRecordIds: [],
        uploadId: uploadId ?? detailGroup.records[0]?.upload_id,
        goldenRecordOverride,
        coReviewAcknowledged:
          mergeMinReviewers <= 1 ? true : coReviewAcknowledged,
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
      const conflict = parseMuhatapConflict(error);
      if (conflict) {
        setMuhatapConflict(conflict);
      }
      setApiError(getErrorMessage(error, "Golden record ve grup kararı kaydedilemedi."));
    } finally {
      setSavingGroupFinalize(false);
    }
  };

  const saveApprovedGolden = async () => {
    if (!detailGroup?.entity_id || !goldenDirtyApproved) return;
    setSavingGolden(true);
    setApiError("");
    setMuhatapConflict(null);
    try {
      const changed = goldenFields.reduce<Record<string, string>>((acc, { key }) => {
        if (goldenDraft[key] !== (detailGroup.golden_record[key] ?? "")) {
          acc[key] = goldenDraft[key];
        }
        return acc;
      }, {});
      await updateGoldenRecord({
        entityId: detailGroup.entity_id,
        fields: changed as DuplicateGroup["golden_record"],
        note: "Mükerrer kayıtlar ekranı",
      });
      setDetailGroup(null);
      groupsCacheRef.current.clear();
      await fetchGroups();
    } catch (error) {
      const conflict = parseMuhatapConflict(error);
      if (conflict) setMuhatapConflict(conflict);
      setApiError(getErrorMessage(error, "Golden güncellenemedi."));
    } finally {
      setSavingGolden(false);
    }
  };

  const openMergeIntoEntityModal = async () => {
    if (mergeMinReviewers > 1 && !coReviewAcknowledged) {
      setApiError(
        `Ayarlar en az ${mergeMinReviewers} inceleme onayı istiyor; önce onay kutusunu işaretleyin.`,
      );
      return;
    }
    if (!detailGroup || selectedRecordIds.size < 1) {
      setApiError("Var olan gruba eklemek için en az bir kayıt seçin.");
      return;
    }
    if (uploadId === null) return;
    setMergeModalOpen(true);
    setMergeTargetEntityId("");
    setMergeLoading(true);
    setApiError("");
    try {
      const res = await getDuplicateGroups({
        decision: "approved",
        uploadId,
        limit: 500,
        page: 1,
        pageSize: 100,
        differentMuhatapCode: false,
      });
      setMergeApprovedGroups(res.groups ?? []);
    } catch (e) {
      setMergeApprovedGroups([]);
      setApiError(e instanceof Error ? e.message : "Onaylı gruplar yüklenemedi.");
    } finally {
      setMergeLoading(false);
    }
  };

  const submitMergeIntoEntity = async () => {
    if (mergeMinReviewers > 1 && !coReviewAcknowledged) {
      setApiError(
        `En az ${mergeMinReviewers} onay için önce onay kutusunu işaretleyin.`,
      );
      return;
    }
    if (!detailGroup || uploadId === null || mergeTargetEntityId === "") return;
    const ids = [...selectedRecordIds];
    if (ids.length < 1) {
      setApiError("En az bir kayıt seçin.");
      return;
    }
    setMergeSubmitting(true);
    setApiError("");
    setMuhatapConflict(null);
    try {
      await mergePendingIntoEntity({
        groupId: detailGroup.group_id,
        entityId: Number(mergeTargetEntityId),
        recordIds: detailGroup.record_ids,
        approvedRecordIds: ids,
        uploadId,
        goldenRecordOverride: buildGoldenOverride(),
        coReviewAcknowledged:
          mergeMinReviewers <= 1 ? true : coReviewAcknowledged,
      });
      setMergeModalOpen(false);
      setDetailGroup(null);
      groupsCacheRef.current.clear();
      await fetchGroups();
    } catch (error) {
      const conflict = parseMuhatapConflict(error);
      if (conflict) setMuhatapConflict(conflict);
      setApiError(getErrorMessage(error, "Var olan gruba eklenemedi."));
    } finally {
      setMergeSubmitting(false);
    }
  };

  const removeMemberFromApprovedGroup = async (recordId: number) => {
    if (!detailGroup?.entity_id || uploadId === null) return;
    const n = detailGroup.record_ids.length;
    const lastPair =
      n <= 2
        ? "\n\nKalan tek kayıt onaylı gruplar listesinde görünmeyebilir. Kaldırılan kayıt bekleyen mükerrer incelemede yalnız başına görünmeyebilir."
        : "\n\nKaldırılan kayıt, bekleyen tarafta diğer adaylarla yeniden eşleşebilir.";
    const ok = window.confirm(
      `Kayıt #${recordId} bu onaylı golden gruptan çıkarılsın mı?${lastPair}`,
    );
    if (!ok) return;
    setRemoveBusyId(recordId);
    setApiError("");
    try {
      const res = await removeMergeMember({
        entityId: detailGroup.entity_id,
        recordId,
        uploadId,
      });
      if (!res.likely_visible_in_pending_heuristic) {
        window.alert(
          "Kaldırılan kayıt için bu yüklemede bekleyen (pending) eşleşme ucu bulunamadı; mükerrer inceleme listesinde görünmeyebilir.",
        );
      }
      setDetailGroup(null);
      groupsCacheRef.current.clear();
      await fetchGroups();
    } catch (error) {
      setApiError(getErrorMessage(error, "Kayıt gruptan kaldırılamadı."));
    } finally {
      setRemoveBusyId(null);
    }
  };

  if (uploadId === null) {
    return (
      <DashboardLayout>
        <Header
          title="İnceleme ve Birleştirme"
          subtitle="Benzer kayıt gruplarını inceleyin ve birleştirme kararını verin"
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
          title="İnceleme ve Birleştirme"
          subtitle="Önce mükerrer tespiti tamamlayın"
        />
        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          <FlowNav step="review" uploadId={uploadId} canGoNext={false} />
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-center">
            <i className="ri-radar-line mb-3 block text-3xl text-amber-600" />
            <p className="text-sm font-semibold text-amber-900">
              Bu dosya için henüz mükerrer tespit yapılmamış
            </p>
            <button
              type="button"
              onClick={() => navigate(`/mukerrer-tespit?upload_id=${uploadId}`)}
              className="mt-4 inline-flex cursor-pointer items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700"
            >
              <i className="ri-play-line" />
              Mükerrer Tespit Ekranına Git
            </button>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <Header
        title="İnceleme ve Birleştirme"
        subtitle="Benzer kayıt gruplarını inceleyin ve birleştirme kararını verin"
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
            <span className="font-semibold text-gray-900">İnceleme özeti</span>
            <span className="ml-2 text-xs text-gray-500">
              Bekleyen: {decisionFilter === "pending" ? total : "—"} · Birleştirilen kayıtlar raporda
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => navigate(`/raporlar?upload_id=${uploadId}&tab=muhatap-merge`)}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              <i className="ri-bar-chart-box-line" />
              Ayrıntılı rapor
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
              PDF olarak indir
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
            <p className="text-xs text-gray-400">Sayfada Göster</p>
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
                  {formatUploadOptionLabel(u)}
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
            İnceleme Bekliyor
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
            Birleştirildi
          </button>
        </div>
        <p className="text-[11px] text-gray-500">
          Bu liste yalnızca <strong>farklı muhatap kodlu</strong> kayıt gruplarını gösterir.
        </p>

        <div className="relative w-full">
          <i className="ri-search-line absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Grup no, ad, TC, telefon veya e-posta ile ara..."
            className="w-full rounded-lg border border-gray-200 py-2.5 pl-9 pr-4 text-sm focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-100"
          />
        </div>

        <div className="flex items-center justify-between">
          <button
            disabled={page <= 1}
            onClick={() => goPage(Math.max(1, page - 1))}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 disabled:opacity-50"
          >
            Geri
          </button>
          <button
            disabled={page >= totalPages}
            onClick={() => goPage(Math.min(totalPages, page + 1))}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 disabled:opacity-50"
          >
            İleri
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
              Kayıt grupları ({decisionFilter === "pending" ? "inceleme bekliyor" : "birleştirildi"})
            </h3>
          </div>
          <div className="overflow-x-auto">
            {filtered.length === 0 && !loading ? (
              <div className="py-10 text-center text-sm text-gray-400">
                Bu filtre için mükerrer grup bulunmuyor.
              </div>
            ) : (
              <table className="w-full min-w-[960px] text-xs">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/70">
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Grup No</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Kayıt Sayısı</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Benzerlik</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Birleştirilmiş Kayıt</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Muhatap Kodları</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-400">Aksiyon</th>
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
                          İncele
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
        onSelectAllRecords={
          decisionFilter === "pending" ? selectAllInGroup : undefined
        }
        onClearAllRecords={
          decisionFilter === "pending" ? clearRecordSelection : undefined
        }
        getRecordMuhatapNoDisplay={getRecordMuhatapNoDisplay}
        onClose={() => setDetailGroup(null)}
        onSave={() =>
          void (decisionFilter === "approved"
            ? saveApprovedGolden()
            : saveGroupGoldenFinalize())
        }
        saving={
          decisionFilter === "approved" ? savingGolden : savingGroupFinalize
        }
        reviewMode={
          decisionFilter === "approved" ? "approved_entity" : "pending_merge"
        }
        onRemoveMember={
          decisionFilter === "approved"
            ? (id) => void removeMemberFromApprovedGroup(id)
            : undefined
        }
        blockingRecordActionId={removeBusyId}
        primaryActionEnabled={
          decisionFilter === "approved"
            ? goldenDirtyApproved && !savingGolden
            : selectedRecordIds.size >= 2 &&
              (mergeMinReviewers <= 1 || coReviewAcknowledged)
        }
        footerStartExtra={
          decisionFilter === "pending" ? (
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
              {mergeMinReviewers > 1 ? (
                <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 text-xs text-amber-950">
                  <input
                    type="checkbox"
                    checked={coReviewAcknowledged}
                    onChange={(e) => setCoReviewAcknowledged(e.target.checked)}
                  />
                  <span>
                    En az {mergeMinReviewers} ayrı inceleme onayı tamamlandı
                    (Ayarlar sayfasındaki onay kuralı)
                  </span>
                </label>
              ) : null}
              <button
                type="button"
                onClick={() => void openMergeIntoEntityModal()}
                disabled={
                  savingGroupFinalize ||
                  mergeSubmitting ||
                  selectedRecordIds.size < 1 ||
                  (mergeMinReviewers > 1 && !coReviewAcknowledged)
                }
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-xs font-semibold text-blue-800 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <i className="ri-links-line" />
                Var olan gruba ekle
              </button>
            </div>
          ) : undefined
        }
        leftExtra={
          <div>
              <div className="mb-3 text-xs font-semibold text-gray-700">
                Birleştirilmiş kayıt alanlarını düzenle
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

      {muhatapConflict ? (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onClick={() => setMuhatapConflict(null)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl"
            role="dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-semibold text-amber-900">
              Muhatap kodu çakışıyor
            </h3>
            <p className="mt-2 text-xs text-gray-600">
              Önerilen kod{" "}
              <span className="font-mono font-semibold">
                {muhatapConflict.proposed_muhatap || "—"}
              </span>{" "}
              aşağıdaki onaylı gruplarda zaten kullanılıyor. Muhatap kodunu (veya golden
              alanları) düzenleyip tekrar deneyin.
            </p>
            <ul className="mt-3 max-h-40 list-inside list-disc overflow-y-auto text-xs text-gray-800">
              {muhatapConflict.conflicts.map((c) => (
                <li key={`${c.entity_id}-${c.upload_id ?? ""}`}>
                  Entity #{c.entity_id}
                  {c.upload_id != null ? ` · yükleme #${c.upload_id}` : ""}
                  {c.canonical_name ? ` — ${c.canonical_name}` : ""}
                </li>
              ))}
            </ul>
            <label className="mb-1 mt-4 block text-xs font-medium text-gray-700">
              Muhatap kodunu düzenle
            </label>
            <input
              value={goldenDraft.clean_muhatap_no}
              onChange={(e) =>
                setGoldenDraft((prev) => ({
                  ...prev,
                  clean_muhatap_no: e.target.value,
                }))
              }
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setMuhatapConflict(null)}
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                Kapat
              </button>
              <button
                type="button"
                onClick={() => {
                  if (mergeModalOpen) void submitMergeIntoEntity();
                  else if (detailGroup && decisionFilter === "pending")
                    void saveGroupGoldenFinalize();
                  else void saveApprovedGolden();
                }}
                disabled={
                  !goldenDraft.clean_muhatap_no.trim() ||
                  savingGroupFinalize ||
                  savingGolden ||
                  mergeSubmitting ||
                  (mergeModalOpen &&
                    (mergeTargetEntityId === "" || mergeLoading))
                }
                className="rounded-lg bg-amber-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-800 disabled:opacity-50"
              >
                Yeniden dene
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {mergeModalOpen && detailGroup && uploadId !== null ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onClick={() => !mergeSubmitting && setMergeModalOpen(false)}
        >
          <div
            className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"
            role="dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-semibold text-gray-900">
              Var olan onaylı gruba ekle
            </h3>
            {!mergeOnboardingDismissed ? (
              <div className="mt-3 rounded-lg border border-blue-100 bg-blue-50/80 p-3 text-xs text-blue-950">
                <p>
                  Seçtiğiniz kayıtlar yeni bir birleşik grup oluşturmak yerine, aşağıda
                  seçeceğiniz mevcut onaylı gruba bağlanır. Muhatap kodu diğer
                  onaylı gruplarla çakışırsa sistem uyarı verir; golden alanını
                  düzenleyip tekrar deneyebilirsiniz.
                </p>
                <button
                  type="button"
                  className="mt-2 text-xs font-semibold text-blue-800 underline"
                  onClick={() => {
                    localStorage.setItem(MERGE_ENTITY_ONBOARD_KEY, "1");
                    setMergeOnboardingDismissed(true);
                  }}
                >
                  Anladım
                </button>
              </div>
            ) : null}
            <p className="mt-2 text-xs text-gray-500">
              Kaynak grup: <span className="font-medium">{detailGroup.group_id}</span> ·
              Seçili {selectedRecordIds.size} kayıt
            </p>
            <label className="mb-1 mt-4 block text-xs font-medium text-gray-600">
              Hedef onaylı grup (entity)
            </label>
            {mergeLoading ? (
              <p className="text-xs text-gray-500">Liste yükleniyor…</p>
            ) : (
              <select
                value={mergeTargetEntityId === "" ? "" : String(mergeTargetEntityId)}
                onChange={(e) => {
                  const v = e.target.value;
                  setMergeTargetEntityId(v === "" ? "" : Number(v));
                }}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
              >
                <option value="">— Seçin —</option>
                {mergeApprovedGroups.map((g) => {
                  const eid = g.entity_id;
                  if (eid == null) return null;
                  return (
                    <option key={g.group_id} value={String(eid)}>
                      #{eid} — {g.golden_record.clean_name || g.group_id} (
                      {g.record_ids.length} üye)
                    </option>
                  );
                })}
              </select>
            )}
            <p className="mt-3 text-[11px] text-gray-500">
              Bu yüklemedeki tüm onaylı birleşik gruplar (tek/çok muhatap) listelenir.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                disabled={mergeSubmitting}
                onClick={() => setMergeModalOpen(false)}
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                Vazgeç
              </button>
              <button
                type="button"
                disabled={
                  mergeSubmitting ||
                  mergeTargetEntityId === "" ||
                  mergeLoading ||
                  (mergeMinReviewers > 1 && !coReviewAcknowledged)
                }
                onClick={() => void submitMergeIntoEntity()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {mergeSubmitting ? (
                  <i className="ri-loader-4-line animate-spin" />
                ) : (
                  <i className="ri-check-line" />
                )}
                Ekle
              </button>
            </div>
          </div>
        </div>
      ) : null}

    </DashboardLayout>
  );
}
