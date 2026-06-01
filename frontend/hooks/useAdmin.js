"use client";

import { useCallback, useEffect, useState } from "react";

export function useAdmin(isAdmin, apiFetch, { onError, onInfo } = {}) {
  const [adminData, setAdminData] = useState(null);
  const [adminSources, setAdminSources] = useState([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [reingestTopic, setReingestTopic] = useState("");

  const loadAdminData = useCallback(async () => {
    if (!isAdmin) {
      setAdminData(null);
      setAdminSources([]);
      return;
    }
    setAdminLoading(true);
    try {
      const [dashboardRes, sourcesRes] = await Promise.all([
        apiFetch("/admin/dashboard?limit=8"),
        apiFetch("/admin/sources"),
      ]);
      if (dashboardRes.ok) setAdminData(await dashboardRes.json());
      if (sourcesRes.ok) setAdminSources(await sourcesRes.json());
    } finally {
      setAdminLoading(false);
    }
  }, [isAdmin, apiFetch]);

  useEffect(() => {
    loadAdminData();
  }, [loadAdminData]);

  const toggleSourceEnabled = useCallback(async (sourceName, enabled, category) => {
    try {
      const r = await apiFetch(
        `/admin/sources/${encodeURIComponent(sourceName)}?category=${encodeURIComponent(category || "unknown")}`,
        { method: "PUT", body: JSON.stringify({ enabled }) }
      );
      if (!r.ok) throw new Error("Unable to update source state");
      await loadAdminData();
    } catch (err) {
      onError?.(err.message || "Unable to update source state");
    }
  }, [apiFetch, onError, loadAdminData]);

  const triggerReingest = useCallback(async (categories) => {
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
      onError?.(err.message || "Unable to reingest topic");
    }
  }, [apiFetch, reingestTopic, onError, onInfo, loadAdminData]);

  return {
    adminData,
    adminSources,
    adminLoading,
    reingestTopic, setReingestTopic,
    loadAdminData,
    toggleSourceEnabled,
    triggerReingest,
  };
}
