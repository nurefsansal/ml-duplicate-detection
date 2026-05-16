import { useCallback, useEffect, useState } from "react";

import { getDuplicateGroups, listUploads, type UploadItem } from "../services/api";

type LoadState<T> = {
  data: T | null;
  loading: boolean;
  error: boolean;
};

function initialState<T>(): LoadState<T> {
  return { data: null, loading: true, error: false };
}

export function resolveActiveUploadId(
  uploads: UploadItem[],
  urlUploadId?: number | null,
): number | null {
  if (uploads.length === 0) return null;
  if (
    urlUploadId != null &&
    Number.isFinite(urlUploadId) &&
    uploads.some((u) => u.id === urlUploadId)
  ) {
    return urlUploadId;
  }
  try {
    const fromStorage =
      localStorage.getItem("lastDetectUploadId") || localStorage.getItem("lastUploadId");
    const parsed = fromStorage ? Number(fromStorage) : NaN;
    if (Number.isFinite(parsed) && uploads.some((u) => u.id === parsed)) return parsed;
  } catch {
    /* ignore */
  }
  return uploads[0]?.id ?? null;
}

async function fetchPendingGroupTotal(uploadId: number): Promise<number> {
  const res = await getDuplicateGroups({
    uploadId,
    decision: "pending",
    page: 1,
    pageSize: 1,
    differentMuhatapCode: true,
  });
  if (!res.success) return 0;
  return res.total ?? res.count ?? 0;
}

export function useDashboardData(activeUploadId: number | null) {
  const [uploads, setUploads] = useState<LoadState<UploadItem[]>>(initialState);
  const [pendingTotal, setPendingTotal] = useState(0);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadUploads = useCallback(async () => {
    setUploads((prev) => ({ ...prev, loading: true, error: false }));
    try {
      const data = await listUploads(50);
      setUploads({ data: data.uploads || [], loading: false, error: false });
    } catch {
      setUploads({ data: null, loading: false, error: true });
    }
  }, []);

  const loadPendingTotal = useCallback(async (uploadId: number | null) => {
    if (uploadId === null) {
      setPendingTotal(0);
      setPendingLoading(false);
      return;
    }
    setPendingLoading(true);
    try {
      setPendingTotal(await fetchPendingGroupTotal(uploadId));
    } catch {
      setPendingTotal(0);
    } finally {
      setPendingLoading(false);
    }
  }, []);

  const refresh = useCallback(
    async (uploadId: number | null) => {
      setRefreshing(true);
      await Promise.all([loadUploads(), loadPendingTotal(uploadId)]);
      setLastSyncedAt(new Date());
      setRefreshing(false);
    },
    [loadPendingTotal, loadUploads],
  );

  useEffect(() => {
    void refresh(activeUploadId);
  }, [activeUploadId, refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadPendingTotal(activeUploadId);
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [activeUploadId, loadPendingTotal]);

  return {
    uploads,
    pendingTotal,
    pendingLoading,
    lastSyncedAt,
    refreshing,
    refresh,
  };
}
