"use client";

import { useCallback, useEffect, useState } from "react";
import type { AdminData, Category, SourceStatus } from "../types/api";
import type { createFetch } from "../lib/api";

type ApiFetch = ReturnType<typeof createFetch>;
type Callbacks = { onError?: (msg: string) => void; onInfo?: (msg: string) => void };

export function useAdmin(isAdmin: boolean | undefined, apiFetch: ApiFetch, { onError, onInfo }: Callbacks = {}) {
  const [adminData, setAdminData] = useState<AdminData | null>(null);
  const [adminSources, setAdminSources] = useState<SourceStatus[]>([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [reingestTopic, setReingestTopic] = useState("");

  const loadAdminData = useCallback(async () => {
    if (!isAdmin) { setAdminData(null); setAdminSources([]); return; }
    setAdminLoading(true);
    try {
      const [dashboardRes, sourcesRes] = await Promise.all([
        apiFetch("/admin/dashboard?limit=8"),
        apiFetch("/admin/sources"),
      ]);
      if (dashboardRes.ok) setAdminData(await dashboardRes.json() as AdminData);
      if (sourcesRes.ok) setAdminSources(await sourcesRes.json() as SourceStatus[]);
    } finally {
      setAdminLoading(false);
    }
  }, [isAdmin, apiFetch]);

  useEffect(() => { loadAdminData(); }, [loadAdminData]);

  const toggleSourceEnabled = useCallback(async (sourceName: string, enabled: boolean, category: string) => {
    try {
      const r = await apiFetch(
        `/admin/sources/${encodeURIComponent(sourceName)}?category=${encodeURIComponent(category || "unknown")}`,
        { method: "PUT", body: JSON.stringify({ enabled }) }
      );
      if (!r.ok) throw new Error("Unable to update source state");
      await loadAdminData();
    } catch (err) {
      onError?.((err as Error).message || "Unable to update source state");
    }
  }, [apiFetch, onError, loadAdminData]);

  const triggerReingest = useCallback(async (categories: Category[]) => {
    if (!reingestTopic.trim()) return;
    try {
      const r = await apiFetch("/admin/reingest", {
        method: "POST",
        body: JSON.stringify({ topic: reingestTopic.trim(), categories }),
      });
      if (!r.ok) throw new Error("Unable to reingest topic");
      const data = await r.json();
      onInfo?.(`Reingested "${data.topic}" and inserted ${data.inserted} documents.`);
      setReingestTopic("");
      await loadAdminData();
    } catch (err) {
      onError?.((err as Error).message || "Unable to reingest topic");
    }
  }, [apiFetch, reingestTopic, onError, onInfo, loadAdminData]);

  return {
    adminData, adminSources, adminLoading,
    reingestTopic, setReingestTopic,
    loadAdminData, toggleSourceEnabled, triggerReingest,
  };
}
