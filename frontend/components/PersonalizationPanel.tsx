"use client";

import type { AlertDeliverySettings, AlertRule, BookmarkItem, Category, SourceDoc } from "../types/api";

interface Props {
  followEntity: string; setFollowEntity: (v: string) => void;
  followed: string[]; onAddFollow: () => void; onRemoveFollow: (entity: string) => void;
  alertQuery: string; setAlertQuery: (v: string) => void;
  alerts: AlertRule[]; onCreateAlert: () => void; onDeleteAlert: (id: number) => void; onToggleAlert: (alert: AlertRule) => void;
  delivery: AlertDeliverySettings; setDelivery: React.Dispatch<React.SetStateAction<AlertDeliverySettings>>;
  deliveryTest: { ok: boolean; preview_only?: boolean; status_code?: number } | null;
  onSaveDelivery: () => void; onTestDelivery: () => void;
  bookmarks: BookmarkItem[]; onRemoveBookmark: (id: number) => void;
  bookmarkFolder: string; setBookmarkFolder: (value: string) => void;
  bookmarkTags: string; setBookmarkTags: (value: string) => void;
  bookmarkNotes: string; setBookmarkNotes: (value: string) => void;
  onUpdateBookmark: (id: number, folder: string, tags: string[], notes: string) => void;
  onLoadMoreBookmarks: () => void;
  activeUserId: string;
}

export default function PersonalizationPanel({
  followEntity, setFollowEntity, followed, onAddFollow, onRemoveFollow,
  alertQuery, setAlertQuery, alerts, onCreateAlert, onDeleteAlert, onToggleAlert,
  delivery, setDelivery, deliveryTest, onSaveDelivery, onTestDelivery,
  bookmarks, onRemoveBookmark, bookmarkFolder, setBookmarkFolder, bookmarkTags, setBookmarkTags,
  bookmarkNotes, setBookmarkNotes, onUpdateBookmark, onLoadMoreBookmarks, activeUserId,
}: Props) {
  return (
    <section className="three-grid">
      <article className="explanation-card">
        <h2>Personalization</h2>
        <div className="inline-row">
          <input value={followEntity} onChange={(e) => setFollowEntity(e.target.value)} placeholder="Follow entity (OpenAI, Lakers, NVIDIA)" />
          <button type="button" onClick={onAddFollow}>Add</button>
        </div>
        <div className="chips">{followed.length ? followed.map((entity) => (
          <button type="button" className="chip active" key={entity} onClick={() => onRemoveFollow(entity)} aria-label={`Unfollow ${entity}`}>{entity} ×</button>
        )) : <p className="muted">Following: None</p>}</div>
        <div className="inline-row">
          <input value={alertQuery} onChange={(e) => setAlertQuery(e.target.value)} placeholder="Create alert query" />
          <button type="button" onClick={onCreateAlert}>Save alert</button>
        </div>
        <div className="panel-list compact-list">
          {(alerts || []).slice(0, 5).map((alert, index) => (
            <div key={`${alert.query}-${index}`} className="bookmark-item">
              <div><p className="bookmark-title">{alert.query}</p><p className="muted">{(alert.categories || []).join(", ")}</p></div>
              <button type="button" className="mini-button" onClick={() => onToggleAlert(alert)}>{alert.enabled ? "Disable" : "Enable"}</button>
              {alert.id != null && <button type="button" className="mini-button" onClick={() => onDeleteAlert(alert.id!)}>Delete</button>}
            </div>
          ))}
        </div>
      </article>
      <article className="explanation-card">
        <h2>Alert Delivery</h2>
        <label className="label">Webhook URL</label>
        <input value={delivery.webhook_url || ""} onChange={(e) => setDelivery((p) => ({ ...p, webhook_url: e.target.value, user_id: activeUserId }))} placeholder="https://hooks.slack.com/..." />
        <label className="label">Digest mode</label>
        <select value={delivery.digest_mode || "daily"} onChange={(e) => setDelivery((p) => ({ ...p, digest_mode: e.target.value as "instant" | "daily", user_id: activeUserId }))}>
          <option value="instant">instant</option>
          <option value="daily">daily</option>
        </select>
        <label className="toggle">
          <input type="checkbox" checked={Boolean(delivery.enabled)} onChange={(e) => setDelivery((p) => ({ ...p, enabled: e.target.checked, user_id: activeUserId }))} />
          Delivery enabled
        </label>
        <label className="toggle">
          <input type="checkbox" checked={Boolean(delivery.email_enabled)} onChange={(e) => setDelivery((p) => ({ ...p, email_enabled: e.target.checked, user_id: activeUserId }))} />
          Email delivery
        </label>
        <label className="label">Timezone</label>
        <input value={delivery.timezone || "UTC"} onChange={(e) => setDelivery((p) => ({ ...p, timezone: e.target.value, user_id: activeUserId }))} placeholder="America/New_York" />
        <label className="label">Daily delivery hour</label>
        <input type="number" min={0} max={23} value={delivery.delivery_hour ?? 9} onChange={(e) => setDelivery((p) => ({ ...p, delivery_hour: Number(e.target.value), user_id: activeUserId }))} />
        <div className="quick-actions">
          <button type="button" onClick={onSaveDelivery}>Save settings</button>
          <button type="button" onClick={onTestDelivery}>Test delivery</button>
        </div>
        {deliveryTest && <p className="muted">{deliveryTest.preview_only ? "Preview generated locally." : `Last test status: ${deliveryTest.status_code || "error"}`}</p>}
      </article>
      <article className="explanation-card">
        <h2>Saved Collection</h2>
        <input aria-label="Default bookmark folder" value={bookmarkFolder} onChange={(event) => setBookmarkFolder(event.target.value)} placeholder="Folder for new bookmarks" />
        <input aria-label="Default bookmark tags" value={bookmarkTags} onChange={(event) => setBookmarkTags(event.target.value)} placeholder="Tags, comma separated" />
        <textarea aria-label="Default bookmark notes" value={bookmarkNotes} onChange={(event) => setBookmarkNotes(event.target.value)} placeholder="Notes for new bookmarks" />
        <div className="bookmark-list compact-list">
          {bookmarks.length ? bookmarks.map((bookmark) => (
            <div key={bookmark.id} className="bookmark-item">
              <div>
                <p className="source-meta">{bookmark.source.source} | {bookmark.source.category}</p>
                <p className="bookmark-title">{bookmark.source.title}</p>
                <p className="muted">{bookmark.folder || "Unfiled"}{bookmark.tags?.length ? ` | ${bookmark.tags.join(", ")}` : ""}</p>
                {bookmark.notes && <p>{bookmark.notes}</p>}
              </div>
              <button type="button" className="mini-button" onClick={() => onUpdateBookmark(bookmark.id!, bookmarkFolder, bookmarkTags.split(",").map((tag) => tag.trim()).filter(Boolean), bookmarkNotes)}>Apply metadata</button>
              <button type="button" className="mini-button" onClick={() => onRemoveBookmark(bookmark.id!)}>Remove</button>
            </div>
          )) : <p className="muted">No bookmarks yet.</p>}
        </div>
        {bookmarks.length >= 12 && <button type="button" className="mini-button" onClick={onLoadMoreBookmarks}>Load more bookmarks</button>}
      </article>
    </section>
  );
}
