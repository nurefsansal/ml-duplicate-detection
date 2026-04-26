import { useEffect, useState } from "react";
import { listUploads, type UploadItem } from "../../../services/api";

const sourceIcon: Record<string, string> = {
  excel: "ri-file-excel-2-line",
  csv: "ri-file-text-line",
  api: "ri-code-s-slash-line",
  unknown: "ri-file-line",
};

function statusBadge(status: string) {
  if (status === "completed")
    return { label: "Tamamlandı", cls: "bg-green-50 text-green-700", icon: "ri-checkbox-circle-fill" };
  if (status === "failed" || status === "error")
    return { label: "Hata", cls: "bg-red-50 text-red-600", icon: "ri-error-warning-fill" };
  return { label: "İşleniyor", cls: "bg-yellow-50 text-yellow-700", icon: "ri-loader-4-line" };
}

function formatDate(iso: string | null): string {
  if (!iso) return "-";
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

export default function UploadHistoryTable() {
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchUploads = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listUploads(30);
      setUploads(data.uploads ?? []);
    } catch {
      setError("Yükleme geçmişi alınamadı.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUploads(); }, []);

  return (
    <div className="bg-white rounded-xl border border-gray-100">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-50">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Yükleme Geçmişi</h3>
          <p className="text-xs text-gray-500 mt-0.5">Son 30 yükleme işlemi</p>
        </div>
        <button
          onClick={fetchUploads}
          disabled={loading}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 bg-gray-50 hover:bg-gray-100 px-3 py-1.5 rounded-lg cursor-pointer transition-colors whitespace-nowrap disabled:opacity-60"
        >
          <i className={`${loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"} text-sm`}></i>
          Yenile
        </button>
      </div>

      {error && (
        <div className="px-5 py-3 text-xs text-red-600 bg-red-50 border-b border-red-100">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50/70">
              <th className="text-left text-gray-400 font-medium px-5 py-3">Dosya Adı</th>
              <th className="text-left text-gray-400 font-medium px-4 py-3">Kaynak</th>
              <th className="text-right text-gray-400 font-medium px-4 py-3">Kayıt</th>
              <th className="text-left text-gray-400 font-medium px-4 py-3">Tarih</th>
              <th className="text-left text-gray-400 font-medium px-4 py-3">Aşama</th>
              <th className="text-left text-gray-400 font-medium px-4 py-3">Durum</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {uploads.length === 0 && !loading ? (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-gray-400">
                  Henüz yükleme yok.
                </td>
              </tr>
            ) : (
              uploads.map((item) => {
                const badge = statusBadge(item.status);
                const icon = sourceIcon[item.source_type?.toLowerCase()] ?? "ri-file-line";
                return (
                  <tr key={item.id} className="hover:bg-gray-50/50 transition-colors">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <i className={`${icon} text-gray-400 text-base`}></i>
                        <span className="text-gray-800 font-medium truncate max-w-[180px]">
                          {item.file_name}
                        </span>
                        <span className="text-gray-400 ml-1">#{item.id}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-gray-500 capitalize">{item.source_type}</td>
                    <td className="px-4 py-3.5 text-right font-medium text-gray-700">
                      {(item.total_records ?? 0).toLocaleString("tr-TR")}
                    </td>
                    <td className="px-4 py-3.5 text-gray-500">{formatDate(item.created_at)}</td>
                    <td className="px-4 py-3.5 text-gray-400">{item.processing_stage ?? "-"}</td>
                    <td className="px-4 py-3.5">
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium ${badge.cls}`}>
                        <i className={`${badge.icon} text-xs`}></i>
                        {badge.label}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
