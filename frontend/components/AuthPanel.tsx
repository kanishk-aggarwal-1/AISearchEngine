"use client";

import { useEffect, useRef } from "react";
import type { AuthFormState, AuthSession, TokenPreviewResponse } from "../types/api";

interface Props {
  session: AuthSession | null;
  authMode: "login" | "register";
  setAuthMode: (mode: "login" | "register") => void;
  authForm: AuthFormState;
  setAuthForm: React.Dispatch<React.SetStateAction<AuthFormState>>;
  resetEmail: string;
  setResetEmail: (v: string) => void;
  resetToken: string;
  setResetToken: (v: string) => void;
  resetPassword: string;
  setResetPassword: (v: string) => void;
  verificationPreview: TokenPreviewResponse | null;
  resetPreview: TokenPreviewResponse | null;
  submitAuth: () => void;
  logout: () => void;
  requestVerification: () => void;
  verifyEmailFromPreview: () => void;
  requestPasswordReset: () => void;
  confirmPasswordReset: () => void;
  loginWithPasskey?: () => void;
  loginWithGoogle?: (credential: string) => void;
}

export default function AuthPanel({
  session, authMode, setAuthMode, authForm, setAuthForm,
  resetEmail, setResetEmail, resetToken, setResetToken,
  resetPassword, setResetPassword, verificationPreview, resetPreview,
  submitAuth, logout, requestVerification, verifyEmailFromPreview,
  requestPasswordReset, confirmPasswordReset,
  loginWithPasskey = () => undefined, loginWithGoogle = () => undefined,
}: Props) {
  const googleButton = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId || session) return;
    const render = () => {
      const google = (window as any).google;
      if (!google || !googleButton.current) return;
      google.accounts.id.initialize({ client_id: clientId, callback: (data: { credential: string }) => loginWithGoogle(data.credential) });
      google.accounts.id.renderButton(googleButton.current, { theme: "outline", size: "large" });
    };
    const existing = document.querySelector<HTMLScriptElement>('script[src="https://accounts.google.com/gsi/client"]');
    if (existing) { existing.addEventListener("load", render); render(); return () => existing.removeEventListener("load", render); }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.addEventListener("load", render);
    document.head.appendChild(script);
    return () => script.removeEventListener("load", render);
  }, [loginWithGoogle, session]);
  return (
    <div className="auth-shell">
      {session ? (
        <>
          <h3>{session.user.display_name}</h3>
          <p className="muted">{session.user.email}</p>
          <p className="muted">
            Role: {session.user.is_admin ? "admin" : "member"} | Email{" "}
            {session.user.email_verified ? "verified" : "unverified"}
          </p>
          <div className="card-actions">
            {!session.user.email_verified && (
              <button type="button" className="mini-button" onClick={requestVerification}>Verify email</button>
            )}
            <button type="button" className="mini-button" onClick={logout}>Sign out</button>
          </div>
          {verificationPreview?.token_preview && (
            <div className="followup-answer compact-block">
              <p className="muted">Verification preview token</p>
              <code>{verificationPreview.token_preview}</code>
              <button type="button" className="mini-button" onClick={verifyEmailFromPreview}>Use preview token</button>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="chips">
            <button type="button" className={authMode === "login" ? "chip active" : "chip"} onClick={() => setAuthMode("login")}>Login</button>
            <button type="button" className={authMode === "register" ? "chip active" : "chip"} onClick={() => setAuthMode("register")}>Register</button>
          </div>
          <input value={authForm.email} onChange={(e) => setAuthForm((p) => ({ ...p, email: e.target.value }))} placeholder="Email" />
          <input type="password" value={authForm.password} onChange={(e) => setAuthForm((p) => ({ ...p, password: e.target.value }))} placeholder="Password" />
          {authMode === "login" && <input inputMode="numeric" value={authForm.otp_code || ""} onChange={(e) => setAuthForm((p) => ({ ...p, otp_code: e.target.value }))} placeholder="Authenticator code (if enabled)" aria-label="Authenticator code" />}
          {authMode === "register" && (
            <>
              <input value={authForm.display_name} onChange={(e) => setAuthForm((p) => ({ ...p, display_name: e.target.value }))} placeholder="Display name" />
              <p className="muted auth-hint">Use at least 10 characters with uppercase, lowercase, and a number.</p>
            </>
          )}
          <button type="button" onClick={submitAuth}>{authMode === "register" ? "Create account" : "Sign in"}</button>
          {authMode === "login" && <button type="button" onClick={loginWithPasskey}>Use passkey</button>}
          <div ref={googleButton} aria-label="Google sign-in" />
        </>
      )}
      <div className="auth-helper">
        <label className="label">Password reset email</label>
        <input value={resetEmail} onChange={(e) => setResetEmail(e.target.value)} placeholder="name@example.com" />
        <div className="card-actions">
          <button type="button" className="mini-button" onClick={requestPasswordReset}>Request reset</button>
        </div>
        {resetPreview?.token_preview && (
          <>
            <input value={resetToken} onChange={(e) => setResetToken(e.target.value)} placeholder="Paste reset token or use preview" />
            <input type="password" value={resetPassword} onChange={(e) => setResetPassword(e.target.value)} placeholder="New password" />
            <p className="muted auth-hint">Reset passwords follow the same rule: 10+ chars, uppercase, lowercase, and a number.</p>
            <button type="button" className="mini-button" onClick={confirmPasswordReset}>Confirm reset</button>
          </>
        )}
      </div>
    </div>
  );
}
