"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import type { createFetch } from "../lib/api";
import type {
  Category,
  ExplanationFormat,
  ExplanationMode,
  SearchResponse,
  Conversation,
  SearchHistoryItem,
  SavedSessionItem,
  SourceType,
  SortBy,
} from "../types/api";

type ApiFetchType = ReturnType<typeof createFetch>;

type Callbacks = { onError?: (msg: string) => void; onInfo?: (msg: string) => void };

export function useSearch(
  _apiUrl: string,
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
  const [domainFilterText, setDomainFilterText] = useState("");
  const [authorFilterText, setAuthorFilterText] = useState("");
  const [languageFilterText, setLanguageFilterText] = useState("");
  const [regionFilterText, setRegionFilterText] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [minCredibility, setMinCredibility] = useState(0);

  const [result, setResult] = useState<SearchResponse | null>(null);
  const [followUpQuestion, setFollowUpQuestion] = useState("");
  const [followUpResponse, setFollowUpResponse] = useState<{ response: string; key_points: string[] } | null>(null);
  const [history, setHistory] = useState<SearchHistoryItem[]>([]);
  const [savedSessions, setSavedSessions] = useState<SavedSessionItem[]>([]);
  const [sessionLabel, setSessionLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [shareUrl, setShareUrl] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const sourceFilter = useMemo(
    () => sourceFilterText.split(",").map((s) => s.trim()).filter(Boolean),
    [sourceFilterText]
  );
  const csv = useCallback((value: string) => value.split(",").map((s) => s.trim()).filter(Boolean), []);

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
    setDomainFilterText("");
    setAuthorFilterText("");
    setLanguageFilterText("");
    setRegionFilterText("");
    setDateFrom("");
    setDateTo("");
    setMinCredibility(0);
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

  const loadHistory = useCallback(async (append = false) => {
    try {
      const offset = append ? history.length : 0;
      const r = await apiFetch(`/me/search-history?limit=12&offset=${offset}`);
      if (!r.ok) { setHistory([]); return; }
      const items = await r.json() as SearchHistoryItem[];
      setHistory((current) => append ? [...current, ...items] : items);
    } catch {
      setHistory([]);
    }
  }, [apiFetch, history.length]);

  const loadSavedSessions = useCallback(async (append = false) => {
    try {
      const offset = append ? savedSessions.length : 0;
      const r = await apiFetch(`/me/saved-sessions?limit=12&offset=${offset}`);
      if (!r.ok) { setSavedSessions([]); return; }
      const items = await r.json() as SavedSessionItem[];
      setSavedSessions((current) => append ? [...current, ...items] : items);
    } catch {
      setSavedSessions([]);
    }
  }, [apiFetch, savedSessions.length]);

  const runSearch = useCallback(async (event: React.FormEvent) => {
    event.preventDefault();
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    onError?.("");
    onInfo?.("");
    setFollowUpResponse(null);
    try {
      const r = await apiFetch("/search/stream", {
        method: "POST",
        signal: controller.signal,
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
          domain_filter: csv(domainFilterText),
          author_filter: csv(authorFilterText),
          language_filter: csv(languageFilterText),
          region_filter: csv(regionFilterText),
          date_from: dateFrom || null,
          date_to: dateTo || null,
          min_credibility: minCredibility,
        }),
      });
      if (!r.ok) throw new Error(`Request failed with status ${r.status}`);
      if (!r.body) {
        setResult(await r.json() as SearchResponse);
      } else {
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let streamed: SearchResponse | null = null;
        let explanation = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() || "";
          for (const frame of frames) {
            const eventName = frame.match(/^event:\s*(.+)$/m)?.[1];
            const data = frame.match(/^data:\s*(.+)$/m)?.[1];
            if (!data) continue;
            if (eventName === "error") {
              throw new Error((JSON.parse(data) as { message?: string }).message || "Search failed");
            } else if (eventName === "result") {
              streamed = { ...(JSON.parse(data) as SearchResponse), explanation: "" };
              setResult(streamed);
            } else if (eventName === "explanation" && streamed) {
              explanation += (JSON.parse(data) as { text: string }).text;
              const nextResult: SearchResponse = JSON.parse(JSON.stringify(streamed)) as SearchResponse;
              nextResult.explanation = explanation;
              streamed = nextResult;
              setResult(nextResult);
            }
          }
        }
      }
      loadHistory();
    } catch (err) {
      if ((err as Error).name !== "AbortError") onError?.((err as Error).message || "Search failed");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setLoading(false);
    }
  }, [
    apiFetch, activeUserId, query, topK, selected, mode, explanationFormat,
    compareAgainst, timeline, recencyDays, sourceFilter, sourceTypesSelected,
    sortBy, domainFilterText, authorFilterText, languageFilterText, regionFilterText,
    dateFrom, dateTo, minCredibility, csv, onError, onInfo, loadHistory,
  ]);

  const cancelSearch = useCallback(() => abortRef.current?.abort(), []);

  const createConversation = useCallback(async () => {
    if (!result?.context_id) return;
    const r = await apiFetch("/conversations", {
      method: "POST", body: JSON.stringify({ context_id: result.context_id, title: query }),
    });
    if (!r.ok) { onError?.("Sign in to create a conversation."); return; }
    setConversation(await r.json() as Conversation);
    onInfo?.("Conversation created from this search.");
  }, [apiFetch, result, query, onError, onInfo]);

  const shareCurrentContext = useCallback(async () => {
    if (!result?.context_id) return;
    const r = await apiFetch(`/contexts/${result.context_id}/share`, { method: "POST" });
    if (!r.ok) { onError?.("Sign in to share this context."); return; }
    const data = await r.json() as { share_token: string };
    const url = `${window.location.origin}/shared/${data.share_token}`;
    setShareUrl(url);
    await navigator.clipboard?.writeText(url);
    onInfo?.("Share link copied.");
  }, [apiFetch, result, onError, onInfo]);

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

  const openSavedSession = useCallback(async (contextId: string) => {
    try {
      const r = await apiFetch(`/me/saved-sessions/${contextId}/context`);
      if (!r.ok) throw new Error("Unable to open saved session");
      const data = await r.json() as { query: string };
      setQuery(data.query);
      onInfo?.("Saved session loaded. Run search to refresh its results.");
    } catch (err) {
      onError?.((err as Error).message || "Unable to open saved session");
    }
  }, [apiFetch, onError, onInfo]);

  const deleteSavedSession = useCallback(async (sessionId: number) => {
    const r = await apiFetch(`/me/saved-sessions/${sessionId}`, { method: "DELETE" });
    if (r.ok) await loadSavedSessions();
  }, [apiFetch, loadSavedSessions]);

  const runFollowUp = useCallback(async () => {
    if (!result?.context_id || !followUpQuestion.trim()) return;
    try {
      const path = conversation
        ? `/conversations/${conversation.conversation_id}/messages`
        : "/followup";
      const body = conversation
        ? { question: followUpQuestion, explanation_mode: mode }
        : {
            user_id: activeUserId, context_id: result.context_id,
            question: followUpQuestion, explanation_mode: mode,
          };
      const r = await apiFetch(path, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error("Follow-up failed");
      const data = await r.json() as { response?: string; content?: string; key_points: string[] };
      setFollowUpResponse({ response: data.response || data.content || "", key_points: data.key_points || [] });
    } catch (err) {
      onError?.((err as Error).message || "Follow-up failed");
    }
  }, [apiFetch, activeUserId, result, followUpQuestion, mode, conversation, onError]);

  const submitFeedback = useCallback(async (helpful: boolean) => {
    if (!result?.context_id) return;
    const r = await apiFetch("/search/feedback", {
      method: "POST", body: JSON.stringify({ context_id: result.context_id, helpful, comment: "" }),
    });
    r.ok ? onInfo?.("Thanks for the feedback.") : onError?.("Unable to save feedback.");
  }, [apiFetch, result, onInfo, onError]);

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
    domainFilterText, setDomainFilterText,
    authorFilterText, setAuthorFilterText,
    languageFilterText, setLanguageFilterText,
    regionFilterText, setRegionFilterText,
    dateFrom, setDateFrom, dateTo, setDateTo,
    minCredibility, setMinCredibility,
    sourceFilter,
    result,
    followUpQuestion, setFollowUpQuestion,
    followUpResponse,
    history, setHistory,
    savedSessions, setSavedSessions,
    sessionLabel, setSessionLabel,
    loading,
    conversation, shareUrl,
    appliedFiltersText,
    runSearch,
    cancelSearch,
    createConversation,
    shareCurrentContext,
    saveCurrentSession,
    openSavedSession,
    deleteSavedSession,
    runFollowUp,
    submitFeedback,
    loadHistory,
    loadSavedSessions,
    loadMoreHistory: () => loadHistory(true),
    loadMoreSavedSessions: () => loadSavedSessions(true),
    resetSearchFilters,
    useHeadlineQuery,
    useSuggestedQuery,
  };
}
