import { useEffect, useRef, useState } from "react";

import DashboardLayout from "../../components/feature/DashboardLayout";
import FieldComparisonsPanel from "../../components/feature/FieldComparisonsPanel";
import Header from "../../components/feature/Header";
import {
  approvePendingMatch,
  getPendingMatches,
  rejectPendingMatch,
} from "../../services/api";
import {
  mapPendingMatchToView,
  type PairWorkflowState,
  type UiDuplicatePair,
} from "../../utils/duplicatePairView";

type TabType = PairWorkflowState;

function formatScore(value: number): string {
  return `${value.toFixed(2)}%`;
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function workflowLabel(value: PairWorkflowState): string {
  if (value === "onaylandi") {
    return "Onaylandi";
  }
  if (value === "reddedildi") {
    return "Reddedildi";
  }
  return "Beklemede";
}

function workflowTone(value: PairWorkflowState): string {
  if (value === "onaylandi") {
    return "bg-green-50 text-green-700";
  }
  if (value === "reddedildi") {
    return "bg-red-50 text-red-600";
  }
  return "bg-yellow-50 text-yellow-700";
}

function algorithmLabel(value?: string): string {
  if (!value) {
    return "Bilinmiyor";
  }
  return value.toUpperCase();
}

function recordMeta(record: UiDuplicatePair["records"][number]): string {
  return [record.telefon, record.email, record.tcKimlikNo]
    .filter(Boolean)
    .join(" | ");
}

function pairNames(group: UiDuplicatePair): string {
  return `${group.records[0].adSoyad || "-"} / ${group.records[1].adSoyad || "-"}`;
}

function pairSearchText(group: UiDuplicatePair): string {
  return [
    String(group.backendMatchId ?? group.id),
    group.records[0].adSoyad,
    group.records[1].adSoyad,
    group.records[0].telefon,
    group.records[1].telefon,
    group.records[0].email,
    group.records[1].email,
    group.records[0].tcKimlikNo,
    group.records[1].tcKimlikNo,
  ]
    .join(" ")
    .toLowerCase();
}

export default function YoneticiOnayi() {
  const [tab, setTab] = useState<TabType>("bekleyen");
  const [detailGroup, setDetailGroup] = useState<UiDuplicatePair | null>(null);
  const [searchText, setSearchText] = useState("");
  const [loading, setLoading] = useState(false);
  const [realData, setRealData] = useState<UiDuplicatePair[]>([]);
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
        const reviewedPairs = prev.filter(
          (group) => group.workflowState !== "bekleyen",
        );
        return [...mapped, ...reviewedPairs];
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

  const data = realData;
  const bekleyen = data.filter((group) => group.workflowState === "bekleyen");
  const onaylandi = data.filter((group) => group.workflowState === "onaylandi");
  const reddedildi = data.filter((group) => group.workflowState === "reddedildi");
  const filteredHistory = (tab === "onaylandi" ? onaylandi : reddedildi).filter(
    (group) =>
      !searchText || pairSearchText(group).includes(searchText.toLowerCase()),
  );

  const updateGroup = (
    groupId: string,
    updates: Partial<UiDuplicatePair>,
  ) => {
    setRealData((prev) =>
      prev.map((group) =>
        group.id === groupId ? { ...group, ...updates } : group,
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

    try {
      const response = await approvePendingMatch({
        matchId: target.backendMatchId,
        mergeIntoEntity: true,
        canonicalName: target.records[0].adSoyad || target.records[1].adSoyad,
      });

      updateGroup(groupId, {
        workflowState: "onaylandi",
        backendDecision: response.status,
        reviewedAt: response.approved_at ?? new Date().toISOString(),
        reviewedBy: response.approved_by ?? null,
        reviewNote: decisionNote || "Kayit onaylandi.",
      });

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

    try {
      const response = await rejectPendingMatch({
        matchId: target.backendMatchId,
        reason: decisionNote || "Kayit reddedildi.",
      });

      updateGroup(groupId, {
        workflowState: "reddedildi",
        backendDecision: response.status,
        reviewedAt: response.rejected_at ?? new Date().toISOString(),
        reviewedBy: response.rejected_by ?? null,
        reviewNote: response.reason || decisionNote || "Kayit reddedildi.",
      });

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
        subtitle="Mukerrer kayit kararlarini gercek backend eslesmeleri uzerinden yonetin"
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
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <i
                className={
                  loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"
                }
              />
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
              Yonetici onayi son detect calismasi uzerinden filtreleniyor. Upload
              ID: {lastUploadId}
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
          <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
            <div className="border-b border-gray-50 px-5 py-4">
              <h3 className="text-sm font-semibold text-gray-900">Onay Bekleyen Kayitlar</h3>
              <p className="mt-0.5 text-xs text-gray-400">
                Match candidate verileri backend response alanlarindan besleniyor
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[940px] text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50/70">
                    <th className="px-5 py-3 text-left font-medium text-gray-400">Match ID</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Left Record</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Right Record</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Score</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Status</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {bekleyen.map((group) => (
                    <tr key={group.id} className="align-top transition-colors hover:bg-gray-50/50">
                      <td className="px-5 py-4">
                        <div className="font-semibold text-gray-800">
                          #{group.backendMatchId ?? group.id}
                        </div>
                        <div className="mt-1 text-xs text-gray-400">
                          {algorithmLabel(group.matchType)}
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <div className="font-medium text-gray-800">
                          {group.records[0].adSoyad || "-"}
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          {recordMeta(group.records[0]) || "-"}
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <div className="font-medium text-gray-800">
                          {group.records[1].adSoyad || "-"}
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          {recordMeta(group.records[1]) || "-"}
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <div className="font-semibold text-gray-900">
                          {formatScore(group.score)}
                        </div>
                        <div className="mt-1 text-xs text-gray-400">
                          {group.decisionReason || "Confidence / score alanindan hesaplandi"}
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <span
                          className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${workflowTone(group.workflowState)}`}
                        >
                          {workflowLabel(group.workflowState)}
                        </span>
                      </td>
                      <td className="px-4 py-4">
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => setDetailGroup(group)}
                            className="cursor-pointer rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
                          >
                            Detay
                          </button>
                          <button
                            onClick={() => handleApprove(group.id)}
                            disabled={loading}
                            className="cursor-pointer rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            Onayla
                          </button>
                          <button
                            onClick={() => handleReject(group.id)}
                            disabled={loading}
                            className="cursor-pointer rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            Reddet
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {bekleyen.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-5 py-10 text-center text-sm text-gray-400">
                        Bekleyen kayit yok.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {(tab === "onaylandi" || tab === "reddedildi") && (
          <div className="space-y-4">
            <div className="relative">
              <i className="ri-search-line absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400" />
              <input
                type="text"
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                placeholder="Match ID veya kisi adi ara..."
                className="w-full rounded-lg border border-gray-200 py-2.5 pl-9 pr-4 text-sm focus:border-red-400 focus:outline-none"
              />
            </div>

            <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[940px] text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50/70">
                      <th className="px-5 py-3 text-left font-medium text-gray-400">Match ID</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Left Record</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Right Record</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Score</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Status</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Tarih</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">Not</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {filteredHistory.map((group) => (
                      <tr key={group.id} className="align-top transition-colors hover:bg-gray-50/50">
                        <td className="px-5 py-3.5 font-medium text-gray-700">
                          #{group.backendMatchId ?? group.id}
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="font-medium text-gray-800">
                            {group.records[0].adSoyad || "-"}
                          </div>
                          <div className="mt-1 text-xs text-gray-500">
                            {recordMeta(group.records[0]) || "-"}
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="font-medium text-gray-800">
                            {group.records[1].adSoyad || "-"}
                          </div>
                          <div className="mt-1 text-xs text-gray-500">
                            {recordMeta(group.records[1]) || "-"}
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="font-semibold text-gray-900">
                            {formatScore(group.score)}
                          </div>
                          <div className="mt-1 text-xs text-gray-400">
                            {algorithmLabel(group.matchType)}
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${workflowTone(group.workflowState)}`}
                          >
                            {workflowLabel(group.workflowState)}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 text-gray-400">
                          {formatDate(group.reviewedAt)}
                        </td>
                        <td className="max-w-[240px] px-4 py-3.5 text-gray-500">
                          {group.reviewNote || "-"}
                        </td>
                      </tr>
                    ))}
                    {filteredHistory.length === 0 && (
                      <tr>
                        <td colSpan={7} className="px-5 py-10 text-center text-sm text-gray-400">
                          Bu sekmede gosterilecek kayit yok.
                        </td>
                      </tr>
                    )}
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
                  Tam Alan Karsilastirmasi - Match #{detailGroup.backendMatchId ?? detailGroup.id}
                </h2>
                <p className="mt-0.5 text-xs text-gray-400">
                  Gercek backend match verisi ve alan bazli karsilastirmalar
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
              <div className="grid grid-cols-1 gap-3 rounded-xl border border-gray-100 bg-gray-50 p-4 md:grid-cols-4">
                <div>
                  <p className="text-[11px] text-gray-400">Match ID</p>
                  <p className="text-sm font-semibold text-gray-800">
                    #{detailGroup.backendMatchId ?? detailGroup.id}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] text-gray-400">Algoritma</p>
                  <p className="text-sm font-semibold text-gray-800">
                    {algorithmLabel(detailGroup.matchType)}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] text-gray-400">Skor</p>
                  <p className="text-sm font-semibold text-gray-800">
                    {formatScore(detailGroup.score)}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] text-gray-400">Kayitlar</p>
                  <p className="text-sm font-semibold text-gray-800">
                    {pairNames(detailGroup)}
                  </p>
                </div>
              </div>

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
                      ["Muhatap Kodu", record.muhatapNo || "-"],
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
                  disabled={loading}
                  className="flex-1 cursor-pointer whitespace-nowrap rounded-lg bg-green-600 py-2.5 text-sm font-semibold text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <i className="ri-checkbox-circle-line mr-1.5" />
                  Onayla
                </button>
                <button
                  onClick={() => handleReject(detailGroup.id)}
                  disabled={loading}
                  className="flex-1 cursor-pointer whitespace-nowrap rounded-lg border-2 border-red-200 py-2.5 text-sm font-semibold text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
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
