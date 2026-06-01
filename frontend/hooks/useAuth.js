"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createFetch } from "../lib/api";

export function useAuth(apiUrl, { onError, onInfo } = {}) {
  const [session, setSession] = useState(null);
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState({ email: "", password: "", display_name: "" });
  const [resetEmail, setResetEmail] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [verificationPreview, setVerificationPreview] = useState(null);
  const [resetPreview, setResetPreview] = useState(null);

  const token = session?.token ?? null;
  const activeUserId = session?.user?.user_id ?? "default";

  const onExpiry = useCallback(() => {
    setSession(null);
    localStorage.removeItem("signalscope_session");
    onError?.("Your session expired. Please sign in again.");
  }, [onError]);

  const apiFetch = useMemo(
    () => createFetch(apiUrl, token, onExpiry),
    [apiUrl, token, onExpiry]
  );

  // Restore session from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem("signalscope_session");
    if (!stored) return;
    try {
      const parsed = JSON.parse(stored);
      setSession(parsed);
    } catch {
      localStorage.removeItem("signalscope_session");
    }
  }, []);

  const persistSession = useCallback((payload) => {
    setSession(payload);
    localStorage.setItem("signalscope_session", JSON.stringify(payload));
  }, []);

  const submitAuth = useCallback(async () => {
    onError?.("");
    onInfo?.("");
    try {
      const isRegister = authMode === "register";
      if (isRegister) {
        const r = await fetch(`${apiUrl}/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(authForm),
        });
        if (!r.ok) {
          const p = await r.json().catch(() => ({}));
          throw new Error(p.detail || "Unable to register");
        }
      }
      const r = await fetch(`${apiUrl}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: authForm.email, password: authForm.password }),
      });
      if (!r.ok) {
        const p = await r.json().catch(() => ({}));
        throw new Error(p.detail || "Unable to sign in");
      }
      persistSession(await r.json());
      setAuthForm((prev) => ({ ...prev, password: "" }));
      onInfo?.(isRegister ? "Account created and signed in." : "Signed in successfully.");
    } catch (err) {
      onError?.(err.message || "Authentication failed");
    }
  }, [apiUrl, authMode, authForm, onError, onInfo, persistSession]);

  const logout = useCallback(async () => {
    try {
      if (token) await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // best effort
    } finally {
      setSession(null);
      localStorage.removeItem("signalscope_session");
      onInfo?.("Signed out.");
    }
  }, [apiFetch, token, onInfo]);

  const requestVerification = useCallback(async () => {
    try {
      const r = await apiFetch("/auth/request-verification", { method: "POST" });
      if (!r.ok) throw new Error("Unable to request verification");
      setVerificationPreview(await r.json());
      onInfo?.("Verification token generated for local development.");
    } catch (err) {
      onError?.(err.message || "Unable to request verification");
    }
  }, [apiFetch, onError, onInfo]);

  const verifyEmailFromPreview = useCallback(async () => {
    if (!verificationPreview?.token_preview) return;
    try {
      const r = await fetch(`${apiUrl}/auth/verify-email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: verificationPreview.token_preview }),
      });
      if (!r.ok) throw new Error("Unable to verify email");
      const user = await r.json();
      setSession((prev) => {
        if (!prev) return prev;
        const next = { ...prev, user };
        localStorage.setItem("signalscope_session", JSON.stringify(next));
        return next;
      });
      onInfo?.("Email verified.");
    } catch (err) {
      onError?.(err.message || "Unable to verify email");
    }
  }, [apiUrl, verificationPreview, onError, onInfo]);

  const requestPasswordReset = useCallback(async () => {
    try {
      const r = await fetch(`${apiUrl}/auth/request-password-reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: resetEmail || authForm.email }),
      });
      if (!r.ok) throw new Error("Unable to request password reset");
      setResetPreview(await r.json());
      onInfo?.("Password reset token generated for local development.");
    } catch (err) {
      onError?.(err.message || "Unable to request password reset");
    }
  }, [apiUrl, resetEmail, authForm.email, onError, onInfo]);

  const confirmPasswordReset = useCallback(async () => {
    try {
      const r = await fetch(`${apiUrl}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: resetToken || resetPreview?.token_preview || "",
          new_password: resetPassword,
        }),
      });
      if (!r.ok) throw new Error("Unable to reset password");
      const p = await r.json();
      onInfo?.(p.message || "Password updated.");
      setResetPassword("");
    } catch (err) {
      onError?.(err.message || "Unable to reset password");
    }
  }, [apiUrl, resetToken, resetPreview, resetPassword, onError, onInfo]);

  return {
    session,
    token,
    activeUserId,
    apiFetch,
    authMode,
    setAuthMode,
    authForm,
    setAuthForm,
    resetEmail,
    setResetEmail,
    resetToken,
    setResetToken,
    resetPassword,
    setResetPassword,
    verificationPreview,
    resetPreview,
    submitAuth,
    logout,
    requestVerification,
    verifyEmailFromPreview,
    requestPasswordReset,
    confirmPasswordReset,
  };
}
