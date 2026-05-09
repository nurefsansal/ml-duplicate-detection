import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { FlowNav } from "../../components/feature/FlowNav";
import { useRequireUploadId } from "../../hooks/useRequireUploadId";
import {
  getRawRecords,
  getUploadColumns,
  type RawRecordItem,
} from "../../services/api";

export default function HamVeri() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requiredId = useRequireUploadId();
  const uploadId = requiredId ?? 0;
  const page = Number(searchParams.get("page") ?? "1");
  const pageSizeParam = searchParams.get("page_size");
  const parsedPageSize = pageSizeParam ? Number(pageSizeParam) : 50;
  const pageSize = [25, 50, 100].includes(parsedPageSize) ? parsedPageSize : 50;

  const [columns, setColumns] = useState<string[]>([]);
  const [records, setRecords] = useState<RawRecordItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const visibleColumns = useMemo(() => columns.slice(0, 25), [columns]);

  const fetchData = useCallback(async () => {
    if (requiredId === null || !Number.isFinite(uploadId) || uploadId <= 0) return;
    setLoading(true);
    setError("");
    try {
      const [colsResp, listResp] = await Promise.all([
        getUploadColumns(uploadId),
        getRawRecords({ upload_id: uploadId, page, page_size: pageSize }),
      ]);
      setColumns(colsResp.source_columns ?? []);
      setRecords(listResp.records ?? []);
      setTotal(listResp.total ?? 0);
      setTotalPages(listResp.total_pages ?? 1);
    } catch {
      setError("Ham veriler yüklenemedi. Backend bağlantısını kontrol edin.");
    } finally {
      setLoading(false);
    }
  }, [requiredId, uploadId, page, pageSize]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const goPage = (p: number) => {
    setSearchParams((prev) => {
      prev.set("page", String(p));
      return prev;
    });
  };

  if (requiredId === null) {
    return (
      <DashboardLayout>
        <Header
          title="Ham Veri"
          subtitle="Yüklenen dosyanın ham satırları (raw_records) — sayfalı önizleme"
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
        title="Ham Veri"
        subtitle="Yüklenen dosyanın ham satırları (raw_records) — sayfalı önizleme"
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <FlowNav step="upload" uploadId={uploadId} />

        <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="bg-white rounded-xl p-4 border border-gray-100">
                <p className="text-xs text-gray-400">Upload ID</p>
                <p className="text-lg font-bold text-gray-900 mt-1">
                  #{uploadId}
                </p>
              </div>
              <div className="bg-white rounded-xl p-4 border border-gray-100">
                <p className="text-xs text-gray-400">Toplam Satır</p>
                <p className="text-lg font-bold text-gray-900 mt-1">
                  {total.toLocaleString("tr-TR")}
                </p>
              </div>
              <div className="bg-white rounded-xl p-4 border border-gray-100">
                <p className="text-xs text-gray-400">Sayfa</p>
                <p className="text-lg font-bold text-gray-900 mt-1">
                  {page} / {totalPages}
                </p>
              </div>
            </div>

            <div className="bg-white rounded-xl p-4 border border-gray-100 flex flex-wrap items-end gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Önizleme
                </label>
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
                  className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:border-red-400"
                >
                  <option value="25">25</option>
                  <option value="50">50</option>
                  <option value="100">100</option>
                </select>
              </div>

              <div className="text-xs text-gray-500">
                Görüntülenen kolon sayısı:{" "}
                <strong>{visibleColumns.length}</strong> /{" "}
                <strong>{columns.length}</strong>
              </div>
            </div>

            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
              <div className="overflow-auto">
                <table className="min-w-[900px] w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr className="text-left text-xs text-gray-500">
                      <th className="px-4 py-3 whitespace-nowrap">#</th>
                      {visibleColumns.map((c) => (
                        <th
                          key={c}
                          className="px-4 py-3 whitespace-nowrap font-medium"
                        >
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {loading ? (
                      <tr>
                        <td
                          className="px-4 py-6 text-gray-500"
                          colSpan={1 + visibleColumns.length}
                        >
                          Yükleniyor…
                        </td>
                      </tr>
                    ) : records.length === 0 ? (
                      <tr>
                        <td
                          className="px-4 py-6 text-gray-500"
                          colSpan={1 + visibleColumns.length}
                        >
                          Kayıt bulunamadı.
                        </td>
                      </tr>
                    ) : (
                      records.map((r, idx) => (
                        <tr key={r.id} className="hover:bg-gray-50/50">
                          <td className="px-4 py-2 text-xs text-gray-400 whitespace-nowrap">
                            {r.row_index ?? idx + 1}
                          </td>
                          {visibleColumns.map((c) => (
                            <td
                              key={`${r.id}-${c}`}
                              className="px-4 py-2 text-gray-800 whitespace-nowrap"
                            >
                              {String(
                                (r.raw_payload as Record<string, unknown>)?.[c] ??
                                  "",
                              )}
                            </td>
                          ))}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <button
                disabled={page <= 1}
                onClick={() => goPage(Math.max(1, page - 1))}
                className="px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-700 disabled:opacity-50"
              >
                Önceki
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => goPage(Math.min(totalPages, page + 1))}
                className="px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-700 disabled:opacity-50"
              >
                Sonraki
              </button>
            </div>
          </>
      </div>
    </DashboardLayout>
  );
}

