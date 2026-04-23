import { useEffect, useRef, useState } from "react";

import DashboardLayout from "../../components/feature/DashboardLayout";
import FieldComparisonsPanel from "../../components/feature/FieldComparisonsPanel";
import Header from "../../components/feature/Header";
import { auditLog, yoneticiler, type AuditLogItem } from "../../mocks/approval";
import { mockDuplicateGroups } from "../../mocks/records";
import {
  approvePendingMatch,
  getPendingMatches,
  rejectPendingMatch,
} from "../../services/api";
import {
  mapMockGroupToView,
  mapPendingMatchToView,
  type PairWorkflowState,
  type UiDuplicatePair,
} from "../../utils/duplicatePairView";

type TabType = PairWorkflowState;

function workflowLabel(value: PairWorkflowState): string {
  if (value === "onaylandi") {
    return "Onaylanan";
  }
  if (value === "reddedildi") {
    return "Reddedilen";
  }
  return "Bekleyen";
}

export default function YoneticiOnayi() {
  const [tab, setTab] = useState<TabType>("bekleyen");
  const [detailGroup, setDetailGroup] = useState<UiDuplicatePair | null>(null);
  const [searchAudit, setSearchAudit] = useState("");
  const [filterYonetici, setFilterYonetici] = useState("Tumu");
  const [loading, setLoading] = useState(false);
  const [realData, setRealData] = useState<UiDuplicatePair[]>([]);
  const [realAuditLog, setRealAuditLog] = useState<AuditLogItem[]>([]);
  const [decisionNote, setDecisionNote] = useState("");
  const [apiError, setApiError] = useState("");
  const [lastUploadId, setLastUploadId] = useState<number | null>(null);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const isMountedRef = useRef(true);

  const refreshPendingMatches = async (uploadId?: number) => {
    setLoading(true);
    setApiError("");

    try {
      const response = await getPendingMatches({
        uploadId,
        limit: 100,
      });
      const mapped = (response.matches || []).map(mapPendingMatchToView);

      if (!isMountedRef.current) {
        return;
      }

      setRealData((prev) => {
        const approvedOrRejected = prev.filter(
          (group) => group.workflowState !== "bekleyen",
        );
        return [...mapped, ...approvedOrRejected];
      });
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }
      setApiError(
        error instanceof Error
          ? error.message
          : "Pending kayitlar alinamadi.",
      );
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    isMountedRef.current = true;

    import("../../services/api")
      .then(({ healthCheck }) => healthCheck())
      .then(() => {
        if (!isMountedRef.current) {
          return;
        }
        setBackendHealthy(true);

        const storedUpload = localStorage.getItem("lastDetectUploadId");
        const parsedUpload = storedUpload ? Number(storedUpload) : Number.NaN;
        const uploadId = Number.isFinite(parsedUpload) ? parsedUpload : undefined;
        setLastUploadId(uploadId ?? null);
        refreshPendingMatches(uploadId);
      })
      .catch(() => {
        if (isMountedRef.current) {
          setBackendHealthy(false);
        }
      });

    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const mockData = mockDuplicateGroups.map(mapMockGroupToView);
  const data = realData.length > 0 ? realData : mockData;
  const logData = realAuditLog.length > 0 ? realAuditLog : auditLog;

  const bekleyen = data.filter((group) => group.workflowState === "bekleyen");
  const onaylandi = data.filter((group) => group.workflowState === "onaylandi");
  const reddedildi = data.filter((group) => group.workflowState === "reddedildi");

  const filteredLog = logData.filter((item) => {
    const matchSearch =
      !searchAudit ||
      item.grup.toLowerCase().includes(searchAudit.toLowerCase()) ||
      item.yonetici.toLowerCase().includes(searchAudit.toLowerCase());
    const matchYonetici =
      filterYonetici === "Tumu" || item.yonetici === filterYonetici;
    return matchSearch && matchYonetici;
  });

  const updateWorkflowState = (groupId: string, workflowState: PairWorkflowState) => {
    setRealData((prev) =>
      prev.map((group) =>
        group.id === groupId ? { ...group, workflowState } : group,
      ),
    );
  };

  const handleApprove = async (groupId: string) => {
    const target = data.find((group) => group.id === groupId);
    if (!target?.backendMatchId) {
      return;
    }

    setLoading(true);
    setApiError("");

    const now = new Date().toLocaleString("tr-TR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

    try {
      await approvePendingMatch({
        matchId: target.backendMatchId,
        approvedBy: "Ahmet Yilmaz",
        mergeIntoEntity: true,
      });

      updateWorkflowState(groupId, "onaylandi");

      const newLog: AuditLogItem = {
        id: `LOG-${String(realAuditLog.length + auditLog.length + 1).padStart(3, "0")}`,
        grup: groupId,
        yonetici: "Ahmet Yilmaz",
        islem: "Onaylandı",
        tarih: now,
        not: decisionNote || "Onaylandi",
      };
      setRealAuditLog((prev) => [newLog, ...prev]);

      setDetailGroup(null);
      setDecisionNote("");
      setTab("onaylandi");
    } catch (error) {
      setApiError(
        error instanceof Error ? error.message : "Onay islemi basarisiz.",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async (groupId: string) => {
    const target = data.find((group) => group.id === groupId);
    if (!target?.backendMatchId) {
      return;
    }

    setLoading(true);
    setApiError("");

    const now = new Date().toLocaleString("tr-TR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

    try {
      await rejectPendingMatch({
        matchId: target.backendMatchId,
        rejectedBy: "Ahmet Yilmaz",
        reason: decisionNote || "Reddedildi",
      });

      updateWorkflowState(groupId, "reddedildi");

      const newLog: AuditLogItem = {
        id: `LOG-${String(realAuditLog.length + auditLog.length + 1).padStart(3, "0")}`,
        grup: groupId,
        yonetici: "Ahmet Yilmaz",
        islem: "Reddedildi",
        tarih: now,
        not: decisionNote || "Reddedildi",
      };
      setRealAuditLog((prev) => [newLog, ...prev]);

      setDetailGroup(null);
      setDecisionNote("");
      setTab("reddedildi");
    } catch (error) {
      setApiError(
        error instanceof Error ? error.message : "Reddetme islemi basarisiz.",
      );
    } finally {
      setLoading(false);
    }
  };

  const refreshLabel = lastUploadId
    ? `Yenile (Upload ${lastUploadId})`
    : "Tumunu Yenile";

  const tabs: { key: TabType; label: string; count: number; color: string }[] = [
    {
      key: "bekleyen",
      label: "Bekleyen",
      count: bekleyen.length,
      color: "border-yellow-200 bg-yellow-50 text-yellow-700",
    },
    {
      key: "onaylandi",
      label: "Onaylanan",
      count: onaylandi.length,
      color: "border-green-200 bg-green-50 text-green-700",
    },
    {
      key: "reddedildi",
      label: "Reddedilen",
      count: reddedildi.length,
      color: "border-red-200 bg-red-50 text-red-600",
    },
  ];

  return (
    <DashboardLayout>
      <Header
        title="Yonetici Onayi"
        subtitle="Mukerrer kayit kararlarini yonetin ve denetleyin"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="rounded bg-red-50 px-2 py-1 text-xs text-red-600">
                Backend: Erisilemiyor
              </span>
            )}
            <button
              onClick={() => refreshPendingMatches(lastUploadId ?? undefined)}
              disabled={loading || backendHealthy === false}
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50"
            >
              <i className={loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"} />
              {refreshLabel}
            </button>
          </div>
        }
      />

      <div className="flex-1 space-y-5 overflow-y-auto p-6">
        {lastUploadId && (
          <div className="flex items-center gap-3 rounded-xl border border-amber-100 bg-amber-50 p-4">
            <i className="ri-information-line text-lg text-amber-600" />
            <p className="text-sm text-amber-700">
              Yonetici onayi son detect calismasi uzerinden filtreleniyor. Upload ID:{" "}
              {lastUploadId}
            </p>
          </div>
        )}

        {apiError && (
          <div className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 p-4">
            <i className="ri-error-warning-fill text-lg text-red-600" />
            <p className="text-sm text-red-700">{apiError}</p>
          </div>
        )}

        {loading && (
          <div className="flex items-center gap-3 rounded-xl border border-blue-100 bg-blue-50 p-4">
            <i className="ri-loader-4-line animate-spin text-lg text-blue-600" />
            <p className="text-sm text-blue-700">Backend verileri yukleniyor...</p>
          </div>
        )}

        <div className="flex w-fit gap-1 rounded-xl bg-gray-100/60 p-1">
          {tabs.map((item) => (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              className={`flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-lg px-5 py-2 text-sm font-medium transition-all ${
                tab === item.key
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {item.label}
              <span
                className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${item.color}`}
              >
                {item.count}
              </span>
            </button>
          ))}
        </div>

        {tab === "bekleyen" && (
          <div className="rounded-xl border border-gray-100 bg-white">
            <div className="border-b border-gray-50 px-5 py-4">
              <h3 className="text-sm font-semibold text-gray-900">Onay Bekleyen Kayitlar</h3>
              <p className="mt-0.5 text-xs text-gray-400">
                Splink alan karsilastirmalarini inceleyip karar verin
              </p>
            </div>
            <div className="divide-y divide-gray-50">
              {bekleyen.map((group) => (
                <div
                  key={group.id}
                  className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-gray-50/50"
                >
                  <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-yellow-50">
                    <i className="ri-time-line text-lg text-yellow-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-gray-800">{group.id}</span>
                      <span className="text-xs text-gray-500">
                        {group.records[0].adSoyad} / {group.records[1].adSoyad}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-gray-400">
                      Match ID: {group.backendMatchId} - Skor: %{group.score.toFixed(1)}
                    </p>
                    <p className="mt-0.5 text-xs text-gray-500">
                      Nihai sistem karari: {group.finalDecisionLabel}
                    </p>
                    {group.decisionReason && (
                      <p className="mt-0.5 text-xs text-gray-500">
                        Karar nedeni: {group.decisionReason}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => setDetailGroup(group)}
                    className="cursor-pointer whitespace-nowrap rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50"
                  >
                    Detay ve Karar Ver
                  </button>
                </div>
              ))}
              {bekleyen.length === 0 && (
                <div className="py-10 text-center text-sm text-gray-400">
                  Bekleyen kayit yok.
                </div>
              )}
            </div>
          </div>
        )}

        {(tab === "onaylandi" || tab === "reddedildi") && (
          <div className="space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="relative flex-1">
                <i className="ri-search-line absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400" />
                <input
                  type="text"
                  value={searchAudit}
                  onChange={(event) => setSearchAudit(event.target.value)}
                  placeholder="Grup ID veya yonetici ara..."
                  className="w-full rounded-lg border border-gray-200 py-2.5 pl-9 pr-4 text-sm focus:border-red-400 focus:outline-none"
                />
              </div>
              <select
                value={filterYonetici}
                onChange={(event) => setFilterYonetici(event.target.value)}
                className="cursor-pointer rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm focus:border-red-400 focus:outline-none"
              >
                <option>Tumu</option>
                {yoneticiler.map((yonetici) => (
                  <option key={yonetici}>{yonetici}</option>
                ))}
              </select>
            </div>

            <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50/70">
                      <th className="px-5 py-3 text-left font-medium text-gray-400">Grup</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Yonetici</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Islem</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Tarih</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Not</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {filteredLog
                      .filter((item) =>
                        tab === "onaylandi"
                          ? item.islem === "Onaylandı"
                          : item.islem === "Reddedildi",
                      )
                      .map((item) => (
                        <tr key={item.id} className="transition-colors hover:bg-gray-50/50">
                          <td className="px-5 py-3.5 font-medium text-gray-700">{item.grup}</td>
                          <td className="px-4 py-3.5">
                            <div className="flex items-center gap-2">
                              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-red-100 text-[10px] font-bold text-red-600">
                                {item.yonetici
                                  .split(" ")
                                  .map((part) => part[0])
                                  .join("")}
                              </div>
                              <span className="text-gray-700">{item.yonetici}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3.5">
                            <span
                              className={`inline-block rounded-full px-2.5 py-1 text-[11px] font-medium ${
                                item.islem === "Onaylandı"
                                  ? "bg-green-50 text-green-700"
                                  : "bg-red-50 text-red-600"
                              }`}
                            >
                              {item.islem}
                            </span>
                          </td>
                          <td className="px-4 py-3.5 text-gray-400">{item.tarih}</td>
                          <td className="max-w-[200px] truncate px-4 py-3.5 text-gray-500">
                            {item.not}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
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
                  Tam Alan Karsilastirmasi - {detailGroup.id}
                </h2>
                <p className="mt-0.5 text-xs text-gray-400">
                  Splink sonucu ve sonrasindaki is kurali gerekceleri
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
                    className={`rounded-xl border-2 p-4 ${
                      index === 0
                        ? "border-gray-200"
                        : "border-red-200 bg-red-50/20"
                    }`}
                  >
                    <span
                      className={`mb-3 inline-block rounded-full px-2 py-0.5 text-[10px] font-bold ${
                        index === 0
                          ? "bg-gray-100 text-gray-600"
                          : "bg-red-100 text-red-600"
                      }`}
                    >
                      Kayit {index + 1} - {record.muhatapNo}
                    </span>
                    {[
                      ["Ad Soyad", record.adSoyad],
                      ["TC Kimlik", record.tcKimlikNo],
                      ["Telefon", record.telefon],
                      ["E-posta", record.email],
                      ["Sehir", record.sehir],
                      ["Adres", record.adres || "-"],
                    ].map(([label, value]) => (
                      <div key={label} className="mb-2">
                        <p className="text-[10px] text-gray-400">{label}</p>
                        <p className="break-words text-xs font-medium text-gray-800">
                          {value}
                        </p>
                      </div>
                    ))}
                  </div>
                ))}
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-gray-700">
                  Karar Notu (Opsiyonel)
                </label>
                <textarea
                  rows={2}
                  placeholder="Karar gerekcenizi yazin..."
                  className="w-full resize-none rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-red-400 focus:outline-none"
                  maxLength={500}
                  value={decisionNote}
                  onChange={(event) => setDecisionNote(event.target.value)}
                />
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => handleApprove(detailGroup.id)}
                  className="flex-1 cursor-pointer whitespace-nowrap rounded-lg bg-green-600 py-2.5 text-sm font-semibold text-white hover:bg-green-700"
                >
                  <i className="ri-checkbox-circle-line mr-1.5" />
                  Onayla
                </button>
                <button
                  onClick={() => handleReject(detailGroup.id)}
                  className="flex-1 cursor-pointer whitespace-nowrap rounded-lg border-2 border-red-200 py-2.5 text-sm font-semibold text-red-600 hover:bg-red-50"
                >
                  <i className="ri-close-circle-line mr-1.5" />
                  Reddet
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
