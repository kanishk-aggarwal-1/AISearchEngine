"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

const categories = ["tech", "research", "sports", "general"];
const modes = ["tldr", "beginner", "deep", "analyst"];
const explanationFormats = ["standard", "bullet", "pros_cons", "timeline", "fact_check"];
const sourceTypes = ["news", "research", "sports", "api", "community"];
const sortOptions = ["relevance", "latest"];
const categoryLabels = {
  tech: "Tech",
  research: "Research",
  sports: "Sports",
  general: "General",
};

export default function HomePage() {
  const [userId, setUserId] = useState("default");
  const [query, setQuery] = useState("latest breakthroughs in AI agents");
  const [compareAgainst, setCompareAgainst] = useState("");
  const [topK, setTopK] = useState(6);
  const [mode, setMode] = useState("beginner");
  const [explanationFormat, setExplanationFormat] = useState("standard");
  const [timeline, setTimeline] = useState(true);
  const [selected, setSelected] = useState(["tech", "research", "general"]);
  const [recencyDays, setRecencyDays] = useState(7);
  const [sortBy, setSortBy] = useState("relevance");
  const [sourceFilterText, setSourceFilterText] = useState("");
  const [sourceTypesSelected, setSourceTypesSelected] = useState([]);

  const [followEntity, setFollowEntity] = useState("");
  const [followed, setFollowed] = useState([]);
  const [alertQuery, setAlertQuery] = useState("");
  const [alerts, setAlerts] = useState([]);
  const [delivery, setDelivery] = useState({ user_id: "default", webhook_url: "", digest_mode: "daily", enabled: false });
  const [deliveryTest, setDeliveryTest] = useState(null);

  const [followUpQuestion, setFollowUpQuestion] = useState("");
  const [followUpResponse, setFollowUpResponse] = useState(null);

  const [sportsInsight, setSportsInsight] = useState(null);
  const [sportsTeam, setSportsTeam] = useState("");
  const [sportsDashboard, setSportsDashboard] = useState(null);

  const [researchInsight, setResearchInsight] = useState(null);
  const [researchPapers, setResearchPapers] = useState([]);
  const [explainedPaper, setExplainedPaper] = useState(null);
  const [comparePapers, setComparePapers] = useState([]);
  const [paperComparison, setPaperComparison] = useState(null);

  const [bookmarks, setBookmarks] = useState([]);
  const [headlines, setHeadlines] = useState({});
  const [headlinesUpdatedAt, setHeadlinesUpdatedAt] = useState("");
  const [headlinesLoading, setHeadlinesLoading] = useState(true);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const apiUrl = useMemo(() => process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000", []);
  const sourceFilter = useMemo(
    () => sourceFilterText.split(",").map((item) => item.trim()).filter(Boolean),
    [sourceFilterText]
  );

  const toggleCategory = (category) => {
    setSelected((prev) => prev.includes(category) ? prev.filter((item) => item !== category) : [...prev, category]);
  };

  const toggleSourceType = (sourceType) => {
    setSourceTypesSelected((prev) => prev.includes(sourceType) ? prev.filter((item) => item !== sourceType) : [...prev, sourceType]);
  };

  const loadHeadlines = async () => {
    setHeadlinesLoading(true);
    try {
      const response = await fetch(`${apiUrl}/headlines?per_category=4&recency_days=${recencyDays}`);
      if (!response.ok) throw new Error(`Headlines request failed with status ${response.status}`);
      const data = await response.json();
      setHeadlines(data.categories || {});
      setHeadlinesUpdatedAt(data.updated_at || "");
    } catch (err) {
      setError(err.message || "Unable to load headlines");
    } finally {
      setHeadlinesLoading(false);
    }
  };

  const refreshFollows = async () => {
    const response = await fetch(`${apiUrl}/users/${userId}/follows`);
    if (!response.ok) return;
    const data = await response.json();
    setFollowed(data.entities || []);
  };

  const refreshAlerts = async () => {
    const response = await fetch(`${apiUrl}/users/${userId}/alerts`);
    if (!response.ok) return;
    const data = await response.json();
    setAlerts(data || []);
  };

  const loadBookmarks = async () => {
    const response = await fetch(`${apiUrl}/users/${userId}/bookmarks`);
    if (!response.ok) return;
    const data = await response.json();
    setBookmarks(data || []);
  };

  const loadDelivery = async () => {
    const response = await fetch(`${apiUrl}/users/${userId}/alert-delivery`);
    if (!response.ok) return;
    const data = await response.json();
    setDelivery(data);
  };

  useEffect(() => {
    loadHeadlines();
  }, [apiUrl, recencyDays]);

  useEffect(() => {
    refreshFollows();
    refreshAlerts();
    loadBookmarks();
    loadDelivery();
  }, [apiUrl, userId]);

  const runSearch = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setFollowUpResponse(null);
    try {
      const response = await fetch(`${apiUrl}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
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
      if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message || "Search failed");
    } finally {
      setLoading(false);
    }
  };

  const addFollow = async () => {
    if (!followEntity.trim()) return;
    try {
      const response = await fetch(`${apiUrl}/users/${userId}/follows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, entity: followEntity.trim() }),
      });
      if (!response.ok) throw new Error("Unable to add follow");
      const data = await response.json();
      setFollowed(data.entities || []);
      setFollowEntity("");
    } catch (err) {
      setError(err.message || "Follow action failed");
    }
  };

  const createAlert = async () => {
    if (!alertQuery.trim()) return;
    try {
      const response = await fetch(`${apiUrl}/users/${userId}/alerts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, query: alertQuery, categories: selected, enabled: true }),
      });
      if (!response.ok) throw new Error("Unable to create alert");
      setAlertQuery("");
      await refreshAlerts();
    } catch (err) {
      setError(err.message || "Alert action failed");
    }
  };

  const saveDelivery = async () => {
    try {
      const response = await fetch(`${apiUrl}/users/${userId}/alert-delivery`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...delivery, user_id: userId }),
      });
      if (!response.ok) throw new Error("Unable to save delivery settings");
      const data = await response.json();
      setDelivery(data);
    } catch (err) {
      setError(err.message || "Unable to save delivery settings");
    }
  };

  const testDelivery = async () => {
    try {
      const response = await fetch(`${apiUrl}/users/${userId}/alert-delivery/test`, { method: "POST" });
      if (!response.ok) throw new Error("Unable to test delivery");
      const data = await response.json();
      setDeliveryTest(data);
    } catch (err) {
      setError(err.message || "Unable to test delivery");
    }
  };

  const runFollowUp = async () => {
    if (!result?.context_id || !followUpQuestion.trim()) return;
    try {
      const response = await fetch(`${apiUrl}/followup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, context_id: result.context_id, question: followUpQuestion, explanation_mode: mode }),
      });
      if (!response.ok) throw new Error("Follow-up failed");
      const data = await response.json();
      setFollowUpResponse(data);
    } catch (err) {
      setError(err.message || "Follow-up failed");
    }
  };

  const fetchSportsInsights = async () => {
    const response = await fetch(`${apiUrl}/sports/insights?query=${encodeURIComponent(query)}`);
    if (!response.ok) return;
    setSportsInsight(await response.json());
  };

  const fetchSportsDashboard = async () => {
    const response = await fetch(`${apiUrl}/sports/dashboard?team=${encodeURIComponent(sportsTeam)}&recency_days=${recencyDays}`);
    if (!response.ok) return;
    setSportsDashboard(await response.json());
  };

  const fetchResearchInsights = async () => {
    const response = await fetch(`${apiUrl}/research/insights?query=${encodeURIComponent(query)}`);
    if (!response.ok) return;
    setResearchInsight(await response.json());
  };

  const fetchResearchPapers = async () => {
    const response = await fetch(`${apiUrl}/research/papers?query=${encodeURIComponent(query)}&recency_days=${Math.max(recencyDays, 7)}`);
    if (!response.ok) return;
    const data = await response.json();
    setResearchPapers(data.papers || []);
    setExplainedPaper(null);
    setPaperComparison(null);
    setComparePapers([]);
  };

  const explainPaper = async (paper) => {
    const response = await fetch(`${apiUrl}/research/explain-paper`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: paper, explanation_mode: mode }),
    });
    if (!response.ok) return;
    setExplainedPaper(await response.json());
  };

  const toggleComparePaper = async (paper) => {
    setComparePapers((prev) => {
      const exists = prev.find((item) => item.url === paper.url);
      if (exists) return prev.filter((item) => item.url !== paper.url);
      return prev.length >= 2 ? [prev[1], paper] : [...prev, paper];
    });
  };

  useEffect(() => {
    const runCompare = async () => {
      if (comparePapers.length !== 2) {
        setPaperComparison(null);
        return;
      }
      const response = await fetch(`${apiUrl}/research/compare-papers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ left: comparePapers[0], right: comparePapers[1] }),
      });
      if (!response.ok) return;
      setPaperComparison(await response.json());
    };
    runCompare();
  }, [comparePapers, apiUrl]);

  const addBookmark = async (source) => {
    try {
      const response = await fetch(`${apiUrl}/users/${userId}/bookmarks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, source }),
      });
      if (!response.ok) throw new Error("Unable to save bookmark");
      await loadBookmarks();
    } catch (err) {
      setError(err.message || "Unable to save bookmark");
    }
  };

  const removeBookmark = async (bookmarkId) => {
    const response = await fetch(`${apiUrl}/users/${userId}/bookmarks/${bookmarkId}`, { method: "DELETE" });
    if (response.ok) await loadBookmarks();
  };

  const useHeadlineQuery = (headline) => {
    setQuery(headline.title);
    setSelected([headline.category]);
    setCompareAgainst("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const appliedFiltersText = result?.applied_filters
    ? `Recency: ${result.applied_filters.recency_days || "any"}d | Sort: ${result.applied_filters.sort_by}`
    : "";

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="badge">SignalScope AI</p>
        <h1>Search live signals. Explain what changed.</h1>
        <p className="subtitle">Broader coverage, recency controls, bookmarks, category pages, sports and research workspaces.</p>
      </section>

      <section className="query-card headlines-card">
        <div className="section-heading">
          <div>
            <h2>Latest Headlines</h2>
            <p className="muted">
              A quick read across the categories. Updated from your live sources.
              {headlinesUpdatedAt ? ` Last refresh: ${new Date(headlinesUpdatedAt).toLocaleString()}` : ""}
            </p>
          </div>
          <button type="button" onClick={loadHeadlines} disabled={headlinesLoading}>{headlinesLoading ? "Refreshing..." : "Refresh headlines"}</button>
        </div>

        <div className="headline-grid">
          {categories.map((category) => (
            <article className="headline-column" key={category}>
              <div className="headline-column-header">
                <h3>{categoryLabels[category]}</h3>
                <Link href={`/category/${category}`} className="text-link">Open page</Link>
              </div>
              <div className="headline-list">
                {(headlines[category] || []).length ? (
                  headlines[category].map((headline, index) => (
                    <div className="headline-stack" key={`${headline.url}-${index}`}>
                      <button type="button" className="headline-item" onClick={() => useHeadlineQuery(headline)}>
                        <p className="source-meta">{headline.source} | {headline.freshness_label || "fresh"}</p>
                        <h4>{headline.title}</h4>
                        <p className="muted">{headline.summary}</p>
                      </button>
                      <button type="button" className="mini-button" onClick={() => addBookmark(headline)}>Save</button>
                    </div>
                  ))
                ) : (
                  <div className="headline-empty muted">{headlinesLoading ? "Loading latest items..." : "No headlines available right now."}</div>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="query-card">
        <form onSubmit={runSearch}>
          <div className="control-grid">
            <div>
              <label className="label">User ID</label>
              <input value={userId} onChange={(e) => setUserId(e.target.value)} />
            </div>
            <div>
              <label className="label">Explanation mode</label>
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                {modes.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Explanation format</label>
              <select value={explanationFormat} onChange={(e) => setExplanationFormat(e.target.value)}>
                {explanationFormats.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Sort by</label>
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                {sortOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
          </div>

          <label className="label" htmlFor="query">Ask anything</label>
          <textarea id="query" value={query} onChange={(e) => setQuery(e.target.value)} rows={3} placeholder="What changed this week in autonomous coding agents?" />

          <div className="filter-grid">
            <div>
              <label className="label" htmlFor="compareAgainst">Compare against</label>
              <input id="compareAgainst" value={compareAgainst} onChange={(e) => setCompareAgainst(e.target.value)} placeholder="quantum computing" />
            </div>
            <div>
              <label className="label" htmlFor="topK">Top results</label>
              <input id="topK" type="number" min={1} max={20} value={topK} onChange={(e) => setTopK(Number(e.target.value) || 6)} />
            </div>
            <div>
              <label className="label" htmlFor="recencyDays">Recent window (days)</label>
              <input id="recencyDays" type="number" min={1} max={30} value={recencyDays} onChange={(e) => setRecencyDays(Number(e.target.value) || 7)} />
            </div>
            <div>
              <label className="label" htmlFor="sourceFilter">Source filter</label>
              <input id="sourceFilter" value={sourceFilterText} onChange={(e) => setSourceFilterText(e.target.value)} placeholder="BBC World, arXiv" />
            </div>
          </div>

          <div className="controls-row">
            <div className="chips">
              {categories.map((category) => (
                <button type="button" key={category} className={selected.includes(category) ? "chip active" : "chip"} onClick={() => toggleCategory(category)}>{category}</button>
              ))}
            </div>
            <div className="chips">
              {sourceTypes.map((sourceType) => (
                <button type="button" key={sourceType} className={sourceTypesSelected.includes(sourceType) ? "chip active" : "chip"} onClick={() => toggleSourceType(sourceType)}>{sourceType}</button>
              ))}
            </div>
            <label className="toggle">
              <input type="checkbox" checked={timeline} onChange={(e) => setTimeline(e.target.checked)} />
              Include timeline
            </label>
          </div>

          <button className="search-button" type="submit" disabled={loading || !query.trim() || selected.length === 0}>{loading ? "Searching..." : "Run Search"}</button>
        </form>

        <div className="quick-actions">
          <button type="button" onClick={refreshFollows}>Refresh follows</button>
          <button type="button" onClick={refreshAlerts}>Refresh alerts</button>
          <button type="button" onClick={fetchSportsInsights}>Sports insights</button>
          <button type="button" onClick={fetchSportsDashboard}>Sports dashboard</button>
          <button type="button" onClick={fetchResearchInsights}>Research insights</button>
          <button type="button" onClick={fetchResearchPapers}>Research papers</button>
        </div>

        {error ? <p className="error">{error}</p> : null}
      </section>

      <section className="three-grid">
        <article className="explanation-card">
          <h2>Personalization</h2>
          <div className="inline-row">
            <input value={followEntity} onChange={(e) => setFollowEntity(e.target.value)} placeholder="Follow entity (e.g., OpenAI, Lakers, NVIDIA)" />
            <button type="button" onClick={addFollow}>Add</button>
          </div>
          <p className="muted">Following: {followed.length ? followed.join(", ") : "None"}</p>
          <div className="inline-row">
            <input value={alertQuery} onChange={(e) => setAlertQuery(e.target.value)} placeholder="Create alert query" />
            <button type="button" onClick={createAlert}>Save alert</button>
          </div>
          <p className="muted">Alerts: {alerts.length}</p>
        </article>

        <article className="explanation-card">
          <h2>Alert Delivery</h2>
          <label className="label">Webhook URL</label>
          <input value={delivery.webhook_url || ""} onChange={(e) => setDelivery((prev) => ({ ...prev, webhook_url: e.target.value, user_id: userId }))} placeholder="https://hooks.slack.com/..." />
          <label className="label">Digest mode</label>
          <select value={delivery.digest_mode || "daily"} onChange={(e) => setDelivery((prev) => ({ ...prev, digest_mode: e.target.value, user_id: userId }))}>
            <option value="instant">instant</option>
            <option value="daily">daily</option>
          </select>
          <label className="toggle">
            <input type="checkbox" checked={Boolean(delivery.enabled)} onChange={(e) => setDelivery((prev) => ({ ...prev, enabled: e.target.checked, user_id: userId }))} />
            Delivery enabled
          </label>
          <div className="quick-actions">
            <button type="button" onClick={saveDelivery}>Save settings</button>
            <button type="button" onClick={testDelivery}>Test delivery</button>
          </div>
          {deliveryTest ? <p className="muted">{deliveryTest.preview_only ? "Preview only generated." : `Last test status: ${deliveryTest.status_code || "error"}`}</p> : null}
        </article>

        <article className="explanation-card">
          <h2>Saved Collection</h2>
          <div className="bookmark-list compact-list">
            {bookmarks.length ? bookmarks.slice(0, 6).map((bookmark) => (
              <div key={bookmark.id} className="bookmark-item">
                <div>
                  <p className="source-meta">{bookmark.source.source} | {bookmark.source.category}</p>
                  <p className="bookmark-title">{bookmark.source.title}</p>
                </div>
                <button type="button" className="mini-button" onClick={() => removeBookmark(bookmark.id)}>Remove</button>
              </div>
            )) : <p className="muted">No bookmarks yet.</p>}
          </div>
        </article>
      </section>

      {result ? (
        <section className="result-grid">
          <article className="explanation-card">
            <h2>Explanation</h2>
            <p className="muted">Provider: {result.explanation_provider}</p>
            <p className="muted">{appliedFiltersText}</p>
            <p className="formatted-block">{result.explanation}</p>
            <h3>Why it matters</h3>
            <p>{result.why_it_matters}</p>
            <h3>What changed last week</h3>
            <p>{result.what_changed_last_week}</p>
            <h3>Claim confidence</h3>
            <p>{Math.round((result.claim_confidence || 0) * 100)}%</p>
            <h3>Key takeaways</h3>
            <ul>
              {(result.key_takeaways || []).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
            </ul>
            {result.contradictions?.length ? (
              <>
                <h3>Potential contradictions</h3>
                <ul>{result.contradictions.map((item, idx) => <li key={`${item}-${idx}`}>{item}</li>)}</ul>
              </>
            ) : null}
            {result.context_id ? (
              <div className="followup-box">
                <h3>Follow-up chat</h3>
                <input value={followUpQuestion} onChange={(e) => setFollowUpQuestion(e.target.value)} placeholder="Ask a follow-up about this context" />
                <button type="button" onClick={runFollowUp}>Ask</button>
                {followUpResponse ? (
                  <div className="followup-answer">
                    <p>{followUpResponse.response}</p>
                    <ul>{(followUpResponse.key_points || []).map((point, idx) => <li key={`${point}-${idx}`}>{point}</li>)}</ul>
                  </div>
                ) : null}
              </div>
            ) : null}
          </article>

          <article className="sources-card">
            <h2>Sources</h2>
            <div className="sources-list">
              {result.sources.map((source, index) => (
                <div key={`${source.url}-${index}`} className="source-item source-card-shell">
                  <a href={source.url} target="_blank" rel="noreferrer" className="source-link-block">
                    <p className="source-meta">{source.source} | {source.category} | {source.freshness_label} | {source.source_type}</p>
                    <h3>{source.title}</h3>
                    <p>{source.summary}</p>
                    <p className="muted">Citation: {source.citation_snippet}</p>
                    <p className="muted">Credibility {Math.round((source.credibility_score || 0) * 100)}% | Confidence {Math.round((source.confidence_score || 0) * 100)}% | Bias {source.bias_label}</p>
                    <p className="muted">Scores S:{source.semantic_score} L:{source.lexical_score} R:{source.recency_score} P:{source.personalization_score}</p>
                    {source.sports_metadata ? <p className="muted">Sports trend: {source.sports_metadata.trend} | Team: {source.sports_metadata.team || "n/a"} | Opponent: {source.sports_metadata.opponent || "n/a"}</p> : null}
                    {source.research_metadata ? <p className="muted">Research theme: {source.research_metadata.theme} | Venue: {source.research_metadata.venue || "n/a"} | Authors: {(source.research_metadata.authors || []).slice(0, 3).join(", ") || "n/a"}</p> : null}
                  </a>
                  <div className="card-actions">
                    <button type="button" className="mini-button" onClick={() => addBookmark(source)}>Save</button>
                    {source.category === "research" ? <button type="button" className="mini-button" onClick={() => explainPaper(source)}>Explain paper</button> : null}
                  </div>
                </div>
              ))}
            </div>
          </article>
        </section>
      ) : null}

      {result?.timeline?.length ? (
        <section className="query-card">
          <h2>Timeline</h2>
          <div className="timeline-list">
            {result.timeline.map((point, idx) => (
              <div className="timeline-item" key={`${point.date}-${point.event}-${idx}`}>
                <p className="source-meta">{point.date} | {point.source} | {point.category}</p>
                <p>{point.event}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="two-grid">
        {sportsInsight || sportsDashboard ? (
          <article className="query-card">
            <h2>Sports Workspace</h2>
            <div className="inline-row">
              <input value={sportsTeam} onChange={(e) => setSportsTeam(e.target.value)} placeholder="Team focus, e.g. Lakers" />
              <button type="button" onClick={fetchSportsDashboard}>Load team view</button>
            </div>
            {sportsInsight ? <p className="muted">Top leagues: {Object.entries(sportsInsight.top_leagues || {}).map(([k, v]) => `${k} (${v})`).join(", ") || "n/a"}</p> : null}
            {sportsDashboard?.latest_scores?.length ? (
              <div className="compact-list">
                <h3>Latest Scores</h3>
                {sportsDashboard.latest_scores.map((item, idx) => <p key={`${item.url}-${idx}`}>{item.title}</p>)}
              </div>
            ) : null}
            {sportsDashboard?.news?.length ? (
              <div className="compact-list">
                <h3>Sports News</h3>
                {sportsDashboard.news.slice(0, 5).map((item, idx) => <p key={`${item.url}-${idx}`}>{item.title}</p>)}
              </div>
            ) : null}
          </article>
        ) : null}

        {researchInsight || researchPapers.length || explainedPaper || paperComparison ? (
          <article className="query-card">
            <h2>Research Workspace</h2>
            {researchInsight ? <p className="muted">Themes: {Object.entries(researchInsight.theme_clusters || {}).map(([k, v]) => `${k} (${v})`).join(", ") || "n/a"}</p> : null}
            {researchPapers.length ? (
              <div className="compact-list research-list">
                <h3>Papers</h3>
                {researchPapers.slice(0, 6).map((paper, idx) => (
                  <div key={`${paper.url}-${idx}`} className="research-row">
                    <div>
                      <p className="bookmark-title">{paper.title}</p>
                      <p className="muted">{paper.research_metadata?.authors?.slice(0, 3).join(", ") || "Unknown authors"}</p>
                    </div>
                    <div className="card-actions">
                      <button type="button" className="mini-button" onClick={() => explainPaper(paper)}>Explain</button>
                      <button type="button" className={comparePapers.find((item) => item.url === paper.url) ? "mini-button active-mini" : "mini-button"} onClick={() => toggleComparePaper(paper)}>Compare</button>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
            {explainedPaper ? (
              <div className="followup-answer">
                <h3>Paper Explainer</h3>
                <p>{explainedPaper.summary}</p>
                <ul>{(explainedPaper.key_takeaways || []).map((item, idx) => <li key={`${item}-${idx}`}>{item}</li>)}</ul>
              </div>
            ) : null}
            {paperComparison ? (
              <div className="followup-answer">
                <h3>Paper Compare</h3>
                <p>{paperComparison.left_title} vs {paperComparison.right_title}</p>
                <p className="muted">Same theme: {String(paperComparison.same_theme)}</p>
                <p className="muted">Shared authors: {(paperComparison.shared_authors || []).join(", ") || "None"}</p>
              </div>
            ) : null}
          </article>
        ) : null}
      </section>
    </main>
  );
}
