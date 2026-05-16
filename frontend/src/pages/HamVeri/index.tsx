import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { FlowNav } from "../../components/feature/FlowNav";
import { useRequireUploadId } from "../../hooks/useRequireUploadId";
import {
  getRawRecords,
  getUploadColumns,
  listUploads,
  type RawRecordItem,
  type UploadItem,
} from "../../services/api";
import { formatUploadIdWithDate } from "../../utils/formatUploadDate";

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
  const [uploadMeta, setUploadMeta] = useState<UploadItem | null>(null);

  const visibleColumns = useMemo(() => columns.slice(0, 25), [columns]);

  useEffect(() => {
    if (requiredId === null) return;
    listUploads(50)
      .then((d) => {
        const found = (d.uploads ?? []).find((u) => u.id === requiredId) ?? null;
        setUploadMeta(found);
      })
      .catch(() => setUploadMeta(null));
  }, [requiredId]);

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
      setError("Veriler yüklenemedi. Lütfen bağlantıyı kontrol edip tekrar deneyin.");
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
          title="Yüklenen Veri"
          subtitle="Yüklediğiniz dosyanın ilk hali — sayfalı önizleme"
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
        title="Yüklenen Veri"
        subtitle="Yüklediğiniz dosyanın ilk hali — sayfalı önizleme"
      />

      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        <FlowNav step="upload" uploadId={uploadId} />

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-gray-100 bg-white p-4">
            <p className="text-xs text-gray-400">Yükleme No</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {formatUploadIdWithDate(uploadId, uploadMeta?.created_at)}
            </p>
          </div>
          <div className="rounded-xl border border-gray-100 bg-white p-4">
            <p className="text-xs text-gray-400">Toplam Kayıt</p>
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
        </div>

        <div className="flex flex-wrap items-end gap-3 rounded-xl border border-gray-100 bg-white p-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">
              Sayfada Göster
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
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-red-400 focus:outline-none"
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>

          <div className="text-xs text-gray-500">
            Görünen alan sayısı: <strong>{visibleColumns.length}</strong> /{" "}
            <strong>{columns.length}</strong>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
          <div className="overflow-auto">
            <table className="min-w-[900px] w-full text-sm">
              <thead className="bg-gray-50">
                <tr className="text-left text-xs text-gray-500">
                  <th className="whitespace-nowrap px-4 py-3">#</th>
                  {visibleColumns.map((c) => (
                    <th
                      key={c}
                      className="whitespace-nowrap px-4 py-3 font-medium"
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
                      Veriler yükleniyor…
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
                      <td className="whitespace-nowrap px-4 py-2 text-xs text-gray-400">
                        {r.row_index ?? idx + 1}
                      </td>
                      {visibleColumns.map((c) => (
                        <td
                          key={`${r.id}-${c}`}
                          className="whitespace-nowrap px-4 py-2 text-gray-800"
                        >
                          {String((r.raw_payload as Record<string, unknown>)?.[c] ?? "")}
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
      </div>
    </DashboardLayout>
  );
}
