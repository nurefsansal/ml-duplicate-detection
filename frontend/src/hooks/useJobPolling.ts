import { useEffect, useRef, useState } from "react";
import { getJobStatus, type JobStatusResponse } from "../services/api";

export function useJobPolling(jobId: number | null | undefined, options?: { intervalMs?: number }) {
  const intervalMs = options?.intervalMs ?? 900;
  const [job, setJob] = useState<JobStatusResponse["job"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let mounted = true;
    setLoading(true);
    setError(null);

    const tick = async () => {
      try {
        const resp = await getJobStatus(jobId);
        if (!mounted) return;
        setJob(resp.job);
        setError(null);
        setLoading(false);
        if (resp.job.status === "completed" || resp.job.status === "failed") {
          if (timerRef.current) window.clearInterval(timerRef.current);
          timerRef.current = null;
        }
      } catch (e) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
        if (timerRef.current) window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };

    tick();
    timerRef.current = window.setInterval(tick, intervalMs);

    return () => {
      mounted = false;
      if (timerRef.current) window.clearInterval(timerRef.current);
      timerRef.current = null;
    };
  }, [jobId, intervalMs]);

  return { job, loading, error };
}

