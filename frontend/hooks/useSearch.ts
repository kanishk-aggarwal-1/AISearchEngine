"use client";

import { useCallback, useMemo, useState } from "react";
import type { createFetch } from "../lib/api";
import type {
  Category,
  ExplanationFormat,
  ExplanationMode,
  SearchResponse,
  SearchHistoryItem,
  SavedSessionItem,
  SourceType,
  SortBy,
} from "../types/api";

type ApiFetchType = ReturnType<typeof createFetch>;

type Callbacks = { onError?: (msg: string) => void; onInfo?: (msg: string) => void };

export function useSearch(
  apiUrl: string,
  activeUserId: string,
  apiFetch: ApiFetchType,
  { onError, onInfo }: Callbacks = {}
) {
  const [query, setQuery] = useState("latest breakthroughs in AI agents");
  const [compareAgainst, setCompareAgainst] = useState("");
  const [topK, setTopK] = useState(6);
  const [mode, setMode] = useState<ExplanationMode>("beginner");
  const [explanationFormat, setExplanationFormat] = useState<ExplanationFormat>("standard");
  const [timeline, setTimeline] = useState(true);
  const [selected, setSelected] = useState<Category[]>(["tech", "research", "general"]);
  const [recencyDays, setRecencyDays] = useState(7);
  const [sortBy, setSortBy] = useState<SortBy>("relevance");
  const [sourceFilterText, setSourceFilterText] = useState("");
  const [sourceTypesSelected, setSourceTypesSelected] = useState<SourceType[]>([]);

  const [result, setResult] = useState<SearchResponse | null>(null);
  const [followUpQuestion, setFollowUpQuestion] = useState("");
  const [followUpResponse, setFollowUpResponse] = useState<{ response: string; key_points: string[] } | null>(null);
  const [history, setHistory] = useState<SearchHistoryItem[]>([]);
  const [savedSessions, setSavedSessions] = useState<SavedSessionItem[]>([]);
  const [sessionLabel, setSessionLabel] = useState("");
  const [loading, setLoading] = useState(false);

  const sourceFilter = useMemo(
    () => sourceFilterText.split(",").map((s) => s.trim()).filter(Boolean),
    [sourceFilterText]
  );

  const appliedFiltersText = result?.applied_filters
    ? `Recency: ${result.applied_filters.recency_days ?? "any"}d | Sort: ${result.applied_filters.sort_by}`
    : "";

  const toggleCategory = useCallback((category: Category) => {
    setSelected((prev) =>
      prev.includes(category) ? prev.filter((c) => c !== category) : [...prev, category]
    );
  }, []);

  const toggleSourceType = useCallback((sourceType: SourceType) => {
    setSourceTypesSelected((prev) =>
      prev.includes(sourceType) ? prev.filter((s) => s !== sourceType) : [...prev, sourceType]
    );
  }, []);

  const resetSearchFilters = useCallback(() => {
    setCompareAgainst("");
    setSourceFilterText("");
    setSourceTypesSelected([]);
    setSortBy("relevance");
    setRecencyDays(7);
    setTimeline(true);
  }, []);

  const useHeadlineQuery = useCallback((headline: { title: string; category: Category }) => {
    setQuery(headline.title);
    setSelected([headline.category]);
    setCompareAgainst("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const useSuggestedQuery = useCallback((suggestion: string) => {
    setQuery(suggestion);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const r = await apiFetch("/me/search-history?limit=12");
      if (!r.ok) { setHistory([]); return; }
      setHistory(await r.json() as SearchHistoryItem[]);
    } catch {
      setHistory([]);
    }
  }, [apiFetch]);

  const loadSavedSessions = useCallback(async () => {
    try {
      const r = await apiFetch("/me/saved-sessions?limit=12");
      if (!r.ok) { setSavedSessions([]); return; }
      setSavedSessions(await r.json() as SavedSessionItem[]);
    } catch {
      setSavedSessions([]);
    }
  }, [apiFetch]);

  const runSearch = useCallback(async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    onError?.("");
    onInfo?.("");
    setFollowUpResponse(null);
    try {
      const r = await fetch(`${apiUrl}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: activeUserId,
          query,
          top_k: topK,
          categories: selected,
          explanation_mode: mode,
          explanation_format: explanationFormat,
          compare_against: compareAgainst || null,
          timeline,
          recency_days: recencyDays,
          source_filter: sourceFilter,
          source_type_filter: sourceTypesSelected,
          sort_by: sortBy,
        }),
      });
      if (!r.ok) throw new Error(`Request failed with status ${r.status}`);
      setResult(await r.json() as SearchResponse);
      loadHistory();
    } catch (err) {
      onError?.((err as Error).message || "Search failed");
    } finally {
      setLoading(false);
    }
  }, [
    apiUrl, activeUserId, query, topK, selected, mode, explanationFormat,
    compareAgainst, timeline, recencyDays, sourceFilter, sourceTypesSelected,
    sortBy, onError, onInfo, loadHistory,
  ]);

  const saveCurrentSession = useCallback(async (contextId: string | undefined, token: string | null) => {
    if (!contextId || !token) return;
    try {
      const r = await apiFetch(`/me/saved-sessions/${contextId}`, {
        method: "POST",
        body: JSON.stringify({ label: sessionLabel || query }),
      });
      if (!r.ok) throw new Error("Unable to save session");
      setSessionLabel("");
      loadSavedSessions();
      onInfo?.("Session saved.");
    } catch (err) {
      onError?.((err as Error).message || "Unable to save session");
    }
  }, [apiFetch, sessionLabel, query, onError, onInfo, loadSavedSessions]);

  const runFollowUp = useCallback(async () => {
    if (!result?.context_id || !followUpQuestion.trim()) return;
    try {
      const r = await fetch(`${apiUrl}/followup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: activeUserId,
          context_id: result.context_id,
          question: followUpQuestion,
          explanation_mode: mode,
        }),
      });
      if (!r.ok) throw new Error("Follow-up failed");
      setFollowUpResponse(await r.json());
    } catch (err) {
      onError?.((err as Error).message || "Follow-up failed");
    }
  }, [apiUrl, activeUserId, result, followUpQuestion, mode, onError]);

  return {
    query, setQuery,
    compareAgainst, setCompareAgainst,
    topK, setTopK,
    mode, setMode,
    explanationFormat, setExplanationFormat,
    timeline, setTimeline,
    selected, toggleCategory,
    recencyDays, setRecencyDays,
    sortBy, setSortBy,
    sourceFilterText, setSourceFilterText,
    sourceTypesSelected, toggleSourceType,
    sourceFilter,
    result,
    followUpQuestion, setFollowUpQuestion,
    followUpResponse,
    history, setHistory,
    savedSessions, setSavedSessions,
    sessionLabel, setSessionLabel,
    loading,
    appliedFiltersText,
    runSearch,
    saveCurrentSession,
    runFollowUp,
    loadHistory,
    loadSavedSessions,
    resetSearchFilters,
    useHeadlineQuery,
    useSuggestedQuery,
  };
}
