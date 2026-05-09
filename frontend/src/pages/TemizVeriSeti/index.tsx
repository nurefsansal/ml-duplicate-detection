import { useState, useEffect, useCallback } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { FlowNav } from "../../components/feature/FlowNav";
import { useRequireUploadId } from "../../hooks/useRequireUploadId";
import {
  getNormalizedRecords,
  buildNormalizedRecordsExportUrl,
  listUploads,
  type NormalizedRecordDb,
  type UploadItem,
} from "../../services/api";

function Badge({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-green-50 text-green-700">
      <i className="ri-checkbox-circle-fill text-[10px]" /> Geçerli
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-50 text-red-600">
      <i className="ri-close-circle-fill text-[10px]" /> Geçersiz
    </span>
  );
}

function SourceBadge({ source, label }: { source?: string; label?: string }) {
  const display =
    label ||
    (source === "entity" ? "Golden Record" : "Tekil Temiz Kayıt");
  if (source === "entity") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700">
        <i className="ri-links-line text-[10px]" /> {display}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-gray-50 px-2 py-0.5 text-[11px] font-medium text-gray-600">
      <i className="ri-file-list-3-line text-[10px]" /> {display}
    </span>
  );
}

export default function TemizVeriSeti() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const uploadId = useRequireUploadId();

  const [records, setRecords] = useState<NormalizedRecordDb[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [search, setSearch] = useState("");
  const [filterValid, setFilterValid] = useState<"" | "true" | "false">("");
  const [hasMissingTc, setHasMissingTc] = useState(false);
  const [hasMissingPhone, setHasMissingPhone] = useState(false);
  const [hasMissingEmail, setHasMissingEmail] = useState(false);
  const [hasMissingCity, setHasMissingCity] = useState(false);

  const page = Number(searchParams.get("page") ?? "1");
  const pageSizeParam = searchParams.get("page_size");
  const parsedPageSize = pageSizeParam ? Number(pageSizeParam) : 50;
  const pageSize = [25, 50, 100].includes(parsedPageSize) ? parsedPageSize : 50;

  const fetchRecords = useCallback(async () => {
    if (uploadId === null) return;
    setLoading(true);
    setError("");
    try {
      const data = await getNormalizedRecords({
        upload_id: uploadId,
        is_valid: filterValid === "" ? undefined : filterValid === "true",
        search: search || undefined,
        has_missing_tc: hasMissingTc || undefined,
        has_missing_phone: hasMissingPhone || undefined,
        has_missing_email: hasMissingEmail || undefined,
        has_missing_city: hasMissingCity || undefined,
        page,
        page_size: pageSize,
      });
      setRecords(data.records ?? []);
      setTotal(data.total ?? 0);
      setTotalPages(data.total_pages ?? 1);
    } catch {
      setError("Veriler yüklenemedi. Backend bağlantısını kontrol edin.");
    } finally {
      setLoading(false);
    }
  }, [uploadId, filterValid, search, hasMissingTc, hasMissingPhone, hasMissingEmail, hasMissingCity, page, pageSize]);

  useEffect(() => {
    listUploads(50)
      .then((d) => setUploads(d.uploads ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchParams((prev) => { prev.set("page", "1"); return prev; });
    fetchRecords();
  };

  const goPage = (p: number) => {
    setSearchParams((prev) => { prev.set("page", String(p)); return prev; });
  };

  const exportUrlCsv = buildNormalizedRecordsExportUrl({
    upload_id: uploadId ?? undefined,
    format: "csv",
  });
  const exportUrlXlsx = buildNormalizedRecordsExportUrl({
    upload_id: uploadId ?? undefined,
    format: "xlsx",
  });
  const exportUrlJson = buildNormalizedRecordsExportUrl({
    upload_id: uploadId ?? undefined,
    format: "json",
  });

  if (uploadId === null) {
    return (
      <DashboardLayout>
        <Header
          title="Temiz Veri Seti"
          subtitle="Birleştirilmiş golden record + tekil temiz kayıtlar — operasyonel çıktı"
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
        title="Temiz Veri Seti"
        subtitle="Birleştirilmiş golden record + tekil temiz kayıtlar — operasyonel çıktı"
        actions={
          <div className="flex items-center gap-3">
            <a
              href={exportUrlCsv}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 border border-gray-200 text-gray-700 text-sm font-medium px-4 py-2 rounded-lg hover:bg-gray-50 transition-colors whitespace-nowrap"
            >
              <i className="ri-download-2-line"></i> CSV
            </a>
            <a
              href={exportUrlXlsx}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 border border-gray-200 text-gray-700 text-sm font-medium px-4 py-2 rounded-lg hover:bg-gray-50 transition-colors whitespace-nowrap"
            >
              <i className="ri-file-excel-2-line"></i> XLSX
            </a>
            <a
              href={exportUrlJson}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 border border-gray-200 text-gray-700 text-sm font-medium px-4 py-2 rounded-lg hover:bg-gray-50 transition-colors whitespace-nowrap"
            >
              <i className="ri-braces-line"></i> JSON
            </a>
            <button
              onClick={() => navigate(`/mukerrer-tespit?upload_id=${uploadId}`)}
              className="flex items-center gap-2 bg-red-600 text-white text-sm font-medium px-5 py-2 rounded-lg hover:bg-red-700 cursor-pointer transition-colors whitespace-nowrap"
            >
              <i className="ri-radar-line"></i> Mükerrer Tespite Git
            </button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        <FlowNav
          step="standardize"
          uploadId={uploadId}
          canGoNext={total > 0}
        />

        <div className="rounded-xl border border-green-100 bg-green-50/80 p-4 text-sm text-green-900">
          <p className="font-medium">Son kullanıma hazır veri</p>
          <p className="mt-1 text-xs text-green-800">
            Bu tablo yönetici onayı sonrası oluşan <strong>Golden Record</strong> satırlarını ve
            mükerrer olmayan <strong>Tekil Temiz Kayıt</strong> satırlarını birlikte listeler. Dışa
            aktarılan dosyalar aynı kolonları içerir (<strong>clean_muhatap_no</strong>,{" "}
            <strong>source_label</strong> dahil).
          </p>
        </div>
        {/* Stat cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="bg-white rounded-xl p-4 border border-gray-100">
            <p className="text-xs text-gray-400">Toplam Kayıt</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{total.toLocaleString("tr-TR")}</p>
          </div>
          <div className="bg-white rounded-xl p-4 border border-gray-100">
            <p className="text-xs text-gray-400">Sayfa</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{page} / {totalPages}</p>
          </div>
          <div className="bg-white rounded-xl p-4 border border-gray-100">
            <p className="text-xs text-gray-400">Seçili Upload</p>
            <p className="text-sm font-semibold text-gray-900 mt-1">
              #{uploadId}
            </p>
          </div>
        </div>

        {/* Filter bar */}
        <div className="bg-white rounded-xl p-4 border border-gray-100">
          <form onSubmit={handleSearch} className="flex flex-wrap items-end gap-3">
            {/* Upload filter */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Upload</label>
              <select
                value={uploadId}
                onChange={(e) => {
                  const v = e.target.value;
                  const nextId = Number(v);
                  if (!Number.isFinite(nextId) || nextId <= 0) return;
                  setSearchParams((p) => {
                    p.set("page", "1");
                    p.set("upload_id", String(nextId));
                    return p;
                  });
                }}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:border-red-400"
              >
                {uploads.map((u) => (
                  <option key={u.id} value={u.id}>#{u.id} — {u.file_name} ({u.total_records} kayıt)</option>
                ))}
              </select>
            </div>

            {/* Validity filter */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Geçerlilik</label>
              <select
                value={filterValid}
                onChange={(e) => { setFilterValid(e.target.value as "" | "true" | "false"); setSearchParams((p) => { p.set("page", "1"); return p; }); }}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:border-red-400"
              >
                <option value="">Tümü</option>
                <option value="true">Geçerli</option>
                <option value="false">Geçersiz</option>
              </select>
            </div>

            {/* Page size */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Önizleme</label>
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

            {/* Search */}
            <div className="flex-1 min-w-[200px]">
              <label className="block text-xs font-medium text-gray-600 mb-1">Arama</label>
              <div className="relative">
                <i className="ri-search-line absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Ad, e-posta, TC, telefon…"
                  className="w-full border border-gray-200 rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-red-400"
                />
              </div>
            </div>

            <button
              type="submit"
              className="flex items-center gap-2 bg-red-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-red-700 cursor-pointer transition-colors whitespace-nowrap"
            >
              <i className="ri-search-line"></i> Ara
            </button>

            <button
              type="button"
              onClick={fetchRecords}
              disabled={loading}
              className="flex items-center gap-1.5 border border-gray-200 text-gray-600 text-sm px-4 py-2 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors whitespace-nowrap disabled:opacity-60"
            >
              <i className={loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"}></i>
              Yenile
            </button>

            {/* Missing field filters */}
            <div className="w-full border-t border-gray-100 pt-3 flex flex-wrap gap-3">
              <p className="text-xs font-medium text-gray-500 self-center">Eksik alan:</p>
              {[
                { label: "TC", state: hasMissingTc, set: setHasMissingTc },
                { label: "Telefon", state: hasMissingPhone, set: setHasMissingPhone },
                { label: "E-posta", state: hasMissingEmail, set: setHasMissingEmail },
                { label: "Şehir", state: hasMissingCity, set: setHasMissingCity },
              ].map(({ label, state, set }) => (
                <label key={label} className="flex items-center gap-1.5 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={state}
                    onChange={(e) => {
                      set(e.target.checked);
                      setSearchParams((p) => { p.set("page", "1"); return p; });
                    }}
                    className="accent-red-600 cursor-pointer"
                  />
                  <span className="text-xs text-gray-600">{label} eksik</span>
                </label>
              ))}
            </div>
          </form>
        </div>

        {error && (
          <div className="rounded-xl border border-red-100 bg-red-50 p-4 flex items-center gap-3">
            <i className="ri-error-warning-fill text-red-600 text-lg" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Table */}
        <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50/70 border-b border-gray-100">
                  <th className="px-4 py-3 text-left font-medium text-gray-400">ID</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Ad Soyad</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">E-posta</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Telefon</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">TC</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Şehir</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Muhatap No</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Upload</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Kaynak türü</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">Durum</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {loading ? (
                  <tr>
                    <td colSpan={10} className="px-5 py-10 text-center text-gray-400">
                      <i className="ri-loader-4-line animate-spin text-xl block mb-2" />
                      Yükleniyor…
                    </td>
                  </tr>
                ) : records.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="px-5 py-10 text-center text-gray-400">
                      Kayıt bulunamadı.
                      {total === 0 && " Önce Veri Yükleme veya Veri Standardizasyon adımını tamamlayın."}
                    </td>
                  </tr>
                ) : (
                  records.map((r) => (
                    <tr key={`${r.source ?? "normalized_record"}-${r.id}`} className="hover:bg-gray-50/50 transition-colors">
                      <td className="px-4 py-3 text-gray-500 font-mono">
                        {r.source === "entity" ? `E#${r.entity_id ?? r.id}` : `#${r.id}`}
                      </td>
                      <td className="px-4 py-3 font-medium text-gray-800">{r.clean_name || "-"}</td>
                      <td className="px-4 py-3 text-gray-600">{r.clean_email || "-"}</td>
                      <td className="px-4 py-3 text-gray-600">{r.clean_phone || "-"}</td>
                      <td className="px-4 py-3 text-gray-600 font-mono">{r.clean_tc || "-"}</td>
                      <td className="px-4 py-3 text-gray-600">{r.clean_city || "-"}</td>
                      <td className="px-4 py-3 text-gray-600 font-mono">{r.clean_muhatap_no || "-"}</td>
                      <td className="px-4 py-3 text-gray-400">#{r.upload_id}</td>
                      <td className="px-4 py-3">
                        <SourceBadge source={r.source} label={r.source_label} />
                      </td>
                      <td className="px-4 py-3"><Badge ok={r.is_valid} /></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-5 py-3 border-t border-gray-50 bg-gray-50/30">
              <p className="text-xs text-gray-500">
                Toplam <strong>{total.toLocaleString("tr-TR")}</strong> kayıt · Sayfa {page} / {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => goPage(page - 1)}
                  disabled={page <= 1}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50 cursor-pointer transition-colors"
                >
                  <i className="ri-arrow-left-s-line" /> Önceki
                </button>
                <button
                  onClick={() => goPage(page + 1)}
                  disabled={page >= totalPages}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50 cursor-pointer transition-colors"
                >
                  Sonraki <i className="ri-arrow-right-s-line" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
