"use client";

import { useCallback, useEffect, useState } from "react";

export function useResearch(apiUrl) {
  const [researchInsight, setResearchInsight] = useState(null);
  const [researchPapers, setResearchPapers] = useState([]);
  const [explainedPaper, setExplainedPaper] = useState(null);
  const [comparePapers, setComparePapers] = useState([]);
  const [paperComparison, setPaperComparison] = useState(null);

  // Auto-compare when exactly two papers are selected
  useEffect(() => {
    if (comparePapers.length !== 2) {
      setPaperComparison(null);
      return;
    }
    const run = async () => {
      const r = await fetch(`${apiUrl}/research/compare-papers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ left: comparePapers[0], right: comparePapers[1] }),
      });
      if (!r.ok) return;
      setPaperComparison(await r.json());
    };
    run();
  }, [comparePapers, apiUrl]);

  const fetchResearchInsights = useCallback(async (query) => {
    const r = await fetch(`${apiUrl}/research/insights?query=${encodeURIComponent(query)}`);
    if (!r.ok) return;
    setResearchInsight(await r.json());
  }, [apiUrl]);

  const fetchResearchPapers = useCallback(async (query, recencyDays) => {
    const r = await fetch(
      `${apiUrl}/research/papers?query=${encodeURIComponent(query)}&recency_days=${Math.max(recencyDays, 7)}`
    );
    if (!r.ok) return;
    const data = await r.json();
    setResearchPapers(data.papers || []);
    setExplainedPaper(null);
    setPaperComparison(null);
    setComparePapers([]);
  }, [apiUrl]);

  const explainPaper = useCallback(async (paper, mode) => {
    const r = await fetch(`${apiUrl}/research/explain-paper`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: paper, explanation_mode: mode }),
    });
    if (!r.ok) return;
    setExplainedPaper(await r.json());
  }, [apiUrl]);

  const toggleComparePaper = useCallback((paper) => {
    setComparePapers((prev) => {
      const exists = prev.find((p) => p.url === paper.url);
      if (exists) return prev.filter((p) => p.url !== paper.url);
      return prev.length >= 2 ? [prev[1], paper] : [...prev, paper];
    });
  }, []);

  return {
    researchInsight,
    researchPapers,
    explainedPaper,
    comparePapers,
    paperComparison,
    fetchResearchInsights,
    fetchResearchPapers,
    explainPaper,
    toggleComparePaper,
  };
}
