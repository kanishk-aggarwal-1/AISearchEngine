"use client";

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
}

export default function AuthPanel({
  session, authMode, setAuthMode, authForm, setAuthForm,
  resetEmail, setResetEmail, resetToken, setResetToken,
  resetPassword, setResetPassword, verificationPreview, resetPreview,
  submitAuth, logout, requestVerification, verifyEmailFromPreview,
  requestPasswordReset, confirmPasswordReset,
}: Props) {
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
          {authMode === "register" && (
            <>
              <input value={authForm.display_name} onChange={(e) => setAuthForm((p) => ({ ...p, display_name: e.target.value }))} placeholder="Display name" />
              <p className="muted auth-hint">Use at least 10 characters with uppercase, lowercase, and a number.</p>
            </>
          )}
          <button type="button" onClick={submitAuth}>{authMode === "register" ? "Create account" : "Sign in"}</button>
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
