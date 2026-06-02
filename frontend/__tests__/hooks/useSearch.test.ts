import { act, renderHook } from "@testing-library/react";
import { useSearch } from "../../hooks/useSearch";
import { createFetch } from "../../lib/api";
import type { Category } from "../../types/api";

const API_URL = "http://localhost:8000";
const mockApiFetch = createFetch(API_URL, null);

beforeEach(() => { jest.clearAllMocks(); });

describe("useSearch — initial state", () => {
  it("initializes with expected defaults", () => {
    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch));
    expect(result.current.query).toBe("latest breakthroughs in AI agents");
    expect(result.current.selected).toEqual(["tech", "research", "general"]);
    expect(result.current.topK).toBe(6);
    expect(result.current.mode).toBe("beginner");
    expect(result.current.recencyDays).toBe(7);
    expect(result.current.sortBy).toBe("relevance");
    expect(result.current.loading).toBe(false);
    expect(result.current.result).toBeNull();
  });
});

describe("useSearch — toggleCategory", () => {
  it("adds a new category", () => {
    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch));
    act(() => { result.current.toggleCategory("sports"); });
    expect(result.current.selected).toContain("sports");
  });

  it("removes an existing category", () => {
    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch));
    act(() => { result.current.toggleCategory("tech"); }); // remove existing
    expect(result.current.selected).not.toContain("tech");
  });

  it("preserves other categories when toggling", () => {
    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch));
    act(() => { result.current.toggleCategory("sports"); });
    expect(result.current.selected).toContain("research");
    expect(result.current.selected).toContain("general");
  });
});

describe("useSearch — resetSearchFilters", () => {
  it("resets all filter state to defaults", () => {
    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch));

    // Mutate filters
    act(() => {
      result.current.setCompareAgainst("quantum");
      result.current.setSourceFilterText("BBC,CNN");
      result.current.setSortBy("latest");
      result.current.setRecencyDays(30);
      result.current.setTimeline(false);
    });

    act(() => { result.current.resetSearchFilters(); });

    expect(result.current.compareAgainst).toBe("");
    expect(result.current.sourceFilterText).toBe("");
    expect(result.current.sortBy).toBe("relevance");
    expect(result.current.recencyDays).toBe(7);
    expect(result.current.timeline).toBe(true);
  });
});

describe("useSearch — useHeadlineQuery", () => {
  it("sets query and narrows selected to the headline's category", () => {
    // Mock window.scrollTo
    Object.defineProperty(window, "scrollTo", { value: jest.fn(), writable: true });

    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch));
    act(() => {
      result.current.useHeadlineQuery({ title: "AI chips dominate CES", category: "tech" as Category });
    });

    expect(result.current.query).toBe("AI chips dominate CES");
    expect(result.current.selected).toEqual(["tech"]);
    expect(result.current.compareAgainst).toBe("");
  });
});

describe("useSearch — useSuggestedQuery", () => {
  it("updates the query text", () => {
    Object.defineProperty(window, "scrollTo", { value: jest.fn(), writable: true });
    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch));
    act(() => { result.current.useSuggestedQuery("latest AI models 2025"); });
    expect(result.current.query).toBe("latest AI models 2025");
  });
});

describe("useSearch — sourceFilter memoization", () => {
  it("parses comma-separated source filter text", () => {
    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch));
    act(() => { result.current.setSourceFilterText("BBC World, arXiv, TechCrunch"); });
    expect(result.current.sourceFilter).toEqual(["BBC World", "arXiv", "TechCrunch"]);
  });

  it("filters out empty entries", () => {
    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch));
    act(() => { result.current.setSourceFilterText("BBC,,arXiv,  "); });
    expect(result.current.sourceFilter).toEqual(["BBC", "arXiv"]);
  });
});

describe("useSearch — appliedFiltersText", () => {
  it("returns empty string when no result", () => {
    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch));
    expect(result.current.appliedFiltersText).toBe("");
  });
});

describe("useSearch — runSearch", () => {
  it("calls /search and stores result", async () => {
    const mockResult = {
      query: "AI agents",
      explanation: "test explanation",
      explanation_provider: "fallback",
      key_takeaways: [], why_it_matters: "", what_changed_last_week: "",
      claim_confidence: 0.8, contradictions: [], sources: [],
      timeline: [], context_id: "ctx-abc", applied_filters: { sort_by: "relevance", source_filter: [], source_type_filter: [] },
      suggested_queries: [],
    };

    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => mockResult,
    } as Response);

    // Mock apiFetch for loadHistory
    const apiFetch = jest.fn().mockResolvedValue({ ok: false });

    const { result } = renderHook(() => useSearch(API_URL, "user-1", apiFetch as ReturnType<typeof createFetch>));
    const fakeEvent = { preventDefault: jest.fn() } as unknown as React.FormEvent;

    await act(async () => { await result.current.runSearch(fakeEvent); });

    expect(result.current.result).toMatchObject({ query: "AI agents", context_id: "ctx-abc" });
    expect(result.current.loading).toBe(false);
  });

  it("sets loading to false and fires onError on network failure", async () => {
    global.fetch = jest.fn().mockRejectedValueOnce(new Error("Network down"));
    const onError = jest.fn();
    const { result } = renderHook(() => useSearch(API_URL, "default", mockApiFetch, { onError }));
    const fakeEvent = { preventDefault: jest.fn() } as unknown as React.FormEvent;

    await act(async () => { await result.current.runSearch(fakeEvent); });

    expect(result.current.loading).toBe(false);
    expect(onError).toHaveBeenCalledWith("Network down");
  });
});
