"use client";

const categories = ["tech", "research", "sports", "general"];
const modes = ["tldr", "beginner", "deep", "analyst"];
const explanationFormats = ["standard", "bullet", "pros_cons", "timeline", "fact_check"];
const sourceTypes = ["news", "research", "sports", "api", "community"];
const sortOptions = ["relevance", "latest"];

export default function SearchForm({
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
  activeUserId, setUserId, session,
  loading,
  onSubmit,
  onRefreshFollows,
  onRefreshAlerts,
  onFetchSportsInsights,
  onFetchSportsDashboard,
  onFetchResearchInsights,
  onFetchResearchPapers,
}) {
  return (
    <section className="query-card">
      <form onSubmit={onSubmit}>
        <div className="control-grid">
          <div>
            <label className="label">Active User ID</label>
            <input
              value={activeUserId}
              onChange={(e) => setUserId(e.target.value)}
              disabled={Boolean(session?.user?.user_id)}
            />
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
        <textarea
          id="query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={3}
          placeholder="What changed this week in autonomous coding agents?"
        />

        <div className="filter-grid">
          <div>
            <label className="label" htmlFor="compareAgainst">Compare against</label>
            <input
              id="compareAgainst"
              value={compareAgainst}
              onChange={(e) => setCompareAgainst(e.target.value)}
              placeholder="quantum computing"
            />
          </div>
          <div>
            <label className="label" htmlFor="topK">Top results</label>
            <input
              id="topK"
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value) || 6)}
            />
          </div>
          <div>
            <label className="label" htmlFor="recencyDays">Recent window (days)</label>
            <input
              id="recencyDays"
              type="number"
              min={1}
              max={30}
              value={recencyDays}
              onChange={(e) => setRecencyDays(Number(e.target.value) || 7)}
            />
          </div>
          <div>
            <label className="label" htmlFor="sourceFilter">Source filter</label>
            <input
              id="sourceFilter"
              value={sourceFilterText}
              onChange={(e) => setSourceFilterText(e.target.value)}
              placeholder="BBC World, arXiv"
            />
          </div>
        </div>

        <div className="controls-row">
          <div className="chips">
            {categories.map((category) => (
              <button
                type="button"
                key={category}
                className={selected.includes(category) ? "chip active" : "chip"}
                onClick={() => toggleCategory(category)}
              >
                {category}
              </button>
            ))}
          </div>
          <div className="chips">
            {sourceTypes.map((sourceType) => (
              <button
                type="button"
                key={sourceType}
                className={sourceTypesSelected.includes(sourceType) ? "chip active" : "chip"}
                onClick={() => toggleSourceType(sourceType)}
              >
                {sourceType}
              </button>
            ))}
          </div>
          <label className="toggle">
            <input
              type="checkbox"
              checked={timeline}
              onChange={(e) => setTimeline(e.target.checked)}
            />
            Include timeline
          </label>
        </div>

        <button
          className="search-button"
          type="submit"
          disabled={loading || !query.trim() || selected.length === 0}
        >
          {loading ? "Searching..." : "Run Search"}
        </button>
      </form>

      <div className="quick-actions">
        <button type="button" onClick={onRefreshFollows}>Refresh follows</button>
        <button type="button" onClick={onRefreshAlerts}>Refresh alerts</button>
        <button type="button" onClick={onFetchSportsInsights}>Sports insights</button>
        <button type="button" onClick={onFetchSportsDashboard}>Sports dashboard</button>
        <button type="button" onClick={onFetchResearchInsights}>Research insights</button>
        <button type="button" onClick={onFetchResearchPapers}>Research papers</button>
      </div>
    </section>
  );
}
