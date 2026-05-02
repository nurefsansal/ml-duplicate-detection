import { useEffect, useMemo, useRef, useState } from "react";

import DashboardLayout from "../../components/feature/DashboardLayout";
import FieldComparisonsPanel from "../../components/feature/FieldComparisonsPanel";
import Header from "../../components/feature/Header";
import {
  approvePendingMatch,
  getMatches,
  rejectPendingMatch,
} from "../../services/api";
import {
  finalDecisionLabel,
  finalDecisionTone,
  mapPendingMatchToView,
  type UiDuplicatePair,
} from "../../utils/duplicatePairView";

function formatScore(value: number): string {
  return `${value.toFixed(2)}%`;
}

function algorithmLabel(value?: string): string {
  return value ? value.toUpperCase() : "Bilinmiyor";
}

function recordMeta(record: UiDuplicatePair["records"][number]): string {
  return [record.telefon, record.email, record.tcKimlikNo]
    .filter(Boolean)
    .join(" | ");
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
  const [activeDecision, setActiveDecision] = useState<
    "pending" | "approved" | "rejected"
  >("pending");
  const [detailGroup, setDetailGroup] = useState<UiDuplicatePair | null>(null);
  const [searchText, setSearchText] = useState("");
  const [loading, setLoading] = useState(false);
  const [matches, setMatches] = useState<UiDuplicatePair[]>([]);
  const [decisionCounts, setDecisionCounts] = useState({
    pending: 0,
    approved: 0,
    rejected: 0,
  });
  const [decisionNote, setDecisionNote] = useState("");
  const [apiError, setApiError] = useState("");
  const [lastUploadId, setLastUploadId] = useState<number | null>(null);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const isMountedRef = useRef(true);

  const refreshMatches = async (
    uploadId: number | undefined,
    decision: "pending" | "approved" | "rejected",
  ) => {
    setLoading(true);
    setApiError("");

    try {
      const response = await getMatches({
        decision,
        uploadId,
        limit: 100,
      });

      if (!isMountedRef.current) {
        return;
      }

      setMatches((response.matches || []).map(mapPendingMatchToView));
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }
      setApiError(
        error instanceof Error
          ? error.message
          : "Kayıtlar alınamadı.",
      );
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  const refreshDecisionCounts = async (uploadId: number | undefined) => {
    try {
      const [pendingRes, approvedRes, rejectedRes] = await Promise.all([
        getMatches({ decision: "pending", uploadId, limit: 1_000_000 }),
        getMatches({ decision: "approved", uploadId, limit: 1_000_000 }),
        getMatches({ decision: "rejected", uploadId, limit: 1_000_000 }),
      ]);
      if (!isMountedRef.current) {
        return;
      }
      setDecisionCounts({
        pending: pendingRes.count ?? 0,
        approved: approvedRes.count ?? 0,
        rejected: rejectedRes.count ?? 0,
      });
    } catch {
      if (isMountedRef.current) {
        setDecisionCounts({ pending: 0, approved: 0, rejected: 0 });
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
        refreshMatches(uploadId, "pending");
        refreshDecisionCounts(uploadId);
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

  useEffect(() => {
    if (backendHealthy === false) {
      return;
    }
    refreshMatches(lastUploadId ?? undefined, activeDecision);
  }, [activeDecision]);

  const filteredMatches = useMemo(
    () =>
      matches.filter(
        (group) =>
          !searchText ||
          pairSearchText(group).includes(searchText.toLowerCase()),
      ),
    [matches, searchText],
  );

  const handleApprove = async (groupId: string) => {
    const target = matches.find((group) => group.id === groupId);
    if (!target?.backendMatchId) {
      return;
    }

    setLoading(true);
    setApiError("");

    try {
      await approvePendingMatch({
        matchId: target.backendMatchId,
        mergeIntoEntity: true,
        canonicalName: target.records[0].adSoyad || target.records[1].adSoyad,
      });

      setMatches((prev) => prev.filter((group) => group.id !== groupId));
      setDetailGroup(null);
      setDecisionNote("");
      await Promise.all([
        refreshMatches(lastUploadId ?? undefined, activeDecision),
        refreshDecisionCounts(lastUploadId ?? undefined),
      ]);
    } catch (error) {
      setApiError(
        error instanceof Error ? error.message : "Onay işlemi başarısız.",
      );
      setLoading(false);
    }
  };

  const handleReject = async (groupId: string) => {
    const target = matches.find((group) => group.id === groupId);
    if (!target?.backendMatchId) {
      return;
    }

    setLoading(true);
    setApiError("");

    try {
      await rejectPendingMatch({
        matchId: target.backendMatchId,
        reason: decisionNote || "Kayıt reddedildi.",
      });

      setMatches((prev) => prev.filter((group) => group.id !== groupId));
      setDetailGroup(null);
      setDecisionNote("");
      await Promise.all([
        refreshMatches(lastUploadId ?? undefined, activeDecision),
        refreshDecisionCounts(lastUploadId ?? undefined),
      ]);
    } catch (error) {
      setApiError(
        error instanceof Error ? error.message : "Reddetme işlemi başarısız.",
      );
      setLoading(false);
    }
  };

  const refreshLabel = lastUploadId
    ? `Yenile (Upload ${lastUploadId})`
    : "Tümünü Yenile";
  const canTakeAction = activeDecision === "pending";

  return (
    <DashboardLayout>
      <Header
        title="Yönetici Onayı"
        subtitle="Bekleyen eşleşmeleri doğrudan backend API verileri üzerinden yönetin"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="rounded bg-red-50 px-2 py-1 text-xs text-red-600">
                Backend: Erişilemiyor
              </span>
            )}
            <button
              onClick={() =>
                Promise.all([
                  refreshMatches(lastUploadId ?? undefined, activeDecision),
                  refreshDecisionCounts(lastUploadId ?? undefined),
                ])
              }
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
              Liste son detect çalışmasındaki upload için filtreleniyor. Upload
              ID: {lastUploadId}
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setActiveDecision("pending")}
            className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
              activeDecision === "pending"
                ? "bg-yellow-500 text-white"
                : "border border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
          >
            Bekleyen: {decisionCounts.pending}
          </button>
          <button
            onClick={() => setActiveDecision("approved")}
            className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
              activeDecision === "approved"
                ? "bg-green-600 text-white"
                : "border border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
          >
            Onaylanan: {decisionCounts.approved}
          </button>
          <button
            onClick={() => setActiveDecision("rejected")}
            className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
              activeDecision === "rejected"
                ? "bg-red-600 text-white"
                : "border border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
          >
            Reddedilen: {decisionCounts.rejected}
          </button>
        </div>

        {apiError && (
          <div className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 p-4">
            <i className="ri-error-warning-fill text-lg text-red-600" />
            <p className="text-sm text-red-700">{apiError}</p>
          </div>
        )}

        {loading && (
          <div className="flex items-center gap-3 rounded-xl border border-blue-100 bg-blue-50 p-4">
            <i className="ri-loader-4-line animate-spin text-lg text-blue-600" />
            <p className="text-sm text-blue-700">Backend verileri yükleniyor...</p>
          </div>
        )}

        <div className="relative">
          <i className="ri-search-line absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400" />
          <input
            type="text"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="Match ID veya kişi adı ara..."
            className="w-full rounded-lg border border-gray-200 py-2.5 pl-9 pr-4 text-sm focus:border-red-400 focus:outline-none"
          />
        </div>

        <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
          <div className="border-b border-gray-50 px-5 py-4">
            <h3 className="text-sm font-semibold text-gray-900">
              Eşleşme Kayıtları
            </h3>
            <p className="mt-0.5 text-xs text-gray-400">
              Bu liste backend API&apos;dan gelen{" "}
              {activeDecision === "pending"
                ? "bekleyen"
                : activeDecision === "approved"
                  ? "onaylanan"
                  : "reddedilen"}{" "}
              eşleşmeleri gösterir.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[940px] text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/70">
                  <th className="px-5 py-3 text-left font-medium text-gray-400">
                    Match ID
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">
                    Left Record
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">
                    Right Record
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">
                    Score
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">
                    Durum
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filteredMatches.map((group) => (
                  <tr
                    key={group.id}
                    className="align-top transition-colors hover:bg-gray-50/50"
                  >
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
                        {group.decisionReason ||
                          "Confidence / score alanından hesaplandı"}
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <span
                        className={`inline-block rounded-full px-2.5 py-1 text-[11px] font-medium ${finalDecisionTone(
                          group.backendDecision || group.finalDecision,
                        )}`}
                      >
                        {finalDecisionLabel(
                          group.backendDecision || group.finalDecision,
                        )}
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
                        {canTakeAction ? (
                          <>
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
                          </>
                        ) : (
                          <span className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-500">
                            İşlem yok
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {filteredMatches.length === 0 && !loading && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-5 py-10 text-center text-sm text-gray-400"
                    >
                      Bu filtre için kayıt yok.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
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
                  Tam Alan Karşılaştırması - Match #
                  {detailGroup.backendMatchId ?? detailGroup.id}
                </h2>
                <p className="mt-0.5 text-xs text-gray-400">
                  Gerçek backend match verisi ve alan bazlı karşılaştırmalar
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
                  <p className="text-[11px] text-gray-400">Kayıtlar</p>
                  <p className="text-sm font-semibold text-gray-800">
                    {detailGroup.records[0].adSoyad || "-"} /{" "}
                    {detailGroup.records[1].adSoyad || "-"}
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
                    key={`${detailGroup.id}-${index}-${record.muhatapNo}`}
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
                      Kayıt {index + 1} - {record.muhatapNo}
                    </span>
                    {[
                      ["Ad Soyad", record.adSoyad],
                      ["TC Kimlik", record.tcKimlikNo],
                      ["Telefon", record.telefon],
                      ["E-posta", record.email],
                      ["Şehir", record.sehir],
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
                  placeholder="Karar gerekçenizi yazın..."
                  className="w-full resize-none rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-red-400 focus:outline-none"
                  maxLength={500}
                  value={decisionNote}
                  onChange={(event) => setDecisionNote(event.target.value)}
                />
              </div>

              {canTakeAction && (
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
              )}
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
