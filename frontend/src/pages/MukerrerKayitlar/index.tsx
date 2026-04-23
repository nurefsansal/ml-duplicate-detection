import { useEffect, useRef, useState } from "react";

import DashboardLayout from "../../components/feature/DashboardLayout";
import FieldComparisonsPanel from "../../components/feature/FieldComparisonsPanel";
import Header from "../../components/feature/Header";
import { mockDuplicateGroups } from "../../mocks/records";
import { detectDuplicatesFromFileWithOptions } from "../../services/api";
import {
  finalDecisionTone,
  mapDetectPairToView,
  mapMockGroupToView,
  type PairWorkflowState,
  type UiDuplicatePair,
} from "../../utils/duplicatePairView";

export default function MukerrerKayitlar() {
  const [search, setSearch] = useState("");
  const [filterDecision, setFilterDecision] = useState("tumu");
  const [selected, setSelected] = useState<string[]>([]);
  const [detailGroup, setDetailGroup] = useState<UiDuplicatePair | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [realData, setRealData] = useState<UiDuplicatePair[]>([]);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let mounted = true;
    import("../../services/api")
      .then(({ healthCheck }) => healthCheck())
      .then(() => {
        if (mounted) {
          setBackendHealthy(true);
        }
      })
      .catch(() => {
        if (mounted) {
          setBackendHealthy(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      loadDataFromFile(file);
    }
  };

  const loadDataFromFile = async (file: File) => {
    setLoading(true);
    try {
      const result = await detectDuplicatesFromFileWithOptions(file, {
        minRulesToMatch: 2,
        saveToDb: true,
      });

      if (typeof result.uploadId === "number") {
        localStorage.setItem("lastDetectUploadId", String(result.uploadId));
      }

      setRealData((result.duplicates || []).map(mapDetectPairToView));
    } catch (error) {
      console.error("Error loading data:", error);
    } finally {
      setLoading(false);
    }
  };

  const data = realData.length > 0 ? realData : mockDuplicateGroups.map(mapMockGroupToView);

  const filtered = data.filter((group) => {
    const matchSearch =
      !search ||
      group.records.some(
        (record) =>
          record.adSoyad.toLowerCase().includes(search.toLowerCase()) ||
          record.muhatapNo.toLowerCase().includes(search.toLowerCase()) ||
          record.tcKimlikNo.includes(search),
      );

    const matchDecision =
      filterDecision === "tumu" || group.workflowState === filterDecision;

    return matchSearch && matchDecision;
  });

  const toggleSelect = (id: string) =>
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id],
    );

  const toggleAll = () =>
    setSelected(selected.length === filtered.length ? [] : filtered.map((group) => group.id));

  const updateWorkflowState = (ids: string[], workflowState: PairWorkflowState) => {
    setRealData((prev) =>
      prev.map((group) =>
        ids.includes(group.id) ? { ...group, workflowState } : group,
      ),
    );
  };

  const decisionBadge: Record<PairWorkflowState, string> = {
    bekleyen: "border border-yellow-200 bg-yellow-50 text-yellow-700",
    onaylandi: "border border-green-200 bg-green-50 text-green-700",
    reddedildi: "border border-red-200 bg-red-50 text-red-600",
  };

  const decisionLabel: Record<PairWorkflowState | "tumu", string> = {
    tumu: "Tumu",
    bekleyen: "Bekleyen",
    onaylandi: "Onaylandi",
    reddedildi: "Reddedildi",
  };

  return (
    <DashboardLayout>
      <Header
        title="Mukerrer Kayitlar"
        subtitle="Tespit edilen mukerrer kayitlari alan bazli skorlarla yonetin"
        actions={
          <div className="flex items-center gap-3">
            {backendHealthy === false && (
              <span className="rounded bg-red-50 px-2 py-1 text-xs text-red-600">
                Backend: Erisilemiyor
              </span>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={handleFileSelect}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50"
            >
              <i className="ri-folder-open-line" />
              {selectedFile ? selectedFile.name : "Veri Yukle"}
            </button>
            {selected.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">{selected.length} secildi</span>
                <button
                  onClick={() => {
                    updateWorkflowState(selected, "onaylandi");
                    setSelected([]);
                  }}
                  className="flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg bg-green-600 px-3 py-2 text-xs text-white hover:bg-green-700"
                >
                  <i className="ri-checkbox-circle-line" /> Toplu Onayla
                </button>
                <button
                  onClick={() => {
                    updateWorkflowState(selected, "reddedildi");
                    setSelected([]);
                  }}
                  className="flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg bg-red-600 px-3 py-2 text-xs text-white hover:bg-red-700"
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
            <p className="text-sm text-blue-700">Veriler yukleniyor...</p>
          </div>
        )}

        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
          <div className="relative w-full flex-1">
            <i className="ri-search-line absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Ad soyad, muhatap no veya TC ile ara..."
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
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Kayit 1</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Kayit 2</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Telefon / E-posta</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Karar</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-400">Islem</th>
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
                      className={`transition-colors hover:bg-gray-50/50 ${
                        selected.includes(group.id) ? "bg-red-50/30" : ""
                      }`}
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
                        <span
                          className={`inline-block rounded-full px-2.5 py-1 text-sm font-bold ${scoreColor}`}
                        >
                          %{group.score.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-4 py-3.5">
                        <p className="font-medium text-gray-800">{group.records[0].adSoyad}</p>
                        <p className="text-gray-400">
                          {group.records[0].tcKimlikNo || "-"} - {group.records[0].muhatapNo}
                        </p>
                      </td>
                      <td className="px-4 py-3.5">
                        <p className="font-medium text-gray-800">{group.records[1].adSoyad}</p>
                        <p className="text-gray-400">
                          {group.records[1].tcKimlikNo || "-"} - {group.records[1].muhatapNo}
                        </p>
                      </td>
                      <td className="px-4 py-3.5 text-gray-500">
                        <p>{group.records[0].telefon || "-"}</p>
                        <p className="mt-1">{group.records[0].email || "-"}</p>
                      </td>
                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-block rounded-full px-2.5 py-1 text-[11px] font-medium ${finalDecisionTone(group.finalDecision)}`}
                        >
                          {group.finalDecisionLabel}
                        </span>
                        <div className="mt-2">
                          <span
                            className={`inline-block rounded-full px-2.5 py-1 text-[11px] font-medium ${decisionBadge[group.workflowState]}`}
                          >
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
            {filtered.length === 0 && (
              <div className="py-10 text-center text-sm text-gray-400">
                Kayit bulunamadi.
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
                  Kayit Karsilastirma - {detailGroup.id}
                </h2>
                <p className="mt-0.5 text-xs text-gray-400">
                  Splink alan karsilastirmalari ve kural gerekceleri
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
                    className={`rounded-xl border-2 p-4 ${
                      index === 0
                        ? "border-gray-200"
                        : "border-red-200 bg-red-50/20"
                    }`}
                  >
                    <div className="mb-3 flex items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          index === 0
                            ? "bg-gray-100 text-gray-600"
                            : "bg-red-100 text-red-600"
                        }`}
                      >
                        Kayit {index + 1}
                      </span>
                      <span className="text-xs text-gray-500">{record.muhatapNo}</span>
                    </div>
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

              <div className="flex gap-3">
                <button
                  onClick={() => {
                    updateWorkflowState([detailGroup.id], "onaylandi");
                    setDetailGroup(null);
                  }}
                  className="flex-1 cursor-pointer whitespace-nowrap rounded-lg bg-green-600 py-2.5 text-sm font-medium text-white hover:bg-green-700"
                >
                  <i className="ri-checkbox-circle-line mr-1.5" />
                  Mukerrer Onayla
                </button>
                <button
                  onClick={() => {
                    updateWorkflowState([detailGroup.id], "reddedildi");
                    setDetailGroup(null);
                  }}
                  className="flex-1 cursor-pointer whitespace-nowrap rounded-lg border border-red-200 py-2.5 text-sm font-medium text-red-600 hover:bg-red-50"
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
