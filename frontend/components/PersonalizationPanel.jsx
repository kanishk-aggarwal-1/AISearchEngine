"use client";

export default function PersonalizationPanel({
  followEntity, setFollowEntity, followed, onAddFollow,
  alertQuery, setAlertQuery, alerts, onCreateAlert,
  delivery, setDelivery, deliveryTest, onSaveDelivery, onTestDelivery,
  bookmarks, onRemoveBookmark,
  activeUserId,
}) {
  return (
    <section className="three-grid">
      <article className="explanation-card">
        <h2>Personalization</h2>
        <div className="inline-row">
          <input
            value={followEntity}
            onChange={(e) => setFollowEntity(e.target.value)}
            placeholder="Follow entity (OpenAI, Lakers, NVIDIA)"
          />
          <button type="button" onClick={onAddFollow}>Add</button>
        </div>
        <p className="muted">Following: {followed.length ? followed.join(", ") : "None"}</p>
        <div className="inline-row">
          <input
            value={alertQuery}
            onChange={(e) => setAlertQuery(e.target.value)}
            placeholder="Create alert query"
          />
          <button type="button" onClick={onCreateAlert}>Save alert</button>
        </div>
        <div className="panel-list compact-list">
          {(alerts || []).slice(0, 5).map((alert, index) => (
            <div key={`${alert.query}-${index}`} className="bookmark-item">
              <div>
                <p className="bookmark-title">{alert.query}</p>
                <p className="muted">{(alert.categories || []).join(", ")}</p>
              </div>
            </div>
          ))}
        </div>
      </article>

      <article className="explanation-card">
        <h2>Alert Delivery</h2>
        <label className="label">Webhook URL</label>
        <input
          value={delivery.webhook_url || ""}
          onChange={(e) =>
            setDelivery((prev) => ({
              ...prev,
              webhook_url: e.target.value,
              user_id: activeUserId,
            }))
          }
          placeholder="https://hooks.slack.com/..."
        />
        <label className="label">Digest mode</label>
        <select
          value={delivery.digest_mode || "daily"}
          onChange={(e) =>
            setDelivery((prev) => ({
              ...prev,
              digest_mode: e.target.value,
              user_id: activeUserId,
            }))
          }
        >
          <option value="instant">instant</option>
          <option value="daily">daily</option>
        </select>
        <label className="toggle">
          <input
            type="checkbox"
            checked={Boolean(delivery.enabled)}
            onChange={(e) =>
              setDelivery((prev) => ({
                ...prev,
                enabled: e.target.checked,
                user_id: activeUserId,
              }))
            }
          />
          Delivery enabled
        </label>
        <div className="quick-actions">
          <button type="button" onClick={onSaveDelivery}>Save settings</button>
          <button type="button" onClick={onTestDelivery}>Test delivery</button>
        </div>
        {deliveryTest && (
          <p className="muted">
            {deliveryTest.preview_only
              ? "Preview generated locally."
              : `Last test status: ${deliveryTest.status_code || "error"}`}
          </p>
        )}
      </article>

      <article className="explanation-card">
        <h2>Saved Collection</h2>
        <div className="bookmark-list compact-list">
          {bookmarks.length ? (
            bookmarks.slice(0, 6).map((bookmark) => (
              <div key={bookmark.id} className="bookmark-item">
                <div>
                  <p className="source-meta">
                    {bookmark.source.source} | {bookmark.source.category}
                  </p>
                  <p className="bookmark-title">{bookmark.source.title}</p>
                </div>
                <button
                  type="button"
                  className="mini-button"
                  onClick={() => onRemoveBookmark(bookmark.id)}
                >
                  Remove
                </button>
              </div>
            ))
          ) : (
            <p className="muted">No bookmarks yet.</p>
          )}
        </div>
      </article>
    </section>
  );
}
