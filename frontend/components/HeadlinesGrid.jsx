"use client";

import Link from "next/link";

const categories = ["tech", "research", "sports", "general"];
const categoryLabels = { tech: "Tech", research: "Research", sports: "Sports", general: "General" };

export default function HeadlinesGrid({
  headlines,
  headlinesUpdatedAt,
  headlinesLoading,
  loadHeadlines,
  onHeadlineClick,
  onBookmark,
}) {
  return (
    <section className="query-card headlines-card">
      <div className="section-heading">
        <div>
          <h2>Latest Headlines</h2>
          <p className="muted">
            A quick read across the categories.
            {headlinesUpdatedAt
              ? ` Last refresh: ${new Date(headlinesUpdatedAt).toLocaleString()}`
              : ""}
          </p>
        </div>
        <button type="button" onClick={loadHeadlines} disabled={headlinesLoading}>
          {headlinesLoading ? "Refreshing..." : "Refresh headlines"}
        </button>
      </div>

      <div className="headline-grid">
        {categories.map((category) => (
          <article className="headline-column" key={category}>
            <div className="headline-column-header">
              <h3>{categoryLabels[category]}</h3>
              <Link href={`/category/${category}`} className="text-link">
                Open page
              </Link>
            </div>
            <div className="headline-list">
              {(headlines[category] || []).length ? (
                headlines[category].map((headline, index) => (
                  <div className="headline-stack" key={`${headline.url}-${index}`}>
                    <button
                      type="button"
                      className="headline-item"
                      onClick={() => onHeadlineClick(headline)}
                    >
                      <p className="source-meta">
                        {headline.source} | {headline.freshness_label || "fresh"}
                      </p>
                      <h4>{headline.title}</h4>
                      <p className="muted">{headline.summary}</p>
                    </button>
                    <button
                      type="button"
                      className="mini-button"
                      onClick={() => onBookmark(headline)}
                    >
                      Save
                    </button>
                  </div>
                ))
              ) : (
                <div className="headline-empty muted">
                  {headlinesLoading
                    ? "Loading latest items..."
                    : "No headlines available right now."}
                </div>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
