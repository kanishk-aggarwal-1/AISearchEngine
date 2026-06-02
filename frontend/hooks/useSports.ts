"use client";

import { useCallback, useState } from "react";
import type { SportsInsight, SportsDashboard } from "../types/api";

export function useSports(apiUrl: string) {
  const [sportsInsight, setSportsInsight] = useState<SportsInsight | null>(null);
  const [sportsTeam, setSportsTeam] = useState("");
  const [sportsDashboard, setSportsDashboard] = useState<SportsDashboard | null>(null);

  const fetchSportsInsights = useCallback(async (query: string) => {
    const r = await fetch(`${apiUrl}/sports/insights?query=${encodeURIComponent(query)}`);
    if (!r.ok) return;
    setSportsInsight(await r.json() as SportsInsight);
  }, [apiUrl]);

  const fetchSportsDashboard = useCallback(async (recencyDays: number) => {
    const r = await fetch(
      `${apiUrl}/sports/dashboard?team=${encodeURIComponent(sportsTeam)}&recency_days=${recencyDays}`
    );
    if (!r.ok) return;
    setSportsDashboard(await r.json() as SportsDashboard);
  }, [apiUrl, sportsTeam]);

  return {
    sportsInsight,
    sportsTeam, setSportsTeam,
    sportsDashboard,
    fetchSportsInsights,
    fetchSportsDashboard,
  };
}
