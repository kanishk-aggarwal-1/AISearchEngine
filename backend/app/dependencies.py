"""Shared FastAPI dependencies: auth extraction and enforcement."""
from fastapi import HTTPException, Request

from backend.app.container import store
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


def current_admin(request: Request) -> AuthUser:
    user = current_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_own_user(request: Request, user_id: str) -> None:
    """Authenticate and verify the caller owns the requested user resource."""
    caller = current_user(request)
    if caller.user_id != user_id and not caller.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
