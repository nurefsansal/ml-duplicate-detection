import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import {
  downloadCleanDatasetCsv,
  downloadMuhatapMergePdf,
  getMuhatapMergeReport,
  listUploadsWithMuhatapMerge,
  type MuhatapMergeReportGroup,
  type UploadWithMergeItem,
  type DuplicateGroupRecord,
} from "../../services/api";

const reportTabs = [
  {
    id: "muhatap-merge",
    icon: "ri-git-merge-line",
    label: "Muhatap Birleştirme",
    desc: "Onaylı birleştirmeler, golden kayıt ve dahil edilmeyen kayıtlar",
  },
];

function formatUploadDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("tr-TR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function MergeTransitionBanner({ group }: { group: MuhatapMergeReportGroup }) {
  const gr = group.golden_record;
  const summary = group.merge_summary;
  const prior =
    summary?.prior_muhatap_codes ??
    gr.prior_muhatap_codes ??
    (group.muhatap_codes || []).filter((c) => c && c !== gr.clean_muhatap_no);
  const target =
    summary?.target_muhatap_code ?? gr.target_muhatap_code ?? gr.clean_muhatap_no ?? "—";
  const targetName = summary?.target_name ?? gr.clean_name ?? "—";
  const line =
    summary?.merged_muhatap_report_line ?? gr.merged_muhatap_report_line;

  return (
    <div className="mb-3 space-y-2">
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] gap-2 items-stretch">
        <div className="rounded-lg border border-gray-200 bg-white px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">
            Önceki kodlar
          </p>
          <p className="text-sm font-semibold text-gray-800 mt-0.5">
            {prior.length > 0 ? prior.join(", ") : "—"}
          </p>
        </div>
        <div className="hidden sm:flex items-center justify-center text-red-500">
          <i className="ri-arrow-right-line text-xl" />
        </div>
        <div className="rounded-lg border-2 border-red-200 bg-red-50/50 px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-red-600">
            Hedef muhatap
          </p>
          <p className="text-sm font-bold text-red-800 mt-0.5">
            {target}
            <span className="font-normal text-gray-600"> · {targetName}</span>
          </p>
        </div>
      </div>
      {line ? (
        <p className="text-xs text-gray-600 leading-relaxed">{line}</p>
      ) : null}
    </div>
  );
}

