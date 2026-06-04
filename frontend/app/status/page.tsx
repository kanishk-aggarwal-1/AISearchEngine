"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface SeriesPoint {
  minute: number;
  searches: number;
  avg_latency_ms: number;
}

interface MetricsSummary {
  searches_total: number;
  searches_last_5min: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  cache_hit_rate: number;
  cache_hits_total: number;
  cache_misses_total: number;
  citation_coverage_pct: number;
  no_result_rate: number;
  no_result_total: number;
  documents_indexed: number;
  distinct_sources: number;
  last_ingestion_at: string | null;
  series: SeriesPoint[];
  backend: string;
  real_embeddings_enabled: boolean;
  server_time: string;
}

const POLL_MS = 5000;

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
  return `${Math.round(secs / 86400)}d ago`;
}

// ── Inline SVG charts (no chart library — keeps bundle small + CSP-safe) ──────
function Sparkline({ values, color, fill, height = 64, unit = "" }: {
  values: number[]; color: string; fill: string; height?: number; unit?: string;
}) {
  const width = 280;
  const max = Math.max(1, ...values);
  const n = values.length;
  if (n === 0) return <div className="chart-empty">No data yet</div>;
  const stepX = width / Math.max(1, n - 1);
  const points = values.map((v, i) => {
    const x = i * stepX;
    const y = height - (v / max) * (height - 8) - 4;
    return [x, y] as const;
  });
  const linePath = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${width},${height} L0,${height} Z`;
  const last = values[values.length - 1];
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img"
      aria-label={`Trend, latest value ${last}${unit}, peak ${max}${unit}`}>
      <path d={areaPath} fill={fill} />
      <path d={linePath} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      {points.length > 0 && (
        <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r="3" fill={color} />
      )}
    </svg>
  );
}

function MetricCard({ label, value, sub, accent }: {
  label: string; value: string; sub?: string; accent?: string;
}) {
  return (
    <article className="metric-card" style={accent ? { borderTopColor: accent } : undefined}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      {sub && <p className="metric-sub">{sub}</p>}
    </article>
  );
}

export default function StatusPage() {
  const apiBase = useMemo(() => {
    return process.env.NEXT_PUBLIC_API_URL
      || (typeof window !== "undefined" && !["localhost", "127.0.0.1"].includes(window.location.hostname)
        ? "/api"
        : "http://127.0.0.1:8000");
  }, []);

  const [data, setData] = useState<MetricsSummary | null>(null);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/metrics/summary`, { cache: "no-store" });
      if (!res.ok) throw new Error(`Metrics request failed (${res.status})`);
      setData(await res.json());
      setError("");
      setLastUpdated(new Date());
    } catch (err) {
      setError((err as Error).message || "Unable to load metrics");
    }
  }, [apiBase]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, POLL_MS);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [load]);

  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

  return (
    <main className="page-shell">
      <nav className="top-nav" aria-label="Primary">
        <p className="badge">SignalScope AI · Status</p>
        <div className="nav-links">
          <Link href="/" className="text-link">← Back to app</Link>
        </div>
      </nav>

      <section className="hero">
        <h1>Live Platform Metrics</h1>
        <p className="subtitle">
          Real, cumulative numbers from live traffic — persisted in Redis, refreshed every {POLL_MS / 1000}s.
        </p>
        <p className="status-meta" aria-live="polite">
          <span className={`status-dot ${error ? "down" : "up"}`} aria-hidden="true" />
          {error
            ? `Reconnecting… ${error}`
            : data
              ? `Live · backend: ${data.backend}${data.real_embeddings_enabled ? " · semantic search" : " · keyword search"} · updated ${lastUpdated ? relativeTime(lastUpdated.toISOString()) : "now"}`
              : "Connecting…"}
        </p>
      </section>

      {!data && !error && <p className="info-banner" role="status">Loading live metrics…</p>}

      {data && (
        <>
          <section className="metric-grid" aria-label="Key metrics">
            <MetricCard label="Total searches" value={data.searches_total.toLocaleString()} accent="#6366f1" />
            <MetricCard label="Searches · last 5 min" value={data.searches_last_5min.toLocaleString()} accent="#06b6d4" />
            <MetricCard label="Latency p50" value={`${data.latency_p50_ms} ms`} accent="#10b981" />
            <MetricCard label="Latency p95" value={`${data.latency_p95_ms} ms`} accent="#f59e0b" />
            <MetricCard label="Cache hit rate" value={pct(data.cache_hit_rate)}
              sub={`${data.cache_hits_total} hits / ${data.cache_misses_total} misses`} accent="#8b5cf6" />
            <MetricCard label="Citation coverage" value={`${data.citation_coverage_pct}%`} accent="#06b6d4" />
            <MetricCard label="No-result rate" value={pct(data.no_result_rate)}
              sub={`${data.no_result_total} empty`} accent="#f43f5e" />
            <MetricCard label="Documents indexed" value={data.documents_indexed.toLocaleString()} accent="#10b981" />
            <MetricCard label="Distinct sources" value={data.distinct_sources.toLocaleString()} accent="#6366f1" />
            <MetricCard label="Last ingestion" value={relativeTime(data.last_ingestion_at)} accent="#8b5cf6" />
          </section>

          <section className="two-grid">
            <article className="query-card">
              <h2>Searches over time</h2>
              <p className="muted">Per-minute search volume (last 30 min)</p>
              <Sparkline values={data.series.map((p) => p.searches)} color="#6366f1" fill="rgba(99,102,241,0.15)" />
            </article>
            <article className="query-card">
              <h2>Avg latency over time</h2>
              <p className="muted">Per-minute average search latency, ms (last 30 min)</p>
              <Sparkline values={data.series.map((p) => p.avg_latency_ms)} color="#10b981" fill="rgba(16,185,129,0.15)" unit="ms" />
            </article>
          </section>
        </>
      )}
    </main>
  );
}
