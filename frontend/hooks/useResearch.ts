"use client";

import { useCallback, useEffect, useState } from "react";
import type { ExplanationMode, ResearchInsight, SourceDoc } from "../types/api";

interface PaperComparison {
  left_title: string;
  right_title: string;
  same_theme: boolean;
  shared_authors: string[];
}

export function useResearch(apiUrl: string) {
  const [researchInsight, setResearchInsight] = useState<ResearchInsight | null>(null);
  const [researchPapers, setResearchPapers] = useState<SourceDoc[]>([]);
  const [explainedPaper, setExplainedPaper] = useState<{ summary: string; key_takeaways: string[] } | null>(null);
  const [comparePapers, setComparePapers] = useState<SourceDoc[]>([]);
  const [paperComparison, setPaperComparison] = useState<PaperComparison | null>(null);

  useEffect(() => {
    if (comparePapers.length !== 2) { setPaperComparison(null); return; }
    const run = async () => {
      const r = await fetch(`${apiUrl}/research/compare-papers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ left: comparePapers[0], right: comparePapers[1] }),
      });
      if (!r.ok) return;
      setPaperComparison(await r.json() as PaperComparison);
    };
    run();
  }, [comparePapers, apiUrl]);

  const fetchResearchInsights = useCallback(async (query: string) => {
    const r = await fetch(`${apiUrl}/research/insights?query=${encodeURIComponent(query)}`);
    if (!r.ok) return;
    setResearchInsight(await r.json() as ResearchInsight);
  }, [apiUrl]);

  const fetchResearchPapers = useCallback(async (query: string, recencyDays: number) => {
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

  const explainPaper = useCallback(async (paper: SourceDoc, mode: ExplanationMode) => {
    const r = await fetch(`${apiUrl}/research/explain-paper`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: paper, explanation_mode: mode }),
    });
    if (!r.ok) return;
    setExplainedPaper(await r.json());
  }, [apiUrl]);

  const toggleComparePaper = useCallback((paper: SourceDoc) => {
    setComparePapers((prev) => {
      const exists = prev.find((p) => p.url === paper.url);
      if (exists) return prev.filter((p) => p.url !== paper.url);
      return prev.length >= 2 ? [prev[1], paper] : [...prev, paper];
    });
  }, []);

  return {
    researchInsight, researchPapers, explainedPaper,
    comparePapers, paperComparison,
    fetchResearchInsights, fetchResearchPapers, explainPaper, toggleComparePaper,
  };
}
