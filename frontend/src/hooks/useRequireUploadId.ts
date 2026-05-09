import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

/**
 * Veri hattı sayfaları: URL'de geçerli `upload_id` yoksa /veri-yukleme'ye yönlendirir.
 * Dönüş: geçerli id veya yönlendirme sırasında null.
 */
export function useRequireUploadId(): number | null {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const raw = searchParams.get("upload_id");
  const parsed = raw ? Number(raw) : NaN;
  const valid = Number.isFinite(parsed) && parsed > 0;

  useEffect(() => {
    if (!valid) {
      navigate("/veri-yukleme", { replace: true });
    }
  }, [valid, navigate]);

  return valid ? parsed : null;
}
