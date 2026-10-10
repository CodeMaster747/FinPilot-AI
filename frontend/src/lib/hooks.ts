"use client";

import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, get } from "@/lib/api";
import type { Job, User } from "@/lib/types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api<User>("/auth/me", { noRedirect: true }), retry: false, staleTime: 60_000 });
}

export type SystemStatus = {
  demo_ready: boolean;
  bootstrap: { status: string; progress: number; message: string | null } | null;
  active_jobs: { id: number; kind: string; status: string; progress: number; message: string | null; user_id: number | null }[];
  store_url: string;
};

export function useSystemStatus(fast = false) {
  return useQuery({
    queryKey: ["system-status"],
    queryFn: () => get<SystemStatus>("/system/status"),
    refetchInterval: (q) => {
      const d = q.state.data;
      return d && d.active_jobs.length === 0 && d.demo_ready && !fast ? 15_000 : 2_000;
    },
  });
}

/** Poll a background job; invalidates the given query keys when it finishes. */
export function useJob(jobId: number | null, invalidate: string[][] = []) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => get<Job>(`/jobs/${jobId}`),
    enabled: jobId !== null,
    refetchInterval: (q) => (q.state.data && ["done", "failed", "interrupted"].includes(q.state.data.status) ? false : 800),
  });
  const done = query.data && ["done", "failed", "interrupted"].includes(query.data.status);
  useEffect(() => {
    if (done) for (const key of invalidate) qc.invalidateQueries({ queryKey: key });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done]);
  return query;
}
