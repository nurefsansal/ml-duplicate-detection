import { useEffect, useState } from "react";
import { listUploads, type UploadItem } from "../../../services/api";

const sourceIcon: Record<string, string> = {
  excel: "ri-file-excel-2-line",
  csv: "ri-file-text-line",
  api: "ri-code-s-slash-line",
  unknown: "ri-file-line",
};

function sourceLabel(source: string | null | undefined): string {
  const value = (source || "").toLowerCase();
  if (value === "excel") return "Excel";
  if (value === "csv") return "CSV";
  if (value === "api") return "API";
  if (value === "institution") return "Kurum Veritabanı";
  if (value === "manuel") return "Elle Giriş";
  return source || "-";
}

function stageLabel(stage: string | null | undefined): string {
  const value = (stage || "").toLowerCase();
  if (!value) return "-";
  if (value.includes("normalize")) return "Standardize edildi";
  if (value.includes("detect")) return "Benzer kayıt tarandı";
  if (value.includes("review")) return "İnceleme bekliyor";
  if (value.includes("export")) return "Hazır veri oluşturuldu";
  if (value.includes("upload")) return "Dosya yüklendi";
  return stage || "-";
}

function statusBadge(status: string) {
  if (status === "completed") {
    return { label: "Tamamlandı", cls: "bg-green-50 text-green-700", icon: "ri-checkbox-circle-fill" };
  }
  if (status === "failed" || status === "error") {
    return { label: "Hata", cls: "bg-red-50 text-red-600", icon: "ri-error-warning-fill" };
  }
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

  useEffect(() => {
    fetchUploads();
  }, []);

  return (
    <div className="rounded-xl border border-gray-100 bg-white">
      <div className="flex items-center justify-between border-b border-gray-50 px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Son Yüklemeler</h3>
          <p className="mt-0.5 text-xs text-gray-500">En son eklenen 30 dosya</p>
        </div>
        <button
          onClick={fetchUploads}
          disabled={loading}
          className="flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg bg-gray-50 px-3 py-1.5 text-xs text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 disabled:opacity-60"
        >
          <i className={`${loading ? "ri-loader-4-line animate-spin" : "ri-refresh-line"} text-sm`} />
          Yenile
        </button>
      </div>

      {error && (
        <div className="border-b border-red-100 bg-red-50 px-5 py-3 text-xs text-red-600">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50/70">
              <th className="px-5 py-3 text-left font-medium text-gray-400">Dosya Adı</th>
              <th className="px-4 py-3 text-left font-medium text-gray-400">Kaynak</th>
              <th className="px-4 py-3 text-right font-medium text-gray-400">Kayıt</th>
              <th className="px-4 py-3 text-left font-medium text-gray-400">Tarih</th>
              <th className="px-4 py-3 text-left font-medium text-gray-400">Son Adım</th>
              <th className="px-4 py-3 text-left font-medium text-gray-400">Durum</th>
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
                  <tr key={item.id} className="transition-colors hover:bg-gray-50/50">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <i className={`${icon} text-base text-gray-400`} />
                        <span className="max-w-[180px] truncate font-medium text-gray-800">
                          {item.file_name}
                        </span>
                        <span className="ml-1 text-gray-400">#{item.id}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-gray-500">{sourceLabel(item.source_type)}</td>
                    <td className="px-4 py-3.5 text-right font-medium text-gray-700">
                      {(item.total_records ?? 0).toLocaleString("tr-TR")}
                    </td>
                    <td className="px-4 py-3.5 text-gray-500">{formatDate(item.created_at)}</td>
                    <td className="px-4 py-3.5 text-gray-400">{stageLabel(item.processing_stage)}</td>
                    <td className="px-4 py-3.5">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ${badge.cls}`}>
                        <i className={`${badge.icon} text-xs`} />
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
