import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import List
from datetime import datetime, timezone

from backend.app.config import settings
from backend.app.container import store
from backend.app.dependencies import current_user, require_own_user
from backend.app.models import (
    AlertDeliverySettings,
    AlertRule,
    BookmarkItem,
    BookmarkRequest,
    FollowRequest,
    FollowResponse,
    SavedSessionItem,
    SaveSessionRequest,
    SearchHistoryItem,
    UserProfile,
)

router = APIRouter()


# ── /users/{user_id}/* ──────────────────────────────────────────────────────

@router.get("/users/{user_id}/profile", response_model=UserProfile)
async def get_user_profile(request: Request, user_id: str) -> UserProfile:
    require_own_user(request, user_id)
    return store.get_profile(user_id)


@router.put("/users/{user_id}/profile", response_model=UserProfile)
async def put_user_profile(request: Request, user_id: str, profile: UserProfile) -> UserProfile:
    require_own_user(request, user_id)
    if profile.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.upsert_profile(profile)


@router.post("/users/{user_id}/follows", response_model=FollowResponse)
async def add_follow(request: Request, user_id: str, payload: FollowRequest) -> FollowResponse:
    require_own_user(request, user_id)
    if payload.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    entities = store.add_follow(user_id, payload.entity)
    return FollowResponse(user_id=user_id, entities=entities)


@router.get("/users/{user_id}/follows", response_model=FollowResponse)
async def get_follows(request: Request, user_id: str) -> FollowResponse:
    require_own_user(request, user_id)
    return FollowResponse(user_id=user_id, entities=store.get_follows(user_id))


@router.post("/users/{user_id}/alerts", response_model=AlertRule)
async def add_alert(request: Request, user_id: str, rule: AlertRule) -> AlertRule:
    require_own_user(request, user_id)
    if rule.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.add_alert(rule)


@router.get("/users/{user_id}/alerts", response_model=List[AlertRule])
async def get_alerts(request: Request, user_id: str) -> List[AlertRule]:
    require_own_user(request, user_id)
    return store.get_alerts(user_id)


@router.get("/users/{user_id}/alert-delivery", response_model=AlertDeliverySettings)
async def get_alert_delivery(request: Request, user_id: str) -> AlertDeliverySettings:
    require_own_user(request, user_id)
    return store.get_alert_delivery(user_id)


@router.put("/users/{user_id}/alert-delivery", response_model=AlertDeliverySettings)
async def put_alert_delivery(
    request: Request, user_id: str, payload: AlertDeliverySettings
) -> AlertDeliverySettings:
    require_own_user(request, user_id)
    if payload.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.upsert_alert_delivery(payload)


@router.post("/users/{user_id}/alert-delivery/test")
async def test_alert_delivery(request: Request, user_id: str) -> dict:
    require_own_user(request, user_id)
    delivery = store.get_alert_delivery(user_id)
    alert_rules = store.get_alerts(user_id)
    preview = {
        "user_id": user_id,
        "digest_mode": delivery.digest_mode,
        "alerts": [item.model_dump() for item in alert_rules[:5]],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if delivery.enabled and delivery.webhook_url:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
                response = await client.post(delivery.webhook_url, json=preview)
            return {"ok": response.status_code < 400, "status_code": response.status_code, "preview": preview}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "preview": preview}
    return {"ok": True, "preview_only": True, "preview": preview}


@router.post("/users/{user_id}/bookmarks", response_model=BookmarkItem)
async def add_bookmark(request: Request, user_id: str, payload: BookmarkRequest) -> BookmarkItem:
    require_own_user(request, user_id)
    if payload.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.add_bookmark(user_id, payload.source)


@router.get("/users/{user_id}/bookmarks", response_model=List[BookmarkItem])
async def get_bookmarks(request: Request, user_id: str) -> List[BookmarkItem]:
    require_own_user(request, user_id)
    return store.get_bookmarks(user_id)


@router.delete("/users/{user_id}/bookmarks/{bookmark_id}")
async def delete_bookmark(request: Request, user_id: str, bookmark_id: int) -> dict:
    require_own_user(request, user_id)
    store.delete_bookmark(user_id, bookmark_id)
    return {"ok": True}


# ── /me/* ────────────────────────────────────────────────────────────────────

@router.get("/me/search-history", response_model=List[SearchHistoryItem])
async def my_search_history(request: Request, limit: int = 25) -> List[SearchHistoryItem]:
    user = current_user(request)
    return store.get_search_history(user.user_id, limit=max(1, min(limit, 100)))


@router.get("/me/saved-sessions", response_model=List[SavedSessionItem])
async def my_saved_sessions(request: Request, limit: int = 25) -> List[SavedSessionItem]:
    user = current_user(request)
    return store.get_saved_sessions(user.user_id, limit=max(1, min(limit, 100)))


@router.post("/me/saved-sessions/{context_id}", response_model=SavedSessionItem)
async def save_my_session(
    request: Request, context_id: str, payload: SaveSessionRequest
) -> SavedSessionItem:
    user = current_user(request)
    return store.save_session(user.user_id, context_id, payload.label)


@router.get("/me/watchlist", response_model=FollowResponse)
async def my_watchlist(request: Request) -> FollowResponse:
    user = current_user(request)
    return FollowResponse(user_id=user.user_id, entities=store.get_follows(user.user_id))
