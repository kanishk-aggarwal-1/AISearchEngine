"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

export default function SportsTeamPage({ params }) {
  const apiUrl = useMemo(() => {
    if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
    if (typeof window !== "undefined" && !["localhost", "127.0.0.1"].includes(window.location.hostname)) {
      return "/api";
    }
    return "http://127.0.0.1:8000";
  }, []);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const team = decodeURIComponent(params.team);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(`${apiUrl}/sports/team/${encodeURIComponent(team)}?recency_days=14`);
        if (!response.ok) throw new Error(`Unable to load team page (${response.status})`);
        setData(await response.json());
      } catch (err) {
        setError(err.message || "Unable to load team page");
      }
    };
    load();
  }, [apiUrl, team]);

  return (
    <main className="page-shell">
      <section className="hero hero-article">
        <p className="badge">Sports Team</p>
        <h1>{team}</h1>
        <p className="subtitle">Recent coverage, timelines, and league context for this team.</p>
        <Link href="/" className="text-link">Back to home</Link>
      </section>

      {error ? <p className="error">{error}</p> : null}

      {data ? (
        <>
          <section className="query-card">
            <h2>League Snapshot</h2>
            <div className="stats-grid">
              {(data.leagues || []).map(([league, count]) => (
                <div key={league} className="stat-card">
                  <strong>{count}</strong>
                  <span>{league}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="result-grid">
            <article className="query-card">
              <h2>Latest Coverage</h2>
              <div className="sources-list">
                {(data.latest || []).map((item, index) => (
                  <a key={`${item.url}-${index}`} className="source-item source-link-block" href={item.url} target="_blank" rel="noreferrer">
                    <p className="source-meta">{item.source} | {item.freshness_label}</p>
                    <h3>{item.title}</h3>
                    <p>{item.summary}</p>
                  </a>
                ))}
              </div>
            </article>

            <article className="query-card">
              <h2>Timeline</h2>
              <div className="timeline-list">
                {(data.timeline || []).map((item, index) => (
                  <div key={`${item.date}-${index}`} className="timeline-item">
                    <p className="source-meta">{item.date} | {item.source}</p>
                    <p>{item.event}</p>
                  </div>
                ))}
              </div>
            </article>
          </section>
        </>
      ) : null}
    </main>
  );
}
