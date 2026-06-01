"use client";

import Link from "next/link";

export default function SportsWorkspace({
  sportsTeam, setSportsTeam,
  sportsInsight,
  sportsDashboard,
  onLoadTeam,
}) {
  return (
    <article className="query-card">
      <h2>Sports Workspace</h2>
      <div className="inline-row">
        <input
          value={sportsTeam}
          onChange={(e) => setSportsTeam(e.target.value)}
          placeholder="Team focus, e.g. Lakers"
        />
        <button type="button" onClick={onLoadTeam}>Load team view</button>
      </div>
      {sportsInsight && (
        <p className="muted">
          Top leagues:{" "}
          {Object.entries(sportsInsight.top_leagues || {})
            .map(([k, v]) => `${k} (${v})`)
            .join(", ") || "n/a"}
        </p>
      )}
      {sportsDashboard?.news?.length ? (
        <div className="compact-list">
          {sportsDashboard.news.slice(0, 6).map((item, idx) => (
            <div key={`${item.url}-${idx}`} className="bookmark-item">
              <div>
                <p className="bookmark-title">{item.title}</p>
                <p className="muted">
                  {item.source} | {item.freshness_label}
                </p>
              </div>
              {item.sports_metadata?.team && (
                <Link
                  href={`/sports/${encodeURIComponent(item.sports_metadata.team)}`}
                  className="mini-link"
                >
                  Open team
                </Link>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">
          Load the sports dashboard to see team-specific headlines and scores.
        </p>
      )}
    </article>
  );
}