export default function Raporlar() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get("tab");
  const initialTab =
    tabFromUrl && reportTabs.some((t) => t.id === tabFromUrl)
      ? tabFromUrl
      : "muhatap-merge";
  const [selectedTab] = useState(initialTab);

  const [mergeUploads, setMergeUploads] = useState<UploadWithMergeItem[]>([]);
  const [uploadsLoading, setUploadsLoading] = useState(true);
  const [selectedUploadId, setSelectedUploadId] = useState<number | null>(null);

  const [mergeReportGroups, setMergeReportGroups] = useState<MuhatapMergeReportGroup[]>([]);
  const [mergeReportMeta, setMergeReportMeta] = useState<{
    totalAll: number;
  } | null>(null);
  const [mergeReportLoading, setMergeReportLoading] = useState(false);
  const [mergeReportError, setMergeReportError] = useState("");
  const [exporting, setExporting] = useState<"clean" | "pdf" | null>(null);
  const [error, setError] = useState("");

  const loadUploads = useCallback(async () => {
    setUploadsLoading(true);
    try {
      const res = await listUploadsWithMuhatapMerge(100);
      const uploads = res.uploads ?? [];
      setMergeUploads(uploads);

      const fromUrl = searchParams.get("upload_id");
      const parsedUrl = fromUrl ? Number(fromUrl) : NaN;
      const fromStorage = localStorage.getItem("lastDetectUploadId");
      const parsedStorage = fromStorage ? Number(fromStorage) : NaN;

      let nextId: number | null = null;
      if (Number.isFinite(parsedUrl) && uploads.some((u) => u.id === parsedUrl)) {
        nextId = parsedUrl;
      } else if (
        Number.isFinite(parsedStorage) &&
        uploads.some((u) => u.id === parsedStorage)
      ) {
        nextId = parsedStorage;
      } else if (uploads.length > 0) {
        nextId = uploads[0].id;
      }
      setSelectedUploadId(nextId);
    } catch {
      setMergeUploads([]);
      setSelectedUploadId(null);
    } finally {
      setUploadsLoading(false);
    }
  }, [searchParams]);

  const loadMergeReport = useCallback(async (uploadId: number | null) => {
    if (uploadId === null) {
      setMergeReportGroups([]);
      setMergeReportMeta(null);
      return;
    }
    setMergeReportLoading(true);
    setMergeReportError("");
    try {
      const res = await getMuhatapMergeReport({
        uploadId,
        decision: "approved",
        page: 1,
        pageSize: 500,
      });
      if (!res.success) {
        setMergeReportError(res.error || "Rapor alınamadı.");
        setMergeReportGroups([]);
        setMergeReportMeta(null);
        return;
      }
      setMergeReportGroups(res.groups || []);
      setMergeReportMeta({
        totalAll: res.count_with_merge_detail ?? res.total_all_groups ?? 0,
      });
    } catch {
      setMergeReportError("Muhatap birleştirme raporu yüklenemedi.");
      setMergeReportGroups([]);
      setMergeReportMeta(null);
    } finally {
      setMergeReportLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUploads();
  }, [loadUploads]);

  useEffect(() => {
    void loadMergeReport(selectedUploadId);
  }, [selectedUploadId, loadMergeReport]);

  const selectUpload = (raw: string) => {
    const id = Number(raw);
    if (!Number.isFinite(id) || id <= 0) return;
    setSelectedUploadId(id);
    localStorage.setItem("lastDetectUploadId", String(id));
    setSearchParams((p) => {
      p.set("upload_id", String(id));
      p.set("tab", "muhatap-merge");
      return p;
    });
  };

  const selectedUpload = mergeUploads.find((u) => u.id === selectedUploadId);

  const handleExportClean = async () => {
    if (selectedUploadId === null) return;
    setExporting("clean");
    setError("");
    try {
      await downloadCleanDatasetCsv({ uploadId: selectedUploadId });
    } catch {
      setError("Temiz veri seti indirilemedi.");
    } finally {
      setExporting(null);
    }
  };

  const handleExportPdf = async () => {
    if (selectedUploadId === null) return;
    setExporting("pdf");
    setError("");
    try {
      await downloadMuhatapMergePdf({
        uploadId: selectedUploadId,
        filename: `muhatap_birlestirme_${selectedUploadId}.pdf`,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "PDF raporu indirilemedi.");
    } finally {
      setExporting(null);
    }
  };

  return (
    <DashboardLayout>
      <Header
        title="Raporlar"
        subtitle="Muhatap birleştirme ve temiz veri seti çıktıları"
        actions={
          <button
            type="button"
            onClick={() => {
              void loadUploads();
              void loadMergeReport(selectedUploadId);
            }}
            disabled={mergeReportLoading || uploadsLoading}
            className="flex items-center gap-2 border border-gray-200 text-gray-600 text-sm px-4 py-2 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors whitespace-nowrap disabled:opacity-60"
          >
            <i
              className={
                mergeReportLoading || uploadsLoading
                  ? "ri-loader-4-line animate-spin"
                  : "ri-refresh-line"
              }
            />
            Yenile
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {error && (
          <div className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 p-4">
            <i className="ri-error-warning-fill text-red-600 text-lg" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2 space-y-5">
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">Dosya Seçimi</h3>
              {uploadsLoading ? (
                <p className="text-sm text-gray-500">
                  <i className="ri-loader-4-line animate-spin mr-2" />
                  Birleştirme yapılmış dosyalar yükleniyor…
                </p>
              ) : mergeUploads.length === 0 ? (
                <p className="text-sm text-gray-500">
                  Henüz muhatap birleştirmesi yapılmış dosya yok. Mükerrer kayıtlarda farklı
                  muhatap kodlu bir grubu onaylayıp Kaydet ile birleştirdikten sonra burada
                  görünür.
                </p>
              ) : (
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-gray-600">
                    İncelenip birleştirilmiş yükleme
                  </label>
                  <select
                    value={selectedUploadId ?? ""}
                    onChange={(e) => selectUpload(e.target.value)}
                    className="w-full min-w-[280px] cursor-pointer rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-100"
                  >
                    {mergeUploads.map((u) => (
                      <option key={u.id} value={u.id}>
                        #{u.id} — {u.file_name} ({u.merge_group_count ?? 0} birleşim,{" "}
                        {formatUploadDate(u.created_at)})
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-1">
                {reportTabs[0].label}
              </h3>
              <p className="text-xs text-gray-500 mb-4">
                Seçilen dosyadaki onaylı muhatap birleştirmeleri. Her satır tek hedef muhatap
                koduna indirgenmiş kişiyi temsil eder.
              </p>

              {mergeReportLoading ? (
                <p className="text-sm text-gray-500 py-6 text-center">
                  <i className="ri-loader-4-line animate-spin mr-2" />
                  Rapor yükleniyor…
                </p>
              ) : mergeReportError ? (
                <p className="text-sm text-red-600">{mergeReportError}</p>
              ) : selectedUploadId === null ? (
                <p className="text-sm text-gray-500 py-6">Dosya seçin.</p>
              ) : (
                <>
                  {mergeReportMeta && (
                    <p className="text-xs text-gray-600 mb-4">
                      Birleştirilmiş grup: <strong>{mergeReportMeta.totalAll}</strong>
                      {selectedUpload ? (
                        <>
                          {" "}
                          · <span className="text-gray-500">{selectedUpload.file_name}</span>
                        </>
                      ) : null}
                    </p>
                  )}
                  {mergeReportGroups.length === 0 ? (
                    <p className="text-sm text-gray-500 py-6">
                      Bu dosya için kayıtlı birleşim detayı yok.
                    </p>
                  ) : (
                    <div className="space-y-8 max-h-[640px] overflow-y-auto pr-1">
                      {mergeReportGroups.map((g) => {
                        const gr = g.golden_record as {
                          merged_member_snapshots?: Array<
                            DuplicateGroupRecord & { muhatap_no_effective?: string }
                          >;
                          excluded_member_snapshots?: Array<
                            DuplicateGroupRecord & { muhatap_no_effective?: string }
                          >;
                        };
                        const snaps = gr.merged_member_snapshots || [];
                        const excluded = gr.excluded_member_snapshots || [];
                        return (
                          <div
                            key={g.group_id}
                            className="rounded-xl border border-gray-100 bg-slate-50/60 p-4"
                          >
                            <div className="flex flex-wrap items-start justify-between gap-2 border-b border-gray-100 pb-2 mb-3">
                              <div>
                                <p className="text-sm font-semibold text-gray-900">
                                  {g.group_id}
                                </p>
                                <p className="text-[11px] text-gray-500 mt-0.5">
                                  Entity #{g.entity_id ?? "—"} · Skor %
                                  {(Number(g.group_score || 0) * 100).toFixed(1)}
                                </p>
                              </div>
                            </div>
                            <MergeTransitionBanner group={g} />
                            <p className="text-[11px] font-semibold text-gray-600 mb-2">
                              Birleşime dahil edilen kayıtlar
                            </p>
                            <div className="overflow-x-auto rounded-lg border border-gray-100 bg-white">
                              <table className="w-full min-w-[720px] text-[10px]">
                                <thead>
                                  <tr className="bg-gray-50 text-left text-gray-500">
                                    <th className="px-2 py-2">Kayıt</th>
                                    <th className="px-2 py-2">Muhatap</th>
                                    <th className="px-2 py-2">Ad</th>
                                    <th className="px-2 py-2">TC</th>
                                    <th className="px-2 py-2">Tel</th>
                                    <th className="px-2 py-2">E-posta</th>
                                    <th className="px-2 py-2">Şehir</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-50">
                                  {snaps.map((row) => (
                                    <tr key={row.record_id} className="text-gray-800">
                                      <td className="px-2 py-1.5 font-mono">{row.record_id}</td>
                                      <td className="px-2 py-1.5 font-medium">
                                        {row.muhatap_no_effective || row.clean_muhatap_no || "—"}
                                      </td>
                                      <td className="px-2 py-1.5">{row.clean_name || "—"}</td>
                                      <td className="px-2 py-1.5">{row.clean_tc || "—"}</td>
                                      <td className="px-2 py-1.5">{row.clean_phone || "—"}</td>
                                      <td className="px-2 py-1.5 break-all">
                                        {row.clean_email || "—"}
                                      </td>
                                      <td className="px-2 py-1.5">{row.clean_city || "—"}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                            {excluded.length > 0 ? (
                              <>
                                <p className="text-[11px] font-semibold text-amber-800 mb-2 mt-4">
                                  Birleşime dahil edilmeyen kayıtlar
                                </p>
                                <div className="overflow-x-auto rounded-lg border border-amber-100 bg-amber-50/40">
                                  <table className="w-full min-w-[520px] text-[10px]">
                                    <thead>
                                      <tr className="bg-amber-50/80 text-left text-amber-900">
                                        <th className="px-2 py-2">Kayıt</th>
                                        <th className="px-2 py-2">Muhatap</th>
                                        <th className="px-2 py-2">Ad</th>
                                        <th className="px-2 py-2">TC</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-amber-100/80">
                                      {excluded.map((row) => (
                                        <tr key={`ex-${row.record_id}`} className="text-gray-800">
                                          <td className="px-2 py-1.5 font-mono">
                                            {row.record_id}
                                          </td>
                                          <td className="px-2 py-1.5 font-medium">
                                            {row.muhatap_no_effective ||
                                              row.clean_muhatap_no ||
                                              "—"}
                                          </td>
                                          <td className="px-2 py-1.5">
                                            {row.clean_name || "—"}
                                          </td>
                                          <td className="px-2 py-1.5">{row.clean_tc || "—"}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="space-y-4">
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Dışa Aktarma</h3>
              <p className="text-xs text-gray-500 mb-4">
                Seçili dosya için operasyonel çıktılar. Temiz veri seti birleştirilmiş tek
                muhatap kodlu satırları içerir.
              </p>
              <div className="space-y-2">
                <button
                  type="button"
                  onClick={() => void handleExportClean()}
                  disabled={exporting !== null || selectedUploadId === null}
                  className="w-full flex items-center justify-center gap-2 bg-white text-gray-700 text-sm font-semibold py-2.5 rounded-xl border border-gray-200 hover:bg-gray-50 disabled:opacity-60 cursor-pointer"
                >
                  <i
                    className={
                      exporting === "clean" ? "ri-loader-4-line animate-spin" : "ri-file-excel-2-line"
                    }
                  />
                  Temiz veri seti (CSV)
                </button>
                <button
                  type="button"
                  onClick={() => void handleExportPdf()}
                  disabled={exporting !== null || selectedUploadId === null}
                  className="w-full flex items-center justify-center gap-2 bg-red-600 text-white text-sm font-semibold py-2.5 rounded-xl hover:bg-red-700 disabled:opacity-60 cursor-pointer"
                >
                  <i
                    className={
                      exporting === "pdf" ? "ri-loader-4-line animate-spin" : "ri-file-pdf-2-line"
                    }
                  />
                  Muhatap birleştirme (PDF)
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
