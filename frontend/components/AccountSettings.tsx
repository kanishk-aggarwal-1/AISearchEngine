"use client";

import { useState } from "react";
import type { AuthSession } from "../types/api";
import type { createFetch } from "../lib/api";
import { creationOptions, credentialJSON } from "../lib/passkeys";

type Props = {
  session: AuthSession | null;
  apiFetch: ReturnType<typeof createFetch>;
  onInfo: (message: string) => void;
  onError: (message: string) => void;
  onDeleted: () => void;
};

export default function AccountSettings({ session, apiFetch, onInfo, onError, onDeleted }: Props) {
  const [displayName, setDisplayName] = useState(session?.user.display_name || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaSecret, setMfaSecret] = useState("");
  if (!session) return null;

  async function updateProfile() {
    const response = await apiFetch("/auth/account", { method: "PUT", body: JSON.stringify({ display_name: displayName }) });
    response.ok ? onInfo("Account profile updated. Sign in again to refresh the header.") : onError("Unable to update account profile.");
  }

  async function changePassword() {
    const response = await apiFetch("/auth/change-password", {
      method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    if (response.ok) {
      setCurrentPassword(""); setNewPassword("");
      onInfo("Password changed. Please sign in again.");
      onDeleted();
    } else onError("Unable to change password.");
  }

  async function revokeSessions() {
    const response = await apiFetch("/auth/revoke-other-sessions", { method: "POST" });
    response.ok ? onInfo("Other sessions revoked.") : onError("Unable to revoke sessions.");
  }

  async function deleteAccount() {
    if (!window.confirm("Permanently delete your account and saved data?")) return;
    const response = await apiFetch("/auth/account", { method: "DELETE" });
    if (response.ok) { onDeleted(); onInfo("Account deleted."); }
    else onError("Unable to delete account.");
  }

  async function setupMfa() {
    const response = await apiFetch("/auth/mfa/setup", { method: "POST" });
    if (!response.ok) return onError("Unable to start MFA setup.");
    const data = await response.json() as { secret: string };
    setMfaSecret(data.secret);
    onInfo("Add the secret to your authenticator, then confirm its code.");
  }

  async function confirmMfa() {
    const response = await apiFetch("/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code: mfaCode }) });
    response.ok ? onInfo("MFA enabled. Future logins require an authenticator code.") : onError("Invalid authenticator code.");
  }

  async function requestEmailChange() {
    const response = await apiFetch("/auth/request-email-change", { method: "POST", body: JSON.stringify({ new_email: newEmail }) });
    response.ok ? onInfo("Check the new address for a confirmation link.") : onError("Unable to request email change.");
  }

  async function exportData() {
    const response = await apiFetch("/auth/export");
    if (!response.ok) return onError("Unable to export account data.");
    const blob = new Blob([JSON.stringify(await response.json(), null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a"); link.href = url; link.download = "signalscope-data.json"; link.click();
    URL.revokeObjectURL(url);
  }

  async function registerPasskey() {
    if (!window.PublicKeyCredential) return onError("This browser does not support passkeys.");
    try {
      const begin = await apiFetch("/auth/passkeys/registration/options", { method: "POST" });
      if (!begin.ok) throw new Error("Unable to start passkey registration.");
      const options = await begin.json() as { challenge_id: string; publicKey: Record<string, any> };
      const credential = await navigator.credentials.create({ publicKey: creationOptions(options.publicKey) });
      if (!credential) throw new Error("Passkey registration was cancelled.");
      const finish = await apiFetch("/auth/passkeys/registration/verify", {
        method: "POST", body: JSON.stringify({ challenge_id: options.challenge_id,
          credential: credentialJSON(credential), name: "Primary passkey" }),
      });
      if (!finish.ok) throw new Error("Passkey could not be verified.");
      onInfo("Passkey registered. You can now use it to sign in.");
    } catch (err) { onError((err as Error).message); }
  }

  return <section className="query-card">
    <h2>Account Settings</h2>
    <div className="three-grid">
      <div className="inline-row">
        <input aria-label="Display name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        <button type="button" onClick={updateProfile}>Update profile</button>
      </div>
      <div>
        <input aria-label="Current password" type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} placeholder="Current password" />
        <input aria-label="New password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} placeholder="New strong password" />
        <button type="button" onClick={changePassword}>Change password</button>
      </div>
      <div className="quick-actions">
        <button type="button" onClick={revokeSessions}>Revoke other sessions</button>
        <button type="button" className="mini-button" onClick={deleteAccount}>Delete account</button>
      </div>
      <div>
        <input aria-label="New email" type="email" value={newEmail} onChange={(event) => setNewEmail(event.target.value)} placeholder="New email address" />
        <button type="button" onClick={requestEmailChange}>Change email</button>
      </div>
      <div>
        <button type="button" onClick={setupMfa}>Set up authenticator MFA</button>
        {mfaSecret && <><code>{mfaSecret}</code><input aria-label="Authenticator confirmation code" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} placeholder="6-digit code" /><button type="button" onClick={confirmMfa}>Enable MFA</button></>}
      </div>
      <div><button type="button" onClick={exportData}>Export my data</button></div>
      <div><button type="button" onClick={registerPasskey}>Register a passkey</button></div>
    </div>
  </section>;
}
