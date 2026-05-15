import { useEffect, useState } from "react";
import {
  getUploadPipelineStatus,
  type UploadPipelineStatus,
} from "../services/api";

export function useUploadPipelineStatus(uploadId: number | null) {
  const [status, setStatus] = useState<UploadPipelineStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (uploadId === null) {
      setStatus(null);
      setError("");
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError("");

    getUploadPipelineStatus(uploadId)
      .then((data) => {
        if (!cancelled) setStatus(data);
      })
      .catch(() => {
        if (!cancelled) {
          setStatus(null);
          setError("Pipeline durumu alınamadı.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [uploadId]);

  return {
    status,
    loading,
    error,
    canReview: Boolean(status?.can_review),
    hasNormalizedRecords: Boolean(status?.has_normalized_records),
  };
}
