"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createFetch } from "../lib/api";
import type {
  AuthFormState,
  AuthSession,
  AuthUser,
  TokenPreviewResponse,
} from "../types/api";

type Callbacks = { onError?: (msg: string) => void; onInfo?: (msg: string) => void };
type ApiFetch = ReturnType<typeof createFetch>;

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string; loc?: Array<string | number> } | undefined;
    if (first?.msg) {
      const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1] || "") : "";
      return field ? `${field}: ${first.msg}` : first.msg;
    }
  }
  return fallback;
}

export function useAuth(apiUrl: string, { onError, onInfo }: Callbacks = {}) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authForm, setAuthForm] = useState<AuthFormState>({ email: "", password: "", display_name: "" });
  const [resetEmail, setResetEmail] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [verificationPreview, setVerificationPreview] = useState<TokenPreviewResponse | null>(null);
  const [resetPreview, setResetPreview] = useState<TokenPreviewResponse | null>(null);

  const token = session?.token ?? null;
  const activeUserId = session?.user?.user_id ?? "default";

  const onExpiry = useCallback(() => {
    setSession(null);
    localStorage.removeItem("signalscope_session");
    onError?.("Your session expired. Please sign in again.");
  }, [onError]);

  const apiFetch: ApiFetch = useMemo(
    () => createFetch(apiUrl, token, onExpiry),
    [apiUrl, token, onExpiry]
  );

  useEffect(() => {
    const stored = localStorage.getItem("signalscope_session");
    if (!stored) return;
    try {
      const parsed = JSON.parse(stored) as AuthSession;
      setSession(parsed);
    } catch {
      localStorage.removeItem("signalscope_session");
    }
  }, []);

  const persistSession = useCallback((payload: AuthSession) => {
    setSession(payload);
    localStorage.setItem("signalscope_session", JSON.stringify(payload));
  }, []);

  const submitAuth = useCallback(async () => {
    onError?.("");
    onInfo?.("");
    try {
      const isRegister = authMode === "register";
      if (isRegister) {
        const trimmedName = authForm.display_name.trim();
        if (trimmedName.length < 2) {
          throw new Error("Display name must be at least 2 characters long.");
        }
        if (authForm.password.length < 10) {
          throw new Error("Password must be at least 10 characters long.");
        }
        if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(authForm.password)) {
          throw new Error("Password must include at least one uppercase letter, one lowercase letter, and one number.");
        }
        const r = await fetch(`${apiUrl}/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(authForm),
        });
        if (!r.ok) {
          const p = await r.json().catch(() => ({}));
          throw new Error(extractErrorMessage(p, "Unable to register"));
        }
      }
      const r = await fetch(`${apiUrl}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: authForm.email, password: authForm.password }),
      });
      if (!r.ok) {
        const p = await r.json().catch(() => ({}));
        throw new Error(extractErrorMessage(p, "Unable to sign in"));
      }
      persistSession(await r.json() as AuthSession);
      setAuthForm((prev) => ({ ...prev, password: "", display_name: prev.display_name.trim() }));
      onInfo?.(isRegister ? "Account created and signed in." : "Signed in successfully.");
    } catch (err) {
      onError?.((err as Error).message || "Authentication failed");
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
      setVerificationPreview(await r.json() as TokenPreviewResponse);
      onInfo?.("Verification token generated for local development.");
    } catch (err) {
      onError?.((err as Error).message || "Unable to request verification");
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
      const user = await r.json() as AuthUser;
      setSession((prev) => {
        if (!prev) return prev;
        const next: AuthSession = { ...prev, user };
        localStorage.setItem("signalscope_session", JSON.stringify(next));
        return next;
      });
      onInfo?.("Email verified.");
    } catch (err) {
      onError?.((err as Error).message || "Unable to verify email");
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
      setResetPreview(await r.json() as TokenPreviewResponse);
      onInfo?.("Password reset token generated for local development.");
    } catch (err) {
      onError?.((err as Error).message || "Unable to request password reset");
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
      const p = await r.json() as { message?: string };
      onInfo?.(p.message || "Password updated.");
      setResetPassword("");
    } catch (err) {
      onError?.((err as Error).message || "Unable to reset password");
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
