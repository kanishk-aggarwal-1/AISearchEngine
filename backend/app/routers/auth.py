from fastapi import APIRouter, HTTPException, Request
import httpx

from backend.app.config import settings
from backend.app.container import email_service, login_throttle, passkeys, store
from backend.app.dependencies import bearer_token, current_user
from backend.app.models import (
    AuthLoginRequest,
    AuthMessage,
    AuthRegisterRequest,
    AuthSessionResponse,
    AuthUser,
    ChangePasswordRequest,
    EmailChangeRequest,
    MfaCodeRequest,
    OAuthGoogleRequest,
    PasskeyAuthenticationBeginRequest,
    PasskeyFinishRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    TokenConfirmRequest,
    TokenPreviewResponse,
    UpdateAccountRequest,
)
from backend.app.services.totp_service import generate_secret, provisioning_uri

router = APIRouter(prefix="/auth")


@router.post("/oauth/google", response_model=AuthSessionResponse)
async def auth_google(payload: OAuthGoogleRequest) -> AuthSessionResponse:
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
        response = await client.get(
            "https://oauth2.googleapis.com/tokeninfo", params={"id_token": payload.id_token}
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="Invalid Google identity token")
    claims = response.json()
    if claims.get("aud") != settings.google_oauth_client_id or claims.get("email_verified") not in {"true", True}:
        raise HTTPException(status_code=401, detail="Google identity token was not issued for this app")
    return store.oauth_session(
        "google", claims["sub"], claims["email"], claims.get("name") or claims["email"]
    )


@router.post("/passkeys/registration/options")
async def passkey_registration_options(request: Request) -> dict:
    user = current_user(request)
    return passkeys.begin_registration(user.user_id, user.email, user.display_name)


@router.post("/passkeys/registration/verify", response_model=AuthMessage)
async def passkey_registration_verify(request: Request, payload: PasskeyFinishRequest) -> AuthMessage:
    user = current_user(request)
    try:
        passkeys.finish_registration(user.user_id, payload.challenge_id, payload.credential, payload.name)
    except Exception:
        raise HTTPException(status_code=400, detail="Passkey registration could not be verified") from None
    return AuthMessage(message="Passkey registered.")


@router.post("/passkeys/authentication/options")
async def passkey_authentication_options(payload: PasskeyAuthenticationBeginRequest) -> dict:
    try:
        return passkeys.begin_authentication(str(payload.email))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/passkeys/authentication/verify", response_model=AuthSessionResponse)
async def passkey_authentication_verify(payload: PasskeyFinishRequest) -> AuthSessionResponse:
    try:
        session = passkeys.finish_authentication(payload.challenge_id, payload.credential)
    except Exception:
        raise HTTPException(status_code=401, detail="Passkey authentication failed") from None
    if not session:
        raise HTTPException(status_code=401, detail="Passkey authentication failed")
    return session


