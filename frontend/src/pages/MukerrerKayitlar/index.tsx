import { useEffect, useRef, useState } from "react";

import DashboardLayout from "../../components/feature/DashboardLayout";
import FieldComparisonsPanel from "../../components/feature/FieldComparisonsPanel";
import Header from "../../components/feature/Header";
import {
  getPendingMatches,
  approvePendingMatch,
  rejectPendingMatch,
} from "../../services/api";
import {
  finalDecisionTone,
  mapPendingMatchToView,
  type PairWorkflowState,
  type UiDuplicatePair,
} from "../../utils/duplicatePairView";

const decisionBadge: Record<PairWorkflowState, string> = {
  bekleyen: "border border-yellow-200 bg-yellow-50 text-yellow-700",
  onaylandi: "border border-green-200 bg-green-50 text-green-700",
  reddedildi: "border border-red-200 bg-red-50 text-red-600",
};

const decisionLabel: Record<PairWorkflowState | "tumu", string> = {
  tumu: "Tümü",
  bekleyen: "Bekleyen",
  onaylandi: "Onaylandı",
  reddedildi: "Reddedildi",
};

export default function MukerrerKayitlar() {
  const [search, setSearch] = useState("");
  const [filterDecision, setFilterDecision] = useState<PairWorkflowState | "tumu">("tumu");
  const [selected, setSelected] = useState<string[]>([]);
  const [detailGroup, setDetailGroup] = useState<UiDuplicatePair | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [data, setData] = useState<UiDuplicatePair[]>([]);
  const [apiError, setApiError] = useState("");
  const isMountedRef = useRef(true);

  const fetchData = async () => {
    setLoading(true);
    setApiError("");
    try {
      const lastUploadId = localStorage.getItem("lastDetectUploadId");
      const uploadId = lastUploadId ? Number(lastUploadId) : undefined;
      const response = await getPendingMatches({ uploadId, limit: 200 });
      if (!isMountedRef.current) return;
      const mapped = (response.matches || []).map(mapPendingMatchToView);
      setData(mapped);
    } catch (err) {
      if (!isMountedRef.current) return;
      setApiError(err instanceof Error ? err.message : "Veriler yüklenemedi.");
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    isMountedRef.current = true;
    fetchData();
    return () => { isMountedRef.current = false; };
  }, []);

  const filtered = data.filter((group) => {
    const matchSearch =
      !search ||
      group.records.some(
        (r) =>
          r.adSoyad.toLowerCase().includes(search.toLowerCase()) ||
          r.muhatapNo.toLowerCase().includes(search.toLowerCase()) ||
          r.tcKimlikNo.includes(search),
      );
    const matchDecision =
      filterDecision === "tumu" || group.workflowState === filterDecision;
    return matchSearch && matchDecision;
  });

  const toggleSelect = (id: string) =>
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id],
    );

  const toggleAll = () =>
    setSelected(selected.length === filtered.length ? [] : filtered.map((g) => g.id));

  const updateGroup = (id: string, updates: Partial<UiDuplicatePair>) => {
    setData((prev) => prev.map((g) => (g.id === id ? { ...g, ...updates } : g)));
  };

  const handleBulkApprove = async () => {
    setActionLoading(true);
    for (const id of selected) {
      const target = data.find((g) => g.id === id);
      if (!target?.backendMatchId) continue;
      try {
        await approvePendingMatch({ matchId: target.backendMatchId, mergeIntoEntity: true });
        updateGroup(id, { workflowState: "onaylandi", backendDecision: "approved" });
      } catch { /* continue */ }
    }
    setSelected([]);
    setActionLoading(false);
  };

  const handleBulkReject = async () => {
    setActionLoading(true);
    for (const id of selected) {
      const target = data.find((g) => g.id === id);
      if (!target?.backendMatchId) continue;
      try {
        await rejectPendingMatch({ matchId: target.backendMatchId });
        updateGroup(id, { workflowState: "reddedildi", backendDecision: "rejected" });
      } catch { /* continue */ }
    }
    setSelected([]);
    setActionLoading(false);
  };

  return (
    <DashboardLayout>
      <Header
        title="Mükerrer Kayıtlar"
        subtitle="Tespit edilen mükerrer kayıtları alan bazlı skorlarla yönetin"
        actions={
          <div className="flex items-center gap-3">
            <button
              onClick={fetchData}
              disabled={loading}
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-60"
            >
              <i className={loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"} />
              Yenile
            </button>
            {selected.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">{selected.length} seçildi</span>
                <button
                  onClick={handleBulkApprove}
                  disabled={actionLoading}
                  className="flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg bg-green-600 px-3 py-2 text-xs text-white hover:bg-green-700 disabled:opacity-60"
                >
                  <i className="ri-checkbox-circle-line" /> Toplu Onayla
                </button>
                <button
                  onClick={handleBulkReject}
                  disabled={actionLoading}
                  className="flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg bg-red-600 px-3 py-2 text-xs text-white hover:bg-red-700 disabled:opacity-60"
                >
                  <i className="ri-close-circle-line" /> Toplu Reddet
                </button>
              </div>
            )}
          </div>
        }
      />

      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        {loading && (
          <div className="flex items-center gap-3 rounded-xl border border-blue-100 bg-blue-50 p-4">
            <i className="ri-loader-4-line animate-spin text-lg text-blue-600" />
            <p className="text-sm text-blue-700">Mükerrer kayıtlar yükleniyor…</p>
          </div>
        )}

        {apiError && (
          <div className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 p-4">
            <i className="ri-error-warning-fill text-lg text-red-600" />
            <p className="text-sm text-red-700">{apiError}</p>
          </div>
        )}

        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
          <div className="relative w-full flex-1">
            <i className="ri-search-line absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Ad soyad, muhatap no veya TC ile ara…"
              className="w-full rounded-lg border border-gray-200 py-2.5 pl-9 pr-4 text-sm focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-100"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {(["tumu", "bekleyen", "onaylandi", "reddedildi"] as const).map((value) => (
              <button
                key={value}
                onClick={() => setFilterDecision(value)}
                className={`cursor-pointer rounded-lg px-4 py-2 text-xs transition-colors whitespace-nowrap ${
                  filterDecision === value
                    ? "bg-red-600 text-white"
                    : "border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                {decisionLabel[value]}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/70">
                  <th className="w-10 px-5 py-3">
                    <input
                      type="checkbox"
                      checked={selected.length === filtered.length && filtered.length > 0}
                      onChange={toggleAll}
                      className="cursor-pointer accent-red-600"
                    />
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Skor</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Kayıt 1</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Kayıt 2</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Telefon / E-posta</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Karar</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-400">İşlem</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((group) => {
                  const scoreColor =
                    group.score >= 90
                      ? "bg-red-50 text-red-600"
                      : group.score >= 80
                        ? "bg-orange-50 text-orange-500"
                        : "bg-yellow-50 text-yellow-600";

                  return (
                    <tr
                      key={group.id}
                      className={`transition-colors hover:bg-gray-50/50 ${selected.includes(group.id) ? "bg-red-50/30" : ""}`}
                    >
                      <td className="px-5 py-3.5">
                        <input
                          type="checkbox"
                          checked={selected.includes(group.id)}
                          onChange={() => toggleSelect(group.id)}
                          className="cursor-pointer accent-red-600"
                        />
                      </td>
                      <td className="px-4 py-3.5">
                        <span className={`inline-block rounded-full px-2.5 py-1 text-sm font-bold ${scoreColor}`}>
                          %{group.score.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-4 py-3.5">
                        <p className="font-medium text-gray-800">{group.records[0].adSoyad}</p>
                        <p className="text-gray-400">
                          {group.records[0].tcKimlikNo || "-"} · #{group.backendMatchId}
                        </p>
                      </td>
                      <td className="px-4 py-3.5">
                        <p className="font-medium text-gray-800">{group.records[1].adSoyad}</p>
                        <p className="text-gray-400">{group.records[1].tcKimlikNo || "-"}</p>
                      </td>
                      <td className="px-4 py-3.5 text-gray-500">
                        <p>{group.records[0].telefon || "-"}</p>
                        <p className="mt-1">{group.records[0].email || "-"}</p>
                      </td>
                      <td className="px-4 py-3.5">
                        <span className={`inline-block rounded-full px-2.5 py-1 text-[11px] font-medium ${finalDecisionTone(group.finalDecision)}`}>
                          {group.finalDecisionLabel}
                        </span>
                        <div className="mt-2">
                          <span className={`inline-block rounded-full px-2.5 py-1 text-[11px] font-medium ${decisionBadge[group.workflowState]}`}>
                            {decisionLabel[group.workflowState]}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-center">
                        <button
                          onClick={() => setDetailGroup(group)}
                          className="cursor-pointer whitespace-nowrap text-xs font-medium text-red-600 hover:underline"
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
                {data.length === 0
                  ? "Henüz mükerrer kayıt yok. Mükerrer Tespit adımını tamamlayın."
                  : "Kayıt bulunamadı."}
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
            className="max-h-[85vh] w-full max-w-4xl overflow-y-auto rounded-2xl bg-white"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
              <div>
                <h2 className="text-base font-bold text-gray-900">
                  Kayıt Karşılaştırma — Match #{detailGroup.backendMatchId ?? detailGroup.id}
                </h2>
                <p className="mt-0.5 text-xs text-gray-400">
                  Splink alan karşılaştırmaları ve kural gerekçeleri
                </p>
              </div>
              <button
                onClick={() => setDetailGroup(null)}
                className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100"
              >
                <i className="ri-close-line text-lg" />
              </button>
            </div>

            <div className="space-y-5 p-6">
              <FieldComparisonsPanel
                fieldComparisons={detailGroup.fieldComparisons}
                overallScore={detailGroup.score}
                finalDecision={detailGroup.finalDecision}
                finalDecisionLabel={detailGroup.finalDecisionLabel}
                riskFlags={detailGroup.riskFlags}
                ruleReasons={detailGroup.ruleReasons}
              />

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {detailGroup.records.map((record, index) => (
                  <div
                    key={`${detailGroup.id}-${record.muhatapNo}`}
                    className={`rounded-xl border-2 p-4 ${index === 0 ? "border-gray-200" : "border-red-200 bg-red-50/20"}`}
                  >
                    <div className="mb-3 flex items-center gap-2">
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${index === 0 ? "bg-gray-100 text-gray-600" : "bg-red-100 text-red-600"}`}>
                        Kayıt {index + 1}
                      </span>
                      <span className="text-xs text-gray-500">{record.muhatapNo}</span>
                    </div>
                    {[
                      ["Ad Soyad", record.adSoyad],
                      ["TC Kimlik", record.tcKimlikNo],
                      ["Telefon", record.telefon],
                      ["E-posta", record.email],
                      ["Şehir", record.sehir],
                    ].map(([label, value]) => (
                      <div key={label} className="mb-2">
                        <p className="text-[10px] text-gray-400">{label}</p>
                        <p className="break-words text-xs font-medium text-gray-800">{value}</p>
                      </div>
                    ))}
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
