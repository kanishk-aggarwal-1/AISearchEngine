"use client";

import { formatDateTime } from "../lib/formatters";
import type { AdminData, AuthSession, Category, SourceStatus } from "../types/api";

interface Props {
  session: AuthSession | null;
  adminData: AdminData | null;
  adminSources: SourceStatus[];
  adminLoading: boolean;
  reingestTopic: string; setReingestTopic: (v: string) => void;
  onRefresh: () => void;
  onToggleSource: (name: string, enabled: boolean, category: string) => void;
  onReingest: (categories: Category[]) => void;
  selected: Category[];
}

export default function AdminDashboard({ session, adminData, adminSources, adminLoading, reingestTopic, setReingestTopic, onRefresh, onToggleSource, onReingest, selected }: Props) {
  if (!session?.user?.is_admin) return null;
  return (
    <section className="query-card admin-panel">
      <div className="section-heading">
        <div><h2>Admin Dashboard</h2><p className="muted">Monitor source health, cache signals, and quickly disable noisy providers.</p></div>
        <button type="button" onClick={onRefresh} disabled={adminLoading}>{adminLoading ? "Refreshing..." : "Refresh admin"}</button>
      </div>
      {adminData?.snapshot && (
        <>
          <div className="stats-grid">
            {Object.entries(adminData.snapshot.counts || {}).map(([label, value]) => (
              <div key={label} className="stat-card"><strong>{value}</strong><span>{label}</span></div>
            ))}
          </div>
          <div className="three-grid admin-summary-grid">
            <div className="followup-answer">
              <h3>Source freshness</h3>
              <p className="muted">Healthy: {adminData.snapshot.source_freshness?.healthy_sources ?? 0}</p>
              <p className="muted">Stale: {adminData.snapshot.source_freshness?.stale_sources ?? 0}</p>
              <p className="muted">Errored: {adminData.snapshot.source_freshness?.errored_sources ?? 0}</p>
            </div>
            <div className="followup-answer">
              <h3>Search ops</h3>
              <p className="muted">Search calls: {adminData.metrics?.counters?.["search.calls"] ?? 0}</p>
              <p className="muted">No-result queries: {adminData.metrics?.counters?.["search.no_result"] ?? 0}</p>
              <p className="muted">Redis hits: {(adminData.metrics?.counters?.["search.cache_hit.redis"] ?? 0) + (adminData.metrics?.counters?.["search.cache_hit.sqlite"] ?? 0)}</p>
            </div>
            <div className="followup-answer">
              <h3>Manual reingest</h3>
              <div className="inline-row">
                <input value={reingestTopic} onChange={(e) => setReingestTopic(e.target.value)} placeholder="Reingest topic, e.g. AI agents" />
                <button type="button" className="mini-button" onClick={() => onReingest(selected)}>Run</button>
              </div>
              <p className="muted">Use this to refresh a topic without waiting for the scheduler.</p>
            </div>
          </div>
          <div className="followup-answer">
            <h3>Recent ingestion runs</h3>
            <div className="compact-list">
              {(adminData.snapshot.recent_ingestion_runs || []).slice(0, 6).map((run) => (
                <div key={run.id} className="bookmark-item">
                  <div>
                    <p className="bookmark-title">{run.trigger_type} | {run.query || "seed_topics"}</p>
                    <p className="muted">Status {run.status} | Inserted {run.inserted_count} | Sources {run.source_count} | Started {formatDateTime(run.started_at)}</p>
                    {run.error_message && <p className="error inline-error">{run.error_message}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
      <div className="panel-list compact-list">
        {adminSources.map((item) => (
          <div key={item.source_name} className="source-admin-row">
            <div>
              <p className="bookmark-title">{item.source_name}</p>
              <p className="muted">{item.category} | Last items: {item.last_item_count} | Success {item.success_count} | Failures {item.failure_count} | Avg latency {item.average_latency_ms ? `${Math.round(item.average_latency_ms)} ms` : "n/a"}</p>
              <p className="muted">Attempted: {formatDateTime(item.last_attempt_at)} | Updated: {formatDateTime(item.updated_at)}</p>
              {item.last_error && <p className="error inline-error">{item.last_error}</p>}
            </div>
            <button type="button" className={item.enabled ? "mini-button" : "mini-button active-mini"} onClick={() => onToggleSource(item.source_name, !item.enabled, item.category)}>{item.enabled ? "Disable" : "Enable"}</button>
          </div>
        ))}
      </div>
    </section>
  );
}