@router.post("/register", response_model=AuthUser)
async def auth_register(payload: AuthRegisterRequest) -> AuthUser:
    try:
        return store.create_user(payload.email, payload.password, payload.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to register user") from None


@router.post("/login", response_model=AuthSessionResponse)
async def auth_login(payload: AuthLoginRequest) -> AuthSessionResponse:
    if await login_throttle.is_locked(payload.email):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(settings.login_lockout_seconds)},
        )
    session = store.authenticate_user(payload.email, payload.password, payload.otp_code)
    if not session:
        await login_throttle.record_failure(payload.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    await login_throttle.reset(payload.email)
    return session


@router.get("/me", response_model=AuthUser)
async def auth_me(request: Request) -> AuthUser:
    return current_user(request)


@router.post("/logout", response_model=AuthMessage)
async def auth_logout(request: Request) -> AuthMessage:
    token = bearer_token(request)
    return store.logout_session(token)


@router.post("/request-verification", response_model=TokenPreviewResponse)
async def auth_request_verification(request: Request) -> TokenPreviewResponse:
    user = current_user(request)
    token, expires_at = store.issue_verification_token(user.user_id)
    verification_link = f"{settings.app_base_url.rstrip('/')}/verify-email?token={token}"
    email_sent = await email_service.send(
        recipient=user.email,
        subject="Verify your SignalScope AI email",
        text_body=(
            f"Hi {user.display_name},\n\n"
            f"Use this link to verify your SignalScope AI account:\n{verification_link}\n\n"
            f"This verification token expires at {expires_at}."
        ),
        html_body=(
            f"<p>Hi {user.display_name},</p>"
            f"<p>Use this link to verify your SignalScope AI account:</p>"
            f'<p><a href="{verification_link}">{verification_link}</a></p>'
            f"<p>This verification token expires at {expires_at}.</p>"
        ),
    )
    return TokenPreviewResponse(
        message="Verification token issued." if email_sent else "Verification token issued. In local development, use the preview token directly.",
        token_preview=(token if settings.email_preview_tokens else ""),
        expires_at=expires_at,
        email_sent=email_sent,
        delivery_mode="smtp" if email_sent else ("preview" if settings.email_preview_tokens else "none"),
        recipient=user.email,
    )


@router.post("/verify-email", response_model=AuthUser)
async def auth_verify_email(payload: TokenConfirmRequest) -> AuthUser:
    user = store.verify_email(payload.token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    return user


@router.post("/request-password-reset", response_model=TokenPreviewResponse)
async def auth_request_password_reset(payload: PasswordResetRequest) -> TokenPreviewResponse:
    issued = store.issue_password_reset_token(payload.email)
    if not issued:
        return TokenPreviewResponse(
            message="If the account exists, a password reset token has been issued.",
            token_preview="",
            expires_at=None,
            email_sent=False,
            delivery_mode="none",
            recipient=payload.email,
        )
    token, expires_at = issued
    reset_link = f"{settings.app_base_url.rstrip('/')}/reset-password?token={token}"
    email_sent = await email_service.send(
        recipient=payload.email.strip(),
        subject="Reset your SignalScope AI password",
        text_body=(
            "We received a request to reset your SignalScope AI password.\n\n"
            f"Use this link to continue:\n{reset_link}\n\n"
            f"This reset token expires at {expires_at}."
        ),
        html_body=(
            "<p>We received a request to reset your SignalScope AI password.</p>"
            f'<p><a href="{reset_link}">{reset_link}</a></p>'
            f"<p>This reset token expires at {expires_at}.</p>"
        ),
    )
    return TokenPreviewResponse(
        message="If the account exists, password reset instructions have been issued.",
        token_preview=(token if settings.email_preview_tokens else ""),
        expires_at=expires_at,
        email_sent=email_sent,
        delivery_mode="preview" if settings.email_preview_tokens else ("smtp" if email_sent else "none"),
        recipient=payload.email.strip(),
    )


@router.post("/reset-password", response_model=AuthMessage)
async def auth_reset_password(payload: PasswordResetConfirmRequest) -> AuthMessage:
    result = store.reset_password(payload.token, payload.new_password)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")
    return result


@router.put("/account", response_model=AuthUser)
async def auth_update_account(request: Request, payload: UpdateAccountRequest) -> AuthUser:
    user = current_user(request)
    updated = store.update_account(user.user_id, payload.display_name)
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return updated


@router.post("/change-password", response_model=AuthMessage)
async def auth_change_password(request: Request, payload: ChangePasswordRequest) -> AuthMessage:
    user = current_user(request)
    if not store.change_password(user.user_id, payload.current_password, payload.new_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    return AuthMessage(message="Password changed. Please sign in again.")


@router.post("/revoke-other-sessions", response_model=AuthMessage)
async def auth_revoke_other_sessions(request: Request) -> AuthMessage:
    user = current_user(request)
    store.revoke_other_sessions(user.user_id, bearer_token(request))
    return AuthMessage(message="Other sessions revoked.")


@router.delete("/account", response_model=AuthMessage)
async def auth_delete_account(request: Request) -> AuthMessage:
    user = current_user(request)
    store.delete_account(user.user_id)
    return AuthMessage(message="Account deleted.")


@router.post("/mfa/setup")
async def auth_mfa_setup(request: Request) -> dict:
    user = current_user(request)
    secret = generate_secret()
    store.set_mfa_secret(user.user_id, secret)
    return {"secret": secret, "provisioning_uri": provisioning_uri(secret, user.email)}


@router.post("/mfa/enable", response_model=AuthMessage)
async def auth_mfa_enable(request: Request, payload: MfaCodeRequest) -> AuthMessage:
    user = current_user(request)
    if not store.enable_mfa(user.user_id, payload.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    return AuthMessage(message="Multi-factor authentication enabled.")


@router.post("/mfa/disable", response_model=AuthMessage)
async def auth_mfa_disable(request: Request, payload: MfaCodeRequest) -> AuthMessage:
    user = current_user(request)
    if not store.disable_mfa(user.user_id, payload.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    return AuthMessage(message="Multi-factor authentication disabled.")


@router.post("/request-email-change", response_model=TokenPreviewResponse)
async def auth_request_email_change(request: Request, payload: EmailChangeRequest) -> TokenPreviewResponse:
    user = current_user(request)
    try:
        token, expires_at = store.issue_email_change_token(user.user_id, str(payload.new_email))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    link = f"{settings.app_base_url.rstrip('/')}/confirm-email-change?token={token}"
    sent = await email_service.send(
        recipient=str(payload.new_email), subject="Confirm your SignalScope AI email change",
        text_body=f"Confirm your new email address: {link}\nThis link expires at {expires_at}.",
        html_body=f'<p>Confirm your new email address:</p><p><a href="{link}">{link}</a></p>',
    )
    return TokenPreviewResponse(
        message="Email change confirmation issued.",
        token_preview=token if settings.email_preview_tokens else "",
        expires_at=expires_at, email_sent=sent,
        delivery_mode="preview" if settings.email_preview_tokens else ("smtp" if sent else "none"),
        recipient=str(payload.new_email),
    )


@router.post("/confirm-email-change", response_model=AuthUser)
async def auth_confirm_email_change(payload: TokenConfirmRequest) -> AuthUser:
    user = store.confirm_email_change(payload.token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired email-change token")
    return user


@router.get("/export")
async def auth_export(request: Request) -> dict:
    user = current_user(request)
    return store.export_user_data(user.user_id)
