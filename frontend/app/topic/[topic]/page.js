"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

export default function TopicPage({ params }) {
  const { topic } = params;
  const apiUrl = useMemo(() => {
    if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
    if (typeof window !== "undefined" && !["localhost", "127.0.0.1"].includes(window.location.hostname)) {
      return "/api";
    }
    return "http://127.0.0.1:8000";
  }, []);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(`${apiUrl}/topic/${encodeURIComponent(topic)}?recency_days=14`);
        if (!response.ok) throw new Error(`Topic request failed with status ${response.status}`);
        setData(await response.json());
      } catch (err) {
        setError(err.message || "Unable to load topic page");
      }
    };
    load();
  }, [apiUrl, topic]);

  const summary = data?.summary;

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="badge">Topic View</p>
        <h1>{decodeURIComponent(topic)}</h1>
        <p className="subtitle">A focused page with grounded explanation, latest sources, and related topics.</p>
        <Link href="/" className="text-link">Back home</Link>
      </section>

      {error ? <section className="query-card"><p className="error">{error}</p></section> : null}

      {summary ? (
        <>
          <section className="result-grid">
            <article className="explanation-card">
              <h2>Overview</h2>
              <p className="muted">Provider: {summary.explanation_provider}</p>
              <p className="formatted-block">{summary.explanation}</p>
              <h3>Key Takeaways</h3>
              <ul>{(summary.key_takeaways || []).map((item, idx) => <li key={`${item}-${idx}`}>{item}</li>)}</ul>
              <h3>Related Topics</h3>
              <div className="chips">
                {(data.related_topics || []).map((item) => (
                  <Link key={item} href={`/topic/${encodeURIComponent(item)}`} className="chip active static-chip">
                    {item}
                  </Link>
                ))}
              </div>
            </article>

            <article className="sources-card">
              <h2>Latest Sources</h2>
              <div className="sources-list">
                {(summary.sources || []).map((source, idx) => (
                  <a key={`${source.url}-${idx}`} href={source.url} target="_blank" rel="noreferrer" className="source-item">
                    <p className="source-meta">{source.source} | {source.category} | {source.freshness_label}</p>
                    <h3>{source.title}</h3>
                    <p>{source.summary}</p>
                  </a>
                ))}
              </div>
            </article>
          </section>

          {summary.timeline?.length ? (
            <section className="query-card">
              <h2>Timeline</h2>
              <div className="timeline-list">
                {summary.timeline.map((point, idx) => (
                  <div className="timeline-item" key={`${point.date}-${point.event}-${idx}`}>
                    <p className="source-meta">{point.date} | {point.source}</p>
                    <p>{point.event}</p>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
