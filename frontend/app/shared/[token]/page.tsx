"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getApiBase } from "../../../lib/api";

interface SharedContext {
  query: string;
  sources: Array<{ title: string; url: string; source: string; summary: string }>;
  created_at?: string;
}

export default function SharedContextPage() {
  const params = useParams<{ token: string }>();
  const [context, setContext] = useState<SharedContext | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${getApiBase()}/shared/${encodeURIComponent(params.token)}`)
      .then(async (response) => {
        if (!response.ok) throw new Error("This share link is invalid or has expired.");
        setContext(await response.json() as SharedContext);
      })
      .catch((err: Error) => setError(err.message));
  }, [params.token]);

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="badge">Shared SignalScope context</p>
        {error && <p className="error" role="alert">{error}</p>}
        {!error && !context && <p role="status">Loading shared context...</p>}
        {context && <>
          <h1>{context.query}</h1>
          <p className="muted">Read-only snapshot</p>
        </>}
      </section>
      {context && <section className="query-card">
        <h2>Sources</h2>
        {context.sources.map((source) => <article key={source.url} className="comparison-card">
          <h3><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a></h3>
          <p className="muted">{source.source}</p>
          <p>{source.summary}</p>
        </article>)}
      </section>}
    </main>
  );
}
