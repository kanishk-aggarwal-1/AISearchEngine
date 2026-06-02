"use client";

import type { AlertRule, AuthSession, BookmarkItem, SavedSessionItem, SearchHistoryItem, SearchResponse } from "../types/api";

interface Props {
  session: AuthSession | null;
  history: SearchHistoryItem[]; onHistorySelect: (q: string) => void;
  savedSessions: SavedSessionItem[];
  sessionLabel: string; setSessionLabel: (v: string) => void;
  onSaveSession: (contextId: string | undefined, token: string | null) => void;
  result: SearchResponse | null;
  followed: string[]; alerts: AlertRule[]; bookmarks: BookmarkItem[];
}

export default function UserDashboard({ session, history, onHistorySelect, savedSessions, sessionLabel, setSessionLabel, onSaveSession, result, followed, alerts, bookmarks }: Props) {
  if (!session) return null;
  return (
    <section className="three-grid">
      <article className="query-card">
        <h2>Search History</h2>
        <div className="panel-list compact-list">
          {history.length ? history.map((item) => (
            <button type="button" key={item.id} className="history-item" onClick={() => onHistorySelect(item.query)}>
              <strong>{item.query}</strong>
              <span className="muted">{(item.categories || []).join(", ")} | {new Date(item.created_at).toLocaleString()}</span>
            </button>
          )) : <p className="muted">No saved history yet.</p>}
        </div>
      </article>
      <article className="query-card">
        <h2>Saved Sessions</h2>
        <div className="inline-row">
          <input value={sessionLabel} onChange={(e) => setSessionLabel(e.target.value)} placeholder="Label current search session" />
          <button type="button" onClick={() => onSaveSession(result?.context_id, session?.token ?? null)} disabled={!result?.context_id}>Save current</button>
        </div>
        <div className="panel-list compact-list">
          {savedSessions.length ? savedSessions.map((item) => (
            <div key={item.id} className="bookmark-item">
              <div>
                <p className="bookmark-title">{item.label || item.context_id}</p>
                <p className="muted">{item.context_id} | {new Date(item.created_at).toLocaleString()}</p>
              </div>
            </div>
          )) : <p className="muted">No saved sessions yet.</p>}
        </div>
      </article>
      <article className="query-card">
        <h2>Account Status</h2>
        <div className="stats-grid">
          <div className="stat-card"><strong>{followed.length}</strong><span>Follows</span></div>
          <div className="stat-card"><strong>{alerts.length}</strong><span>Alerts</span></div>
          <div className="stat-card"><strong>{bookmarks.length}</strong><span>Bookmarks</span></div>
          <div className="stat-card"><strong>{savedSessions.length}</strong><span>Sessions</span></div>
        </div>
      </article>
    </section>
  );
}
