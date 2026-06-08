"use client";

import { useCallback, useEffect, useState } from "react";
import type { AlertDeliverySettings, AlertRule, BookmarkItem, Category, SourceDoc } from "../types/api";
import type { createFetch } from "../lib/api";

type ApiFetch = ReturnType<typeof createFetch>;
type Callbacks = { onError?: (msg: string) => void; onInfo?: (msg: string) => void };

const defaultDelivery: AlertDeliverySettings = {
  user_id: "default",
  webhook_url: "",
  digest_mode: "daily",
  enabled: false,
};

export function usePersonalization(
  apiUrl: string,
  activeUserId: string,
  isAuthenticated: boolean,
  apiFetch: ApiFetch,
  { onError, onInfo }: Callbacks = {}
) {
  const [followEntity, setFollowEntity] = useState("");
  const [followed, setFollowed] = useState<string[]>([]);
  const [alertQuery, setAlertQuery] = useState("");
  const [alerts, setAlerts] = useState<AlertRule[]>([]);
  const [delivery, setDelivery] = useState<AlertDeliverySettings>(defaultDelivery);
  const [deliveryTest, setDeliveryTest] = useState<{ ok: boolean; preview_only?: boolean; status_code?: number } | null>(null);
  const [bookmarks, setBookmarks] = useState<BookmarkItem[]>([]);

  /**
   * Returns true when the user is signed in.
   * For mutation callbacks, pass an error message — it will be surfaced via
   * onError so the user knows why the action was blocked.
   * For read/refresh callbacks, omit the message to fail silently and clear state.
   */
  const requireAuth = useCallback(
    (errorMsg?: string): boolean => {
      if (isAuthenticated) return true;
      if (errorMsg) onError?.(errorMsg);
      return false;
    },
    [isAuthenticated, onError]
  );

  const refreshFollows = useCallback(async () => {
    if (!requireAuth()) {
      setFollowed([]);
      return;
    }
    try {
      const r = await apiFetch(`/users/${activeUserId}/follows`);
      if (!r.ok) return;
      const data = await r.json();
      setFollowed(data.entities || []);
    } catch { /* unauthenticated users get empty list */ }
  }, [apiFetch, activeUserId, requireAuth]);

  const refreshAlerts = useCallback(async () => {
    if (!requireAuth()) {
      setAlerts([]);
      return;
    }
    try {
      const r = await apiFetch(`/users/${activeUserId}/alerts`);
      if (!r.ok) return;
      setAlerts((await r.json() as AlertRule[]) || []);
    } catch { /* ignore */ }
  }, [apiFetch, activeUserId, requireAuth]);

  const loadBookmarks = useCallback(async () => {
    if (!requireAuth()) {
      setBookmarks([]);
      return;
    }
    try {
      const r = await apiFetch(`/users/${activeUserId}/bookmarks`);
      if (!r.ok) return;
      setBookmarks((await r.json() as BookmarkItem[]) || []);
    } catch { /* ignore */ }
  }, [apiFetch, activeUserId, requireAuth]);

  const loadDelivery = useCallback(async () => {
    if (!requireAuth()) {
      setDelivery({ ...defaultDelivery, user_id: activeUserId });
      return;
    }
    try {
      const r = await apiFetch(`/users/${activeUserId}/alert-delivery`);
      if (!r.ok) return;
      setDelivery(await r.json() as AlertDeliverySettings);
    } catch { /* ignore */ }
  }, [apiFetch, activeUserId, requireAuth]);

  useEffect(() => {
    refreshFollows();
    refreshAlerts();
    loadBookmarks();
    loadDelivery();
  }, [refreshFollows, refreshAlerts, loadBookmarks, loadDelivery]);

  const addFollow = useCallback(async () => {
    if (!followEntity.trim()) return;
    if (!requireAuth("Please sign in before following topics.")) return;
    try {
      const r = await apiFetch(`/users/${activeUserId}/follows`, {
        method: "POST",
        body: JSON.stringify({ user_id: activeUserId, entity: followEntity.trim() }),
      });
      if (!r.ok) throw new Error("Unable to add follow");
      const data = await r.json();
      setFollowed(data.entities || []);
      setFollowEntity("");
    } catch (err) {
      onError?.((err as Error).message || "Follow action failed");
    }
  }, [apiFetch, activeUserId, followEntity, requireAuth, onError]);

  const createAlert = useCallback(async (query: string, categories: Category[]) => {
    const q = (typeof query === "string" ? query : alertQuery).trim();
    if (!q) return;
    if (!requireAuth("Please sign in before creating alerts.")) return;
    try {
      const r = await apiFetch(`/users/${activeUserId}/alerts`, {
        method: "POST",
        body: JSON.stringify({ user_id: activeUserId, query: q, categories, enabled: true }),
      });
      if (!r.ok) throw new Error("Unable to create alert");
      if (query === alertQuery) setAlertQuery("");
      await refreshAlerts();
      onInfo?.(`Alert created for "${q}".`);
    } catch (err) {
      onError?.((err as Error).message || "Alert action failed");
    }
  }, [apiFetch, activeUserId, alertQuery, requireAuth, onError, onInfo, refreshAlerts]);

  const saveDelivery = useCallback(async () => {
    if (!requireAuth("Please sign in before saving delivery settings.")) return;
    try {
      const r = await apiFetch(`/users/${activeUserId}/alert-delivery`, {
        method: "PUT",
        body: JSON.stringify({ ...delivery, user_id: activeUserId }),
      });
      if (!r.ok) throw new Error("Unable to save delivery settings");
      setDelivery(await r.json() as AlertDeliverySettings);
      onInfo?.("Alert delivery settings saved.");
    } catch (err) {
      onError?.((err as Error).message || "Unable to save delivery settings");
    }
  }, [apiFetch, activeUserId, delivery, requireAuth, onError, onInfo]);

  const testDelivery = useCallback(async () => {
    if (!requireAuth("Please sign in before testing alert delivery.")) return;
    try {
      const r = await apiFetch(`/users/${activeUserId}/alert-delivery/test`, { method: "POST" });
      if (!r.ok) throw new Error("Unable to test delivery");
      setDeliveryTest(await r.json());
    } catch (err) {
      onError?.((err as Error).message || "Unable to test delivery");
    }
  }, [apiFetch, activeUserId, requireAuth, onError]);

  const addBookmark = useCallback(async (source: SourceDoc) => {
    if (!requireAuth("Please sign in before saving bookmarks.")) return;
    try {
      const r = await apiFetch(`/users/${activeUserId}/bookmarks`, {
        method: "POST",
        body: JSON.stringify({ user_id: activeUserId, source }),
      });
      if (!r.ok) throw new Error("Unable to save bookmark");
      await loadBookmarks();
    } catch (err) {
      onError?.((err as Error).message || "Unable to save bookmark");
    }
  }, [apiFetch, activeUserId, requireAuth, onError, loadBookmarks]);

  const removeBookmark = useCallback(async (bookmarkId: number) => {
    if (!requireAuth()) return;
    try {
      const r = await apiFetch(`/users/${activeUserId}/bookmarks/${bookmarkId}`, { method: "DELETE" });
      if (r.ok) await loadBookmarks();
    } catch { /* ignore */ }
  }, [apiFetch, activeUserId, requireAuth, loadBookmarks]);

  return {
    followEntity, setFollowEntity, followed,
    alertQuery, setAlertQuery, alerts,
    delivery, setDelivery, deliveryTest,
    bookmarks,
    refreshFollows, refreshAlerts,
    addFollow, createAlert, saveDelivery, testDelivery, addBookmark, removeBookmark,
  };
}
