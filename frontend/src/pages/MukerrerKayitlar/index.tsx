import { useEffect, useMemo, useRef, useState } from "react";

import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  getDuplicateGroups,
  type DuplicateGroup,
} from "../../services/api";

function pct(value: number): string {
  return `%${(Number(value || 0) * 100).toFixed(1)}`;
}

function filterClass(active: boolean): string {
  return active
    ? "bg-red-600 text-white"
    : "border border-gray-200 text-gray-600 hover:bg-gray-50";
}

export default function MukerrerKayitlar() {
  const [decisionFilter, setDecisionFilter] = useState<
    "pending" | "approved" | "rejected"
  >("approved");
  const [search, setSearch] = useState("");
  const [detailGroup, setDetailGroup] = useState<DuplicateGroup | null>(null);
  const [loading, setLoading] = useState(false);
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [apiError, setApiError] = useState("");
  const isMountedRef = useRef(true);

  const fetchGroups = async (
    decision: "pending" | "approved" | "rejected",
  ) => {
    setLoading(true);
    setApiError("");
    try {
      const lastUploadId = localStorage.getItem("lastDetectUploadId");
      const uploadId = lastUploadId ? Number(lastUploadId) : undefined;
      const response = await getDuplicateGroups({
        decision,
        uploadId,
        limit: 5000,
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
  };

  useEffect(() => {
    isMountedRef.current = true;
    fetchGroups(decisionFilter);
    return () => {
      isMountedRef.current = false;
    };
  }, [decisionFilter]);

  const filtered = useMemo(() => {
    if (!search) return groups;
    const text = search.toLowerCase();
    return groups.filter((group) => {
      if (group.group_id.toLowerCase().includes(text)) return true;
      return group.records.some(
        (record) =>
          record.clean_name.toLowerCase().includes(text) ||
          record.clean_tc.includes(search) ||
          record.clean_phone.includes(search) ||
          record.clean_email.toLowerCase().includes(text),
      );
    });
  }, [groups, search]);

  return (
    <DashboardLayout>
      <Header
        title="Mükerrer Kayıtlar"
        subtitle="Pair yerine duplicate group ve golden record görünümü"
        actions={
          <button
            onClick={() => fetchGroups(decisionFilter)}
            disabled={loading}
            className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-60"
          >
            <i className={loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"} />
            Yenile
          </button>
        }
      />

      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        <div className="flex items-center gap-2">
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
            <table className="w-full min-w-[900px] text-xs">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/70">
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Group ID</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Record Count</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Match Count</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Group Score</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Golden Name</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-400">İşlem</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((group) => (
                  <tr key={group.group_id} className="transition-colors hover:bg-gray-50/50">
                    <td className="px-4 py-3.5 font-medium text-gray-800">{group.group_id}</td>
                    <td className="px-4 py-3.5 text-gray-600">{group.record_ids.length}</td>
                    <td className="px-4 py-3.5 text-gray-600">{group.match_count}</td>
                    <td className="px-4 py-3.5 text-gray-600">{pct(group.group_score)}</td>
                    <td className="px-4 py-3.5 text-gray-700">{group.golden_record.clean_name || "-"}</td>
                    <td className="px-4 py-3.5 text-center">
                      <button
                        onClick={() => setDetailGroup(group)}
                        className="cursor-pointer text-xs font-medium text-red-600 hover:underline"
                      >
                        Detay
                      </button>
                    </td>
                  </tr>
                ))}
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
            className="max-h-[85vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white"
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

            <div className="space-y-5 p-6">
              <div className="rounded-xl border border-green-100 bg-green-50 p-4">
                <h3 className="mb-3 text-sm font-semibold text-green-800">Golden Record</h3>
                <div className="grid grid-cols-1 gap-3 text-xs md:grid-cols-2">
                  <div><span className="text-gray-500">Ad Soyad:</span> {detailGroup.golden_record.clean_name || "-"}</div>
                  <div><span className="text-gray-500">TC:</span> {detailGroup.golden_record.clean_tc || "-"}</div>
                  <div><span className="text-gray-500">Telefon:</span> {detailGroup.golden_record.clean_phone || "-"}</div>
                  <div><span className="text-gray-500">E-posta:</span> {detailGroup.golden_record.clean_email || "-"}</div>
                  <div><span className="text-gray-500">Şehir:</span> {detailGroup.golden_record.clean_city || "-"}</div>
                  <div><span className="text-gray-500">Adres:</span> {detailGroup.golden_record.clean_address || "-"}</div>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {detailGroup.records.map((record) => (
                  <div key={record.record_id} className="rounded-xl border border-gray-200 p-4">
                    <div className="mb-2 text-xs font-semibold text-gray-700">Record #{record.record_id}</div>
                    <div className="space-y-1 text-xs text-gray-700">
                      <div><span className="text-gray-500">Ad Soyad:</span> {record.clean_name || "-"}</div>
                      <div><span className="text-gray-500">TC:</span> {record.clean_tc || "-"}</div>
                      <div><span className="text-gray-500">Telefon:</span> {record.clean_phone || "-"}</div>
                      <div><span className="text-gray-500">E-posta:</span> {record.clean_email || "-"}</div>
                      <div><span className="text-gray-500">Şehir:</span> {record.clean_city || "-"}</div>
                      <div><span className="text-gray-500">Adres:</span> {record.clean_address || "-"}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
