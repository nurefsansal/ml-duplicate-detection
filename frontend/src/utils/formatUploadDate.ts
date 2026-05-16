import type { UploadItem } from "../services/api";

/** Yükleme tarihi — yalnızca gün/ay/yıl, saat yok. */
export function formatUploadDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("tr-TR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return String(iso);
  }
}

type UploadOptionFields = Pick<
  UploadItem,
  "id" | "file_name" | "total_records" | "created_at"
>;

/** Select / dropdown seçenek metni. */
export function formatUploadOptionLabel(
  upload: UploadOptionFields,
  extra?: string,
): string {
  const records = Number(upload.total_records ?? 0).toLocaleString("tr-TR");
  const date = formatUploadDate(upload.created_at);
  const base = `#${upload.id} — ${upload.file_name} (${records} kayıt, ${date})`;
  return extra ? `${base}${extra}` : base;
}

/** Kart veya kısa gösterim: #12 · 16.05.2026 */
export function formatUploadIdWithDate(
  id: number,
  createdAt?: string | null,
): string {
  const date = formatUploadDate(createdAt);
  return date !== "—" ? `#${id} · ${date}` : `#${id}`;
}
