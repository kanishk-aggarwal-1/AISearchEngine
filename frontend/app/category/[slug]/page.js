"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

const labels = {
  tech: "Tech",
  research: "Research",
  sports: "Sports",
  general: "General",
};

export default function CategoryPage({ params }) {
  const { slug } = params;
  const apiUrl = useMemo(() => process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000", []);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(`${apiUrl}/category/${slug}?recency_days=7`);
        if (!response.ok) throw new Error(`Category request failed with status ${response.status}`);
        setData(await response.json());
      } catch (err) {
        setError(err.message || "Unable to load category page");
      }
    };
    load();
  }, [apiUrl, slug]);

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="badge">{labels[slug] || slug}</p>
        <h1>{labels[slug] || slug} Headlines</h1>
        <p className="subtitle">A dedicated category landing page with a hero story, latest headlines, and trending topics.</p>
        <Link href="/" className="text-link">Back home</Link>
      </section>

      {error ? <section className="query-card"><p className="error">{error}</p></section> : null}

      {data?.hero_headline ? (
        <section className="query-card hero-article">
          <p className="source-meta">{data.hero_headline.source} | {data.hero_headline.freshness_label}</p>
          <h2>{data.hero_headline.title}</h2>
          <p>{data.hero_headline.summary}</p>
          <a href={data.hero_headline.url} target="_blank" rel="noreferrer" className="text-link">Open source</a>
        </section>
      ) : null}

      {data ? (
        <section className="two-grid">
          <article className="query-card">
            <h2>Trending Topics</h2>
            <div className="chips">
              {(data.trending_topics || []).map((topic) => <span key={topic} className="chip active static-chip">{topic}</span>)}
            </div>
            <h3>Top Sources</h3>
            <ul>
              {(data.top_sources || []).map(([source, count]) => <li key={source}>{source} ({count})</li>)}
            </ul>
          </article>

          <article className="query-card">
            <h2>Latest</h2>
            <div className="compact-list">
              {(data.latest || []).map((item, idx) => (
                <a key={`${item.url}-${idx}`} href={item.url} target="_blank" rel="noreferrer" className="source-item">
                  <p className="source-meta">{item.source} | {item.freshness_label}</p>
                  <h3>{item.title}</h3>
                  <p>{item.summary}</p>
                </a>
              ))}
            </div>
          </article>
        </section>
      ) : null}
    </main>
  );
}