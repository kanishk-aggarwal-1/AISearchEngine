"""Shared FastAPI dependencies: auth extraction and enforcement."""

from fastapi import HTTPException, Request

from backend.app.container import logger, store
from backend.app.models import AuthUser


def bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "").strip()
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return auth.split(" ", 1)[1].strip()


def current_user(request: Request) -> AuthUser:
    token = bearer_token(request)
    user = store.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


def optional_user(request: Request) -> AuthUser | None:
    """Return the authenticated caller when a bearer token is present."""
    auth = request.headers.get("Authorization", "").strip()
    if not auth:
        return None
    return current_user(request)


def resolve_search_user(request: Request, requested_user_id: str) -> str:
    """Bind registered-user searches to the authenticated session.

    Anonymous searches share a deliberately non-account identity. Their context
    IDs are random capabilities, so they cannot address registered-user data.
    """
    caller = optional_user(request)
    if caller:
        if requested_user_id not in {"", "default", caller.user_id}:
            raise HTTPException(status_code=403, detail="Search user does not match authenticated session")
        return caller.user_id
    if requested_user_id.startswith("user_"):
        raise HTTPException(status_code=401, detail="Authentication required for this user")
    return "anonymous"


def current_admin(request: Request) -> AuthUser:
    user = current_user(request)
    if not user.is_admin:
        logger.warning("audit admin_access_denied user_id=%s path=%s", user.user_id, request.url.path)
        raise HTTPException(status_code=403, detail="Admin access required")
    logger.info("audit admin_access user_id=%s path=%s", user.user_id, request.url.path)
    return user


def require_own_user(request: Request, user_id: str) -> None:
    """Authenticate and verify the caller owns the requested user resource."""
    caller = current_user(request)
    if caller.user_id != user_id and not caller.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
