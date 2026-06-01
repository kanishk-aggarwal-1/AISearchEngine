"use client";

import { useCallback, useEffect, useState } from "react";

const defaultDelivery = {
  user_id: "default",
  webhook_url: "",
  digest_mode: "daily",
  enabled: false,
};

export function usePersonalization(apiUrl, activeUserId, apiFetch, { onError, onInfo } = {}) {
  const [followEntity, setFollowEntity] = useState("");
  const [followed, setFollowed] = useState([]);
  const [alertQuery, setAlertQuery] = useState("");
  const [alerts, setAlerts] = useState([]);
  const [delivery, setDelivery] = useState(defaultDelivery);
  const [deliveryTest, setDeliveryTest] = useState(null);
  const [bookmarks, setBookmarks] = useState([]);

  const refreshFollows = useCallback(async () => {
    try {
      const r = await apiFetch(`/users/${activeUserId}/follows`);
      if (!r.ok) return;
      const data = await r.json();
      setFollowed(data.entities || []);
    } catch {
      // unauthenticated users get empty list
    }
  }, [apiFetch, activeUserId]);

  const refreshAlerts = useCallback(async () => {
    try {
      const r = await apiFetch(`/users/${activeUserId}/alerts`);
      if (!r.ok) return;
      setAlerts((await r.json()) || []);
    } catch {
      // ignore
    }
  }, [apiFetch, activeUserId]);

  const loadBookmarks = useCallback(async () => {
    try {
      const r = await apiFetch(`/users/${activeUserId}/bookmarks`);
      if (!r.ok) return;
      setBookmarks((await r.json()) || []);
    } catch {
      // ignore
    }
  }, [apiFetch, activeUserId]);

  const loadDelivery = useCallback(async () => {
    try {
      const r = await apiFetch(`/users/${activeUserId}/alert-delivery`);
      if (!r.ok) return;
      setDelivery(await r.json());
    } catch {
      // ignore
    }
  }, [apiFetch, activeUserId]);

  useEffect(() => {
    refreshFollows();
    refreshAlerts();
    loadBookmarks();
    loadDelivery();
  }, [refreshFollows, refreshAlerts, loadBookmarks, loadDelivery]);

  const addFollow = useCallback(async () => {
    if (!followEntity.trim()) return;
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
      onError?.(err.message || "Follow action failed");
    }
  }, [apiFetch, activeUserId, followEntity, onError]);

  const createAlert = useCallback(async (query, categories) => {
    const q = (typeof query === "string" ? query : alertQuery).trim();
    if (!q) return;
    try {
      const r = await apiFetch(`/users/${activeUserId}/alerts`, {
        method: "POST",
        body: JSON.stringify({ user_id: activeUserId, query: q, categories, enabled: true }),
      });
      if (!r.ok) throw new Error("Unable to create alert");
      if (typeof query !== "string") setAlertQuery("");
      await refreshAlerts();
      if (typeof query === "string") onInfo?.(`Alert created for "${q}".`);
    } catch (err) {
      onError?.(err.message || "Alert action failed");
    }
  }, [apiFetch, activeUserId, alertQuery, onError, onInfo, refreshAlerts]);

  const saveDelivery = useCallback(async () => {
    try {
      const r = await apiFetch(`/users/${activeUserId}/alert-delivery`, {
        method: "PUT",
        body: JSON.stringify({ ...delivery, user_id: activeUserId }),
      });
      if (!r.ok) throw new Error("Unable to save delivery settings");
      setDelivery(await r.json());
      onInfo?.("Alert delivery settings saved.");
    } catch (err) {
      onError?.(err.message || "Unable to save delivery settings");
    }
  }, [apiFetch, activeUserId, delivery, onError, onInfo]);

  const testDelivery = useCallback(async () => {
    try {
      const r = await apiFetch(`/users/${activeUserId}/alert-delivery/test`, { method: "POST" });
      if (!r.ok) throw new Error("Unable to test delivery");
      setDeliveryTest(await r.json());
    } catch (err) {
      onError?.(err.message || "Unable to test delivery");
    }
  }, [apiFetch, activeUserId, onError]);

  const addBookmark = useCallback(async (source) => {
    try {
      const r = await apiFetch(`/users/${activeUserId}/bookmarks`, {
        method: "POST",
        body: JSON.stringify({ user_id: activeUserId, source }),
      });
      if (!r.ok) throw new Error("Unable to save bookmark");
      await loadBookmarks();
    } catch (err) {
      onError?.(err.message || "Unable to save bookmark");
    }
  }, [apiFetch, activeUserId, onError, loadBookmarks]);

  const removeBookmark = useCallback(async (bookmarkId) => {
    try {
      const r = await apiFetch(`/users/${activeUserId}/bookmarks/${bookmarkId}`, { method: "DELETE" });
      if (r.ok) await loadBookmarks();
    } catch {
      // ignore
    }
  }, [apiFetch, activeUserId, loadBookmarks]);

  return {
    followEntity, setFollowEntity,
    followed,
    alertQuery, setAlertQuery,
    alerts,
    delivery, setDelivery,
    deliveryTest,
    bookmarks,
    refreshFollows,
    refreshAlerts,
    addFollow,
    createAlert,
    saveDelivery,
    testDelivery,
    addBookmark,
    removeBookmark,
  };
}
