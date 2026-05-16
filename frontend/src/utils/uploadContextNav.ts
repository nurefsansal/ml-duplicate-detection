const PATHS_NEEDING_UPLOAD = new Set([
  "/",
  "/ham-veri",
  "/veri-normalizasyon",
  "/temiz-veri-seti",
  "/mukerrer-tespit",
  "/mukerrer-kayitlar",
]);

/**
 * Sidebar ve linkler için: son bilinen upload_id varsa query ile birleştirir.
 * Path'te zaten `?decision=pending` gibi parametreler varsa korunur.
 */
export function withUploadContext(path: string): string {
  const qMark = path.indexOf("?");
  const pathOnly = qMark >= 0 ? path.slice(0, qMark) : path;
  if (!PATHS_NEEDING_UPLOAD.has(pathOnly)) return path;

  try {
    const raw =
      localStorage.getItem("lastUploadId") ||
      localStorage.getItem("lastDetectUploadId");
    const id = raw ? Number(raw) : NaN;
    if (!Number.isFinite(id) || id <= 0) return path;

    const params = new URLSearchParams(qMark >= 0 ? path.slice(qMark + 1) : "");
    params.set("upload_id", String(id));
    return `${pathOnly}?${params.toString()}`;
  } catch {
    return path;
  }
}
