"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

export default function ResearchPaperPage({ params }) {
  const apiUrl = useMemo(() => {
    if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
    if (typeof window !== "undefined" && !["localhost", "127.0.0.1"].includes(window.location.hostname)) {
      return "/api";
    }
    return "http://127.0.0.1:8000";
  }, []);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const paperId = decodeURIComponent(params.paperId);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(`${apiUrl}/research/paper/${encodeURIComponent(paperId)}`);
        if (!response.ok) throw new Error(`Unable to load paper (${response.status})`);
        setData(await response.json());
      } catch (err) {
        setError(err.message || "Unable to load paper");
      }
    };
    load();
  }, [apiUrl, paperId]);

  return (
    <main className="page-shell">
      <section className="hero hero-article">
        <p className="badge">Research Paper</p>
        <h1>{data?.paper?.title || paperId}</h1>
        <p className="subtitle">Paper summary, related work, and quick navigation back into the search workflow.</p>
        <Link href="/" className="text-link">Back to home</Link>
      </section>

      {error ? <p className="error">{error}</p> : null}

      {data ? (
        <>
          <section className="query-card">
            <p className="source-meta">
              {data.paper.source} | {data.paper.research_metadata?.venue || "Unknown venue"} | {(data.paper.research_metadata?.authors || []).slice(0, 4).join(", ") || "Unknown authors"}
            </p>
            <p>{data.paper.summary}</p>
            <div className="card-actions">
              <a className="mini-link" href={data.paper.url} target="_blank" rel="noreferrer">Open source</a>
              {data.paper.research_metadata?.code_url ? <a className="mini-link" href={data.paper.research_metadata.code_url} target="_blank" rel="noreferrer">Code</a> : null}
            </div>
          </section>

          <section className="result-grid">
            <article className="query-card">
              <h2>AI Summary</h2>
              <p className="formatted-block">{data.summary?.explanation || "No summary available."}</p>
              <ul>
                {(data.summary?.key_takeaways || []).map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            </article>

            <article className="query-card">
              <h2>Related Papers</h2>
              <div className="sources-list">
                {(data.related_papers || []).map((item, index) => (
                  <Link
                    key={`${item.url}-${index}`}
                    className="source-item source-link-block"
                    href={item.research_metadata?.paper_id ? `/research/${encodeURIComponent(item.research_metadata.paper_id)}` : "/"}
                  >
                    <p className="source-meta">{item.research_metadata?.theme || "Related theme"} | {item.research_metadata?.venue || "Unknown venue"}</p>
                    <h3>{item.title}</h3>
                    <p>{item.summary}</p>
                  </Link>
                ))}
              </div>
            </article>
          </section>
        </>
      ) : null}
    </main>
  );
}
