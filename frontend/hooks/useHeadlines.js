"use client";

import { useCallback, useEffect, useState } from "react";

export function useHeadlines(apiUrl, recencyDays, { onError } = {}) {
  const [headlines, setHeadlines] = useState({});
  const [headlinesUpdatedAt, setHeadlinesUpdatedAt] = useState("");
  const [headlinesLoading, setHeadlinesLoading] = useState(true);

  const loadHeadlines = useCallback(async () => {
    setHeadlinesLoading(true);
    try {
      const r = await fetch(`${apiUrl}/headlines?per_category=4&recency_days=${recencyDays}`);
      if (!r.ok) throw new Error(`Headlines request failed with status ${r.status}`);
      const data = await r.json();
      setHeadlines(data.categories || {});
      setHeadlinesUpdatedAt(data.updated_at || "");
    } catch (err) {
      onError?.(err.message || "Unable to load headlines");
    } finally {
      setHeadlinesLoading(false);
    }
  }, [apiUrl, recencyDays, onError]);

  useEffect(() => {
    loadHeadlines();
  }, [loadHeadlines]);

  return { headlines, headlinesUpdatedAt, headlinesLoading, loadHeadlines };
}
