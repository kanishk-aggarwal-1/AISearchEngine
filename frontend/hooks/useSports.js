"use client";

import { useCallback, useState } from "react";

export function useSports(apiUrl) {
  const [sportsInsight, setSportsInsight] = useState(null);
  const [sportsTeam, setSportsTeam] = useState("");
  const [sportsDashboard, setSportsDashboard] = useState(null);

  const fetchSportsInsights = useCallback(async (query) => {
    const r = await fetch(`${apiUrl}/sports/insights?query=${encodeURIComponent(query)}`);
    if (!r.ok) return;
    setSportsInsight(await r.json());
  }, [apiUrl]);

  const fetchSportsDashboard = useCallback(async (recencyDays) => {
    const r = await fetch(
      `${apiUrl}/sports/dashboard?team=${encodeURIComponent(sportsTeam)}&recency_days=${recencyDays}`
    );
    if (!r.ok) return;
    setSportsDashboard(await r.json());
  }, [apiUrl, sportsTeam]);

  return {
    sportsInsight,
    sportsTeam, setSportsTeam,
    sportsDashboard,
    fetchSportsInsights,
    fetchSportsDashboard,
  };
}
