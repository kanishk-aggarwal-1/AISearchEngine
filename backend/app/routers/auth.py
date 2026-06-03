from fastapi import APIRouter, HTTPException, Request

from backend.app.config import settings
from backend.app.container import email_service, login_throttle, store
from backend.app.dependencies import bearer_token, current_user
from backend.app.models import (
    AuthLoginRequest,
    AuthMessage,
    AuthRegisterRequest,
    AuthSessionResponse,
    AuthUser,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    TokenConfirmRequest,
    TokenPreviewResponse,
)

router = APIRouter(prefix="/auth")


@router.post("/register", response_model=AuthUser)
async def auth_register(payload: AuthRegisterRequest) -> AuthUser:
    try:
        return store.create_user(payload.email, payload.password, payload.display_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to register user: {exc}") from exc


@router.post("/login", response_model=AuthSessionResponse)
async def auth_login(payload: AuthLoginRequest) -> AuthSessionResponse:
    if await login_throttle.is_locked(payload.email):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(settings.login_lockout_seconds)},
        )
    session = store.authenticate_user(payload.email, payload.password)
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
        token_preview=(token if settings.email_preview_tokens or not email_sent else ""),
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
        message="Password reset token issued." if email_sent else "Password reset token issued. In local development, use the preview token directly.",
        token_preview=(token if settings.email_preview_tokens or not email_sent else ""),
        expires_at=expires_at,
        email_sent=email_sent,
        delivery_mode="smtp" if email_sent else ("preview" if settings.email_preview_tokens else "none"),
        recipient=payload.email.strip(),
    )


@router.post("/reset-password", response_model=AuthMessage)
async def auth_reset_password(payload: PasswordResetConfirmRequest) -> AuthMessage:
    result = store.reset_password(payload.token, payload.new_password)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")
    return result
