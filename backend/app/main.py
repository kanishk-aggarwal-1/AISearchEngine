import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.models import (
    AlertDeliverySettings,
    AlertRule,
    AppliedFilters,
    AuthLoginRequest,
    AuthMessage,
    AuthRegisterRequest,
    AuthSessionResponse,
    AuthUser,
    BookmarkItem,
    BookmarkRequest,
    Category,
    CompareRequest,
    FollowRequest,
    FollowResponse,
    FollowUpRequest,
    FollowUpResponse,
    IngestionRunRecord,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    SavedSessionItem,
    SaveSessionRequest,
    SearchRequest,
    SearchHistoryItem,
    SearchResponse,
    SourceStatus,
    SourceToggleRequest,
    SourceDoc,
    TokenConfirmRequest,
    TokenPreviewResponse,
    UserProfile,
)
from backend.app.services.alert_service import AlertService
from backend.app.services.cache_service import CacheService
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.email_service import EmailService
from backend.app.services.enrichment_service import EnrichmentService
from backend.app.services.explainer import ExplainerService
from backend.app.services.ingestion import IngestionService
from backend.app.services.logging_service import get_logger, setup_logging
from backend.app.services.observability_service import MetricsService
from backend.app.services.retriever import RetrieverService
from backend.app.services.scheduler import SchedulerService
from backend.app.services.source_registry import SourceRegistry
from backend.app.services.store_factory import create_store
from backend.app.services.vector_index_service import VectorIndexService


class IngestEventRequest(BaseModel):
    topic: str = Field(min_length=2)
    categories: List[Category] = Field(default_factory=lambda: ["tech", "research", "sports", "general"])


class ResearchExplainRequest(BaseModel):
    source: SourceDoc
    explanation_mode: str = "beginner"


class ResearchCompareRequest(BaseModel):
    left: SourceDoc
    right: SourceDoc


setup_logging()
logger = get_logger("signalscope.api")
metrics = MetricsService()
RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
ALLOWED_ORIGINS = [settings.frontend_origin, *[item.strip() for item in settings.extra_frontend_origins.split(",") if item.strip()]]

app = FastAPI(title="AI Search Retriever", version="0.7.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = create_store()
cache = CacheService()
registry = SourceRegistry(store)
enricher = EnrichmentService()
embedding_service = EmbeddingService()
retriever = RetrieverService(embedding_service)
explainer = ExplainerService()
vector_index = VectorIndexService()
ingestion = IngestionService(registry, store, enricher, settings.max_fetch_per_source)
alerts = AlertService(store, metrics=metrics)
scheduler = SchedulerService(ingestion, settings.scheduler_interval_minutes, alerts=alerts)
email_service = EmailService()


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if not settings.enable_metrics:
        return await call_next(request)

    start = time.perf_counter()
    path = request.url.path
    method = request.method
    metrics.inc("http.requests_total")
    metrics.inc(f"http.requests.{method}.{path}")

    try:
        response = await call_next(request)
        metrics.inc(f"http.responses.{response.status_code}")
    except Exception as exc:
        metrics.inc("http.errors_total")
        logger.exception("request_failed method=%s path=%s error=%s", method, path, exc)
        raise
    finally:
        elapsed = time.perf_counter() - start
        metrics.observe("http.request_latency", elapsed)
        metrics.observe(f"http.request_latency.{method}.{path}", elapsed)

    return response


def _security_headers(response: JSONResponse | None = None) -> dict:
    return {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "Cache-Control": "no-store",
    }


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    import random

    client_host = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - 60
    bucket = [stamp for stamp in RATE_LIMIT_BUCKETS.get(client_host, []) if stamp >= window_start]

    # Probabilistically prune IPs that haven't been seen in the last window
    if random.random() < 0.01:
        stale_ips = [ip for ip, stamps in RATE_LIMIT_BUCKETS.items() if not stamps or max(stamps) < window_start]
        for ip in stale_ips:
            del RATE_LIMIT_BUCKETS[ip]

    if len(bucket) >= settings.rate_limit_per_minute:
        metrics.inc("http.rate_limited")
        return JSONResponse(
            {"detail": "Rate limit exceeded. Please retry shortly."},
            status_code=429,
            headers=_security_headers(),
        )
    bucket.append(now)
    RATE_LIMIT_BUCKETS[client_host] = bucket

    response = await call_next(request)
    for header, value in _security_headers().items():
        response.headers[header] = value
    return response


@app.on_event("startup")
async def startup_event() -> None:
    await scheduler.start()
    logger.info(
        "startup_complete vector_enabled=%s real_embeddings=%s strict_real_embeddings=%s cache_backend=%s redis_enabled=%s",
        vector_index.enabled,
        embedding_service.real_embeddings_enabled,
        settings.strict_real_embeddings,
        settings.cache_backend,
        cache.using_redis,
    )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await scheduler.stop()
    await cache.close()


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "max_fetch_per_source": settings.max_fetch_per_source,
        "openai_enabled": bool(settings.openai_api_key),
        "gemini_enabled": bool(settings.gemini_api_key),
        "real_embeddings_enabled": embedding_service.real_embeddings_enabled,
        "strict_real_embeddings": settings.strict_real_embeddings,
        "newsapi_enabled": bool(settings.newsapi_key),
        "db_path": settings.db_path,
        "scheduler_interval_minutes": settings.scheduler_interval_minutes,
        "embedding_model": settings.embedding_model,
        "vector_backend": settings.vector_backend,
        "vector_enabled": vector_index.enabled,
        "metrics_enabled": settings.enable_metrics,
        "cache_backend": settings.cache_backend,
        "redis_enabled": cache.using_redis,
        "redis_connected": await cache.ping() if cache.using_redis else False,
    }


@app.get("/health/deep")
async def deep_health() -> dict:
    db_ok = store.ping()
    redis_ok = await cache.ping() if cache.using_redis else False
    vector_status = await vector_index.health()
    last_ingestion_at = store.last_successful_ingestion_at()

    llm_components = {
        "gemini": {
            "configured": bool(settings.gemini_api_key),
            "status": "configured" if settings.gemini_api_key else "unconfigured",
        },
        "openai": {
            "configured": bool(settings.openai_api_key),
            "status": "configured" if settings.openai_api_key else "unconfigured",
        },
        "fallback_explainer": {
            "configured": True,
            "status": "ready",
        },
    }

    components = {
        "api": {"status": "ok", "app_name": settings.app_name if hasattr(settings, "app_name") else "SignalScope AI"},
        "database": {
            "status": "ok" if db_ok else "degraded",
            "backend": "postgres" if settings.using_postgres else "sqlite",
            "database_url_configured": bool(settings.database_url.strip()),
            "sqlite_path": settings.sqlite_database_path,
        },
        "cache": {
            "status": "ok" if redis_ok else ("disabled" if not cache.using_redis else "degraded"),
            "backend": settings.cache_backend,
            "redis_enabled": cache.using_redis,
            "redis_connected": redis_ok,
        },
        "llm": {
            "status": "ok" if (settings.gemini_api_key or settings.openai_api_key) else "degraded",
            "providers": llm_components,
            "real_embeddings_enabled": embedding_service.real_embeddings_enabled,
        },
        "vector": vector_status,
        "ingestion": {
            "status": "ok" if last_ingestion_at else "degraded",
            "last_successful_ingestion_at": last_ingestion_at,
        },
    }

    overall_ok = db_ok and (redis_ok or not cache.using_redis)

    return {
        "ok": overall_ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }


@app.get("/metrics")
async def get_metrics() -> JSONResponse:
    return JSONResponse(
        {
            **metrics.snapshot(),
            "source_freshness": store.source_freshness_summary(),
            "last_successful_ingestion_at": store.last_successful_ingestion_at(),
        }
    )


@app.get("/metrics/prometheus")
async def get_metrics_prometheus() -> PlainTextResponse:
    lines = [metrics.as_prometheus_text().rstrip()]
    freshness = store.source_freshness_summary()
    for key, value in freshness.items():
        metric = f"signalscope_source_freshness_{key}"
        lines.append(f"{metric} {value}")
    last_ingestion = store.last_successful_ingestion_at()
    if last_ingestion:
        try:
            ts = datetime.fromisoformat(last_ingestion).timestamp()
        except Exception:
            ts = 0.0
    else:
        ts = 0.0
    lines.append(f"signalscope_ingestion_last_successful_timestamp {ts}")
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.get("/admin/dashboard")
async def admin_dashboard(request: Request, limit: int = 10) -> dict:
    _current_admin(request)
    return {
        "snapshot": store.admin_snapshot(limit=max(1, min(limit, 50))),
        "metrics": metrics.snapshot(),
    }


@app.get("/admin/sources", response_model=List[SourceStatus])
async def admin_sources(request: Request, category: Category | None = None) -> List[SourceStatus]:
    _current_admin(request)
    return store.get_source_statuses(category=category)


@app.put("/admin/sources/{source_name}", response_model=SourceStatus)
async def admin_toggle_source(request: Request, source_name: str, payload: SourceToggleRequest, category: str = "unknown") -> SourceStatus:
    _current_admin(request)
    return store.set_source_enabled(source_name, payload.enabled, category=category)


@app.get("/admin/ingestion-runs", response_model=List[IngestionRunRecord])
async def admin_ingestion_runs(request: Request, limit: int = 20) -> List[IngestionRunRecord]:
    _current_admin(request)
    return store.recent_ingestion_runs(limit=max(1, min(limit, 100)))


@app.post("/admin/reingest")
async def admin_reingest(request: Request, payload: IngestEventRequest) -> dict:
    _current_admin(request)
    start = time.perf_counter()
    inserted = await ingestion.ingest_event(payload.topic, payload.categories)
    metrics.inc("ingestion.reingest.calls")
    metrics.observe("ingestion.reingest.latency", time.perf_counter() - start)
    metrics.inc("ingestion.documents_inserted", inserted)
    return {"ok": True, "inserted": inserted, "topic": payload.topic, "categories": payload.categories}


@app.post("/ingest/run")
async def run_ingestion(request: Request) -> dict:
    _current_admin(request)
    start = time.perf_counter()
    inserted = await ingestion.ingest_seed_topics()
    metrics.inc("ingestion.run.calls")
    metrics.observe("ingestion.run.latency", time.perf_counter() - start)
    metrics.inc("ingestion.documents_inserted", inserted)
    return {"ok": True, "inserted": inserted}


@app.post("/ingest/webhook")
async def ingest_webhook(request: Request, payload: IngestEventRequest) -> dict:
    _current_admin(request)
    start = time.perf_counter()
    inserted = await ingestion.ingest_event(payload.topic, payload.categories)
    metrics.inc("ingestion.webhook.calls")
    metrics.observe("ingestion.webhook.latency", time.perf_counter() - start)
    metrics.inc("ingestion.documents_inserted", inserted)
    return {"ok": True, "inserted": inserted, "topic": payload.topic}


def _require_own_user(request: Request, user_id: str) -> None:
    """Authenticate the request and enforce that the caller owns the resource."""
    caller = _current_user(request)
    if caller.user_id != user_id and not caller.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")


@app.get("/users/{user_id}/profile", response_model=UserProfile)
async def get_user_profile(request: Request, user_id: str) -> UserProfile:
    _require_own_user(request, user_id)
    return store.get_profile(user_id)


@app.put("/users/{user_id}/profile", response_model=UserProfile)
async def put_user_profile(request: Request, user_id: str, profile: UserProfile) -> UserProfile:
    _require_own_user(request, user_id)
    if profile.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.upsert_profile(profile)


@app.post("/users/{user_id}/follows", response_model=FollowResponse)
async def add_follow(request: Request, user_id: str, payload: FollowRequest) -> FollowResponse:
    _require_own_user(request, user_id)
    if payload.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    entities = store.add_follow(user_id, payload.entity)
    return FollowResponse(user_id=user_id, entities=entities)


@app.get("/users/{user_id}/follows", response_model=FollowResponse)
async def get_follows(request: Request, user_id: str) -> FollowResponse:
    _require_own_user(request, user_id)
    return FollowResponse(user_id=user_id, entities=store.get_follows(user_id))


@app.post("/users/{user_id}/alerts", response_model=AlertRule)
async def add_alert(request: Request, user_id: str, rule: AlertRule) -> AlertRule:
    _require_own_user(request, user_id)
    if rule.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.add_alert(rule)


@app.get("/users/{user_id}/alerts", response_model=List[AlertRule])
async def get_alerts(request: Request, user_id: str) -> List[AlertRule]:
    _require_own_user(request, user_id)
    return store.get_alerts(user_id)


@app.get("/users/{user_id}/alert-delivery", response_model=AlertDeliverySettings)
async def get_alert_delivery(request: Request, user_id: str) -> AlertDeliverySettings:
    _require_own_user(request, user_id)
    return store.get_alert_delivery(user_id)


@app.put("/users/{user_id}/alert-delivery", response_model=AlertDeliverySettings)
async def put_alert_delivery(request: Request, user_id: str, payload: AlertDeliverySettings) -> AlertDeliverySettings:
    _require_own_user(request, user_id)
    if payload.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.upsert_alert_delivery(payload)


@app.post("/users/{user_id}/alert-delivery/test")
async def test_alert_delivery(request: Request, user_id: str) -> dict:
    _require_own_user(request, user_id)
    delivery = store.get_alert_delivery(user_id)
    alerts = store.get_alerts(user_id)
    preview = {
        "user_id": user_id,
        "digest_mode": delivery.digest_mode,
        "alerts": [item.model_dump() for item in alerts[:5]],
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


@app.post("/users/{user_id}/bookmarks", response_model=BookmarkItem)
async def add_bookmark(request: Request, user_id: str, payload: BookmarkRequest) -> BookmarkItem:
    _require_own_user(request, user_id)
    if payload.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.add_bookmark(user_id, payload.source)


@app.get("/users/{user_id}/bookmarks", response_model=List[BookmarkItem])
async def get_bookmarks(request: Request, user_id: str) -> List[BookmarkItem]:
    _require_own_user(request, user_id)
    return store.get_bookmarks(user_id)


@app.delete("/users/{user_id}/bookmarks/{bookmark_id}")
async def delete_bookmark(request: Request, user_id: str, bookmark_id: int) -> dict:
    _require_own_user(request, user_id)
    store.delete_bookmark(user_id, bookmark_id)
    return {"ok": True}


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "").strip()
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return auth.split(" ", 1)[1].strip()


def _current_user(request: Request) -> AuthUser:
    token = _bearer_token(request)
    user = store.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


def _current_admin(request: Request) -> AuthUser:
    user = _current_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@app.post("/auth/register", response_model=AuthUser)
async def auth_register(payload: AuthRegisterRequest) -> AuthUser:
    try:
        return store.create_user(payload.email, payload.password, payload.display_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to register user: {exc}")


@app.post("/auth/login", response_model=AuthSessionResponse)
async def auth_login(payload: AuthLoginRequest) -> AuthSessionResponse:
    session = store.authenticate_user(payload.email, payload.password)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return session


@app.get("/auth/me", response_model=AuthUser)
async def auth_me(request: Request) -> AuthUser:
    return _current_user(request)


@app.post("/auth/logout", response_model=AuthMessage)
async def auth_logout(request: Request) -> AuthMessage:
    token = _bearer_token(request)
    return store.logout_session(token)


@app.post("/auth/request-verification", response_model=TokenPreviewResponse)
async def auth_request_verification(request: Request) -> TokenPreviewResponse:
    user = _current_user(request)
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
            f"<p><a href=\"{verification_link}\">{verification_link}</a></p>"
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


@app.post("/auth/verify-email", response_model=AuthUser)
async def auth_verify_email(payload: TokenConfirmRequest) -> AuthUser:
    user = store.verify_email(payload.token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    return user


@app.post("/auth/request-password-reset", response_model=TokenPreviewResponse)
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
            f"<p><a href=\"{reset_link}\">{reset_link}</a></p>"
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


@app.post("/auth/reset-password", response_model=AuthMessage)
async def auth_reset_password(payload: PasswordResetConfirmRequest) -> AuthMessage:
    result = store.reset_password(payload.token, payload.new_password)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")
    return result


@app.get("/me/search-history", response_model=List[SearchHistoryItem])
async def my_search_history(request: Request, limit: int = 25) -> List[SearchHistoryItem]:
    user = _current_user(request)
    return store.get_search_history(user.user_id, limit=max(1, min(limit, 100)))


@app.get("/me/saved-sessions", response_model=List[SavedSessionItem])
async def my_saved_sessions(request: Request, limit: int = 25) -> List[SavedSessionItem]:
    user = _current_user(request)
    return store.get_saved_sessions(user.user_id, limit=max(1, min(limit, 100)))


@app.post("/me/saved-sessions/{context_id}", response_model=SavedSessionItem)
async def save_my_session(request: Request, context_id: str, payload: SaveSessionRequest) -> SavedSessionItem:
    user = _current_user(request)
    return store.save_session(user.user_id, context_id, payload.label)


@app.get("/me/watchlist", response_model=FollowResponse)
async def my_watchlist(request: Request) -> FollowResponse:
    user = _current_user(request)
    return FollowResponse(user_id=user.user_id, entities=store.get_follows(user.user_id))


def _apply_search_filters(docs: List[SourceDoc], payload: SearchRequest) -> List[SourceDoc]:
    filtered = docs
    if payload.recency_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=payload.recency_days)
        filtered = [
            doc for doc in filtered
            if doc.published_at and (doc.published_at if doc.published_at.tzinfo else doc.published_at.replace(tzinfo=timezone.utc)) >= cutoff
        ]
    if payload.source_filter:
        wanted = {item.lower() for item in payload.source_filter if item.strip()}
        filtered = [doc for doc in filtered if doc.source.lower() in wanted]
    if payload.source_type_filter:
        allowed = set(payload.source_type_filter)
        filtered = [doc for doc in filtered if doc.source_type in allowed]
    return filtered


def _sort_docs(docs: List[SourceDoc], sort_by: str) -> List[SourceDoc]:
    if sort_by == "latest":
        return sorted(
            docs,
            key=lambda item: (
                item.published_at.isoformat() if item.published_at else "",
                item.credibility_score,
            ),
            reverse=True,
        )
    return sorted(docs, key=lambda item: item.total_score, reverse=True)


def _topic_summary(docs: List[SourceDoc]) -> List[str]:
    counter = Counter()
    for doc in docs[:20]:
        for tag in doc.entity_tags[:4]:
            if len(tag) >= 3:
                counter[tag] += 1
    return [item for item, _ in counter.most_common(8)]


def _filter_recent_docs(docs: List[SourceDoc], recency_days: int) -> List[SourceDoc]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, recency_days))
    filtered = []
    for doc in docs:
        if not doc.published_at:
            continue
        published = doc.published_at if doc.published_at.tzinfo else doc.published_at.replace(tzinfo=timezone.utc)
        if published >= cutoff:
            filtered.append(doc)
    return filtered


def _trending_payload(categories: List[Category], recency_days: int = 7, limit: int = 10) -> dict:
    docs = _filter_recent_docs(store.all_recent_documents(categories, limit=200), recency_days)
    topic_counter = Counter()
    for doc in docs:
        for tag in doc.entity_tags[:5]:
            if len(tag) >= 3:
                topic_counter[tag] += 1
    return {
        "categories": categories,
        "recency_days": recency_days,
        "topics": [{"topic": topic, "count": count} for topic, count in topic_counter.most_common(limit)],
        "sample_sources": [doc.model_dump(mode="json") for doc in docs[: min(limit, 8)]],
    }


def _headline_cache_key(category: str, limit: int, recency_days: int) -> str:
    return f"{category}:{limit}:{recency_days}"


def _suggested_queries(payload: SearchRequest) -> List[str]:
    raw = payload.query.strip()
    tokens = [token for token in raw.split() if token.lower() not in {"latest", "news", "what", "happening", "today", "this", "week"}]
    compact = " ".join(tokens).strip() or raw
    suggestions: List[str] = []

    if payload.source_filter or payload.source_type_filter:
        suggestions.append(f"{compact} without source filters")
    if payload.recency_days is not None and payload.recency_days <= 7:
        suggestions.append(f"{compact} in the last 30 days")
    if "latest" not in raw.lower():
        suggestions.append(f"latest {compact}")
    if "research" in payload.categories:
        suggestions.append(f"{compact} research papers")
    if "sports" in payload.categories:
        suggestions.append(f"{compact} latest scores")
    if "general" in payload.categories:
        suggestions.append(f"{compact} world news")

    unique: List[str] = []
    seen = set()
    for item in suggestions:
        clean = " ".join(item.split()).strip()
        if clean and clean.lower() not in seen and clean.lower() != raw.lower():
            seen.add(clean.lower())
            unique.append(clean)
    return unique[:4]


async def _latest_headlines_for_category(category: Category, limit: int, recency_days: int = 7) -> List[dict]:
    seed_queries = {
        "tech": [""],
        "research": ["AI", "machine learning"],
        "sports": ["NBA", "NFL", "MLB", "Premier League"],
        "general": [""],
    }
    queries = seed_queries.get(category, [""])
    fetch_limit = max(limit * 3, settings.max_fetch_per_source)
    cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)

    live_docs: List[SourceDoc] = []
    for seed_query in queries:
        live_docs.extend(await registry.gather(seed_query, [category], fetch_limit))
    live_docs = enricher.enrich(queries[0] or category, live_docs)
    if live_docs:
        store.upsert_documents(live_docs)

    recent_docs = store.all_recent_documents([category], limit=max(limit * 6, 24))
    merged_docs: dict[str, SourceDoc] = {}
    for doc in [*live_docs, *recent_docs]:
        key = store.canonicalize_url(doc.url, doc.source, doc.title)
        if key not in merged_docs:
            merged_docs[key] = doc

    docs = enricher.enrich(queries[0] or category, list(merged_docs.values()))
    fresh_docs = []
    for doc in docs:
        if not doc.published_at:
            continue
        published_at = doc.published_at if doc.published_at.tzinfo else doc.published_at.replace(tzinfo=timezone.utc)
        if published_at >= cutoff:
            fresh_docs.append(doc)

    fresh_docs = sorted(fresh_docs, key=lambda item: item.published_at.isoformat() if item.published_at else "", reverse=True)
    return [doc.model_dump(mode="json") for doc in fresh_docs[:limit]]


@app.get("/headlines")
async def headlines(per_category: int = 4, recency_days: int = 7) -> dict:
    limit = max(1, min(per_category, 8))
    recency = max(1, min(recency_days, 30))
    cache_key = _headline_cache_key("all", limit, recency)
    cached = await cache.get("headlines", cache_key)
    if cached:
        metrics.inc("headlines.cache_hit")
        return json.loads(cached)

    categories: List[Category] = ["tech", "research", "sports", "general"]
    payload = {}
    for category in categories:
        payload[category] = await _latest_headlines_for_category(category, limit, recency)
    response = {"updated_at": datetime.now(timezone.utc).isoformat(), "categories": payload, "recency_days": recency}
    await cache.set_json("headlines", cache_key, response, max(5, min(recency * 60, 180)))
    return response


@app.get("/headlines/{category}")
async def headlines_by_category(category: Category, limit: int = 10, recency_days: int = 7) -> dict:
    normalized_limit = max(1, min(limit, 20))
    normalized_recency = max(1, min(recency_days, 30))
    cache_key = _headline_cache_key(category, normalized_limit, normalized_recency)
    cached = await cache.get("headline_category", cache_key)
    if cached:
        metrics.inc("headlines.category_cache_hit")
        return json.loads(cached)

    items = await _latest_headlines_for_category(category, normalized_limit, normalized_recency)
    docs = [SourceDoc.model_validate(item) for item in items]
    response = {
        "category": category,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "headlines": items,
        "trending_topics": _topic_summary(docs),
    }
    await cache.set_json("headline_category", cache_key, response, max(5, min(normalized_recency * 60, 180)))
    return response


@app.get("/category/{category}")
async def category_page(category: Category, recency_days: int = 7) -> dict:
    normalized_recency = max(1, min(recency_days, 30))
    cache_key = _headline_cache_key(category, 12, normalized_recency)
    cached = await cache.get("category_page", cache_key)
    if cached:
        metrics.inc("category_page.cache_hit")
        return json.loads(cached)

    items = await _latest_headlines_for_category(category, 12, normalized_recency)
    docs = [SourceDoc.model_validate(item) for item in items]
    response = {
        "category": category,
        "hero_headline": items[0] if items else None,
        "secondary_headlines": items[1:5],
        "latest": items,
        "trending_topics": _topic_summary(docs),
        "top_sources": Counter(doc.source for doc in docs).most_common(5),
    }
    await cache.set_json("category_page", cache_key, response, max(5, min(normalized_recency * 60, 180)))
    return response


@app.get("/trending")
async def trending(category: Category | None = None, recency_days: int = 7, limit: int = 10) -> dict:
    categories = [category] if category else ["tech", "research", "sports", "general"]
    return _trending_payload(categories, recency_days=max(1, min(recency_days, 30)), limit=max(1, min(limit, 20)))


@app.get("/topic/{topic}")
async def topic_page(topic: str, recency_days: int = 7) -> dict:
    result = await _search_core(
        SearchRequest(
            query=topic,
            user_id="topic_page",
            categories=["tech", "research", "sports", "general"],
            top_k=8,
            timeline=True,
            recency_days=max(1, min(recency_days, 30)),
        ),
        use_cache=False,
    )
    docs = result.sources
    return {
        "topic": topic,
        "summary": result.model_dump(mode="json"),
        "related_topics": _topic_summary(docs),
        "top_sources": Counter(doc.source for doc in docs).most_common(6),
    }


async def _search_core(payload: SearchRequest, use_cache: bool = True) -> SearchResponse:
    start = time.perf_counter()
    profile = store.get_profile(payload.user_id)
    follows = store.get_follows(payload.user_id)
    mode = payload.explanation_mode or profile.explanation_mode

    categories = payload.categories
    if profile.preferred_categories:
        categories = list(dict.fromkeys([*categories, *profile.preferred_categories]))
    query_analysis = retriever.analyze_query(payload.query, categories)
    search_query = str(query_analysis["rewritten_query"])

    cache_key = (
        f"v5::{payload.user_id}::{payload.query.lower().strip()}::{search_query.lower().strip()}::{','.join(sorted(categories))}::"
        f"{payload.top_k}::{mode}::{payload.explanation_format}::{payload.compare_against or ''}::"
        f"{payload.recency_days or 0}::{payload.sort_by}::{','.join(sorted(payload.source_filter))}::"
        f"{','.join(sorted(payload.source_type_filter))}"
    )

    if use_cache:
        cached = await cache.get_query_cache(cache_key)
        if cached:
            metrics.inc("search.cache_hit.redis")
            cached_payload = json.loads(cached)
            cached_payload.setdefault("explanation_provider", "fallback")
            cached_payload.setdefault("applied_filters", AppliedFilters().model_dump())
            cached_payload.setdefault("suggested_queries", [])
            return SearchResponse.model_validate(cached_payload)

        cached = store.get_query_cache(cache_key, max_age_minutes=settings.query_cache_minutes)
        if cached:
            metrics.inc("search.cache_hit.sqlite")
            cached_payload = json.loads(cached)
            cached_payload.setdefault("explanation_provider", "fallback")
            cached_payload.setdefault("applied_filters", AppliedFilters().model_dump())
            cached_payload.setdefault("suggested_queries", [])
            await cache.put_query_cache(cache_key, cached_payload, settings.query_cache_minutes)
            return SearchResponse.model_validate(cached_payload)

    metrics.inc("search.cache_miss")

    retrieval_started = time.perf_counter()
    live_docs = await registry.gather(search_query, categories, settings.max_fetch_per_source)
    live_docs = enricher.enrich(search_query, live_docs)
    if live_docs:
        store.upsert_documents(live_docs)

    query_embedding: List[float] = []
    try:
        query_embedding = await embedding_service.embed(search_query)
    except Exception as exc:
        logger.warning("query_embedding_failed error=%s", exc)

    vector_docs: List[SourceDoc] = []
    try:
        vector_docs = await vector_index.search(query_embedding, categories, settings.vector_top_k)
        metrics.inc("vector.search.hit" if vector_docs else "vector.search.empty")
    except Exception as exc:
        logger.warning("vector_search_pipeline_failed error=%s", exc)
        metrics.inc("vector.search.error")

    candidate_docs = store.all_recent_documents(categories, limit=180)
    merged_docs: dict[str, SourceDoc] = {}
    for doc in [*candidate_docs, *vector_docs, *live_docs]:
        key = store.canonicalize_url(doc.url, doc.source, doc.title)
        if key not in merged_docs:
            merged_docs[key] = doc

    chunk_hits_by_doc = {}
    chunk_candidates = store.search_chunks(search_query, categories, limit=max(settings.chunk_top_k * 4, payload.top_k * 8))
    cached_chunk_embeddings = store.chunk_embedding_map(categories, limit=800)
    chunk_rank_started = time.perf_counter()
    ranked_chunks, new_chunk_embeddings, query_embedding = await retriever.rank_chunks(
        search_query,
        chunk_candidates,
        cached_embeddings=cached_chunk_embeddings,
        query_embedding=query_embedding,
    )
    metrics.observe("search.chunk_ranking_latency", time.perf_counter() - chunk_rank_started)
    for chunk in ranked_chunks:
        existing = chunk_hits_by_doc.get(chunk.canonical_url)
        if not existing or chunk.total_score > existing.total_score:
            chunk_hits_by_doc[chunk.canonical_url] = chunk

    docs = enricher.enrich(search_query, list(merged_docs.values()))
    docs = _apply_search_filters(docs, payload)

    cached_embeddings = store.embedding_map(categories, limit=300)
    ranked, new_embeddings, query_embedding = await retriever.rank(
        search_query,
        docs,
        payload.top_k if payload.sort_by == "relevance" else max(payload.top_k * 3, payload.top_k),
        profile=profile,
        follows=follows,
        cached_embeddings=cached_embeddings,
        chunk_hits_by_doc=chunk_hits_by_doc,
        query_embedding=query_embedding,
    )
    ranked = _sort_docs(ranked, payload.sort_by)[: payload.top_k]
    metrics.observe("search.retrieval_latency", time.perf_counter() - retrieval_started)

    try:
        if query_embedding:
            await vector_index.ensure_collection(len(query_embedding))
        upserted = await vector_index.upsert_documents(live_docs, new_embeddings)
        metrics.inc("vector.upsert.points", upserted)
    except Exception as exc:
        logger.warning("vector_upsert_failed error=%s", exc)
        metrics.inc("vector.upsert.error")

    if live_docs:
        store.upsert_documents(live_docs, new_embeddings, new_chunk_embeddings)

    contradictions = enricher.contradictions(ranked)
    claim_confidence = enricher.claim_confidence(ranked, contradictions)
    for doc in ranked:
        confidence = (0.5 * doc.credibility_score) + (0.5 * min(doc.total_score / 8.0, 1.0))
        doc.confidence_score = round(max(0.05, min(0.99, confidence)), 4)

    explain_started = time.perf_counter()
    explanation_pack = await explainer.explain(payload.query, ranked, mode, contradictions, payload.explanation_format)
    metrics.observe("llm.explanation_latency", time.perf_counter() - explain_started)
    timeline = enricher.timeline(ranked, max_points=8) if payload.timeline else []

    comparison = None
    if payload.compare_against:
        other = await _search_core(
            SearchRequest(
                query=payload.compare_against,
                top_k=payload.top_k,
                categories=categories,
                user_id=payload.user_id,
                explanation_mode=mode,
                explanation_format=payload.explanation_format,
                timeline=False,
                recency_days=payload.recency_days,
                source_filter=payload.source_filter,
                source_type_filter=payload.source_type_filter,
                sort_by=payload.sort_by,
            ),
            use_cache=False,
        )
        comparison = enricher.compare(payload.query, ranked, payload.compare_against, other.sources)

    context_key = f"{payload.user_id}:{payload.query}:{','.join(categories)}"
    context_id = hashlib.md5(context_key.encode("utf-8")).hexdigest()[:16]
    store.save_context(context_id, payload.user_id, payload.query, ranked)
    store.add_search_history(payload.user_id, payload.query, categories, context_id)

    response = SearchResponse(
        query=payload.query,
        explanation_provider=str(explanation_pack.get("provider", "fallback")),
        explanation=str(explanation_pack.get("explanation", "")),
        key_takeaways=[str(item) for item in explanation_pack.get("key_takeaways", [])][:6],
        why_it_matters=str(explanation_pack.get("why_it_matters", "")),
        what_changed_last_week=str(explanation_pack.get("what_changed_last_week", "")),
        claim_confidence=round(claim_confidence, 4),
        contradictions=contradictions,
        sources=ranked,
        timeline=timeline,
        comparison=comparison,
        context_id=context_id,
        applied_filters=AppliedFilters(
            recency_days=payload.recency_days,
            source_filter=payload.source_filter,
            source_type_filter=payload.source_type_filter,
            sort_by=payload.sort_by,
        ),
        suggested_queries=(_suggested_queries(payload) if not ranked else []),
    )

    payload_json = response.model_dump(mode="json")
    await cache.put_query_cache(cache_key, payload_json, settings.query_cache_minutes)
    store.put_query_cache(cache_key, payload_json)
    metrics.inc("search.calls")
    if not ranked:
        metrics.inc("search.no_result")
    metrics.observe("search.latency", time.perf_counter() - start)
    return response


@app.post("/search", response_model=SearchResponse)
async def search(payload: SearchRequest) -> SearchResponse:
    return await _search_core(payload, use_cache=True)


@app.post("/compare")
async def compare(payload: CompareRequest) -> dict:
    request_a = SearchRequest(
        query=payload.query_a,
        user_id=payload.user_id,
        categories=payload.categories,
        top_k=8,
        timeline=False,
        recency_days=payload.recency_days,
        source_filter=payload.source_filter,
        source_type_filter=payload.source_type_filter,
        sort_by=payload.sort_by,
    )
    request_b = SearchRequest(
        query=payload.query_b,
        user_id=payload.user_id,
        categories=payload.categories,
        top_k=8,
        timeline=False,
        recency_days=payload.recency_days,
        source_filter=payload.source_filter,
        source_type_filter=payload.source_type_filter,
        sort_by=payload.sort_by,
    )
    result_a = await _search_core(request_a, use_cache=False)
    result_b = await _search_core(request_b, use_cache=False)
    comparison = enricher.compare(payload.query_a, result_a.sources, payload.query_b, result_b.sources)
    return {
        "comparison": comparison.model_dump(),
        "query_a_top_sources": [item.model_dump(mode="json") for item in result_a.sources[:4]],
        "query_b_top_sources": [item.model_dump(mode="json") for item in result_b.sources[:4]],
    }


@app.post("/followup", response_model=FollowUpResponse)
async def followup(payload: FollowUpRequest) -> FollowUpResponse:
    context = store.get_context(payload.context_id, payload.user_id)
    if not context:
        raise HTTPException(status_code=404, detail="Context not found for this user")
    query, docs = context
    started = time.perf_counter()
    answer, key_points = await explainer.followup(query, docs, payload.question, payload.explanation_mode)
    metrics.observe("llm.followup_latency", time.perf_counter() - started)
    return FollowUpResponse(context_id=payload.context_id, response=answer, key_points=key_points)


@app.get("/sports/insights")
async def sports_insights(query: str = "NBA") -> dict:
    docs = store.search_documents(query, ["sports"], limit=15)
    if not docs:
        docs = store.all_recent_documents(["sports"], limit=15)
    leagues = Counter(doc.sports_metadata.league for doc in docs if doc.sports_metadata and doc.sports_metadata.league)
    statuses = Counter(doc.sports_metadata.status for doc in docs if doc.sports_metadata and doc.sports_metadata.status)
    impacts = [doc.sports_metadata.injury_trade_impact for doc in docs if doc.sports_metadata and doc.sports_metadata.injury_trade_impact]
    return {
        "query": query,
        "top_leagues": dict(leagues.most_common(5)),
        "status_breakdown": dict(statuses.most_common(5)),
        "trend_summary": [doc.sports_metadata.trend for doc in docs if doc.sports_metadata and doc.sports_metadata.trend][:5],
        "injury_trade_impacts": impacts[:5],
        "sample_events": [doc.model_dump(mode="json") for doc in docs[:5]],
    }


@app.get("/sports/dashboard")
async def sports_dashboard(team: str = "", recency_days: int = 7) -> dict:
    items = await _latest_headlines_for_category("sports", 12, max(1, min(recency_days, 30)))
    docs = [SourceDoc.model_validate(item) for item in items]
    if team.strip():
        lower_team = team.lower()
        docs = [
            doc for doc in docs
            if lower_team in doc.title.lower() or lower_team in doc.summary.lower()
            or (doc.sports_metadata and ((doc.sports_metadata.team or "").lower() == lower_team or (doc.sports_metadata.opponent or "").lower() == lower_team))
        ]
    latest_scores = [doc.model_dump(mode="json") for doc in docs if doc.sports_metadata and doc.sports_metadata.scoreline][:6]
    upcoming = [doc.model_dump(mode="json") for doc in docs if doc.sports_metadata and not doc.sports_metadata.scoreline][:6]
    return {
        "team": team,
        "news": [doc.model_dump(mode="json") for doc in docs[:8]],
        "latest_scores": latest_scores,
        "upcoming": upcoming,
        "top_leagues": Counter(doc.sports_metadata.league for doc in docs if doc.sports_metadata and doc.sports_metadata.league).most_common(6),
    }


@app.get("/sports/team/{team}")
async def sports_team_page(team: str, recency_days: int = 14) -> dict:
    docs = _filter_recent_docs(store.all_recent_documents(["sports"], limit=80), recency_days)
    lower_team = team.lower()
    team_docs = [
        doc for doc in docs
        if lower_team in doc.title.lower() or lower_team in doc.summary.lower()
        or (doc.sports_metadata and ((doc.sports_metadata.team or "").lower() == lower_team or (doc.sports_metadata.opponent or "").lower() == lower_team))
    ]
    return {
        "team": team,
        "latest": [doc.model_dump(mode="json") for doc in team_docs[:10]],
        "timeline": [item.model_dump(mode="json") for item in enricher.timeline(team_docs, max_points=8)],
        "leagues": Counter(doc.sports_metadata.league for doc in team_docs if doc.sports_metadata and doc.sports_metadata.league).most_common(5),
    }


@app.get("/research/insights")
async def research_insights(query: str = "AI") -> dict:
    docs = store.search_documents(query, ["research"], limit=25)
    if not docs:
        docs = store.all_recent_documents(["research"], limit=25)
    themes = Counter(doc.research_metadata.theme for doc in docs if doc.research_metadata and doc.research_metadata.theme)
    venues = Counter(doc.research_metadata.venue for doc in docs if doc.research_metadata and doc.research_metadata.venue)
    code_count = sum(1 for doc in docs if doc.research_metadata and bool(doc.research_metadata.code_available))
    return {
        "query": query,
        "theme_clusters": dict(themes.most_common(8)),
        "top_venues": dict(venues.most_common(8)),
        "code_available_count": code_count,
        "sample_papers": [doc.model_dump(mode="json") for doc in docs[:6]],
    }


@app.get("/research/papers")
async def research_papers(query: str = "AI", recency_days: int = 30) -> dict:
    request = SearchRequest(
        query=query,
        categories=["research"],
        top_k=12,
        recency_days=max(1, min(recency_days, 30)),
        sort_by="latest",
        explanation_mode="beginner",
        explanation_format="bullet",
        timeline=False,
    )
    result = await _search_core(request, use_cache=False)
    return {"query": query, "papers": [item.model_dump(mode="json") for item in result.sources]}


@app.get("/research/paper/{paper_id}")
async def research_paper_page(paper_id: str) -> dict:
    docs = store.all_recent_documents(["research"], limit=120)
    match = next(
        (
            doc for doc in docs
            if doc.research_metadata and (
                (doc.research_metadata.paper_id or "").lower() == paper_id.lower()
                or paper_id.lower() in doc.url.lower()
            )
        ),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail="Paper not found")

    related = []
    for doc in docs:
        if doc.url == match.url:
            continue
        if not doc.research_metadata or not match.research_metadata:
            continue
        same_theme = doc.research_metadata.theme == match.research_metadata.theme
        shared_authors = set(doc.research_metadata.authors).intersection(match.research_metadata.authors)
        if same_theme or shared_authors:
            related.append(doc)

    explanation = await explainer.explain(match.title, [match], "deep", [], "bullet")
    return {
        "paper": match.model_dump(mode="json"),
        "summary": explanation,
        "related_papers": [doc.model_dump(mode="json") for doc in related[:6]],
    }


@app.post("/research/explain-paper")
async def research_explain_paper(payload: ResearchExplainRequest) -> dict:
    docs = [payload.source]
    explanation = await explainer.explain(payload.source.title, docs, payload.explanation_mode, [], "bullet")
    return {
        "paper": payload.source.model_dump(mode="json"),
        "summary": explanation["explanation"],
        "key_takeaways": explanation["key_takeaways"],
    }


@app.post("/research/compare-papers")
async def research_compare_papers(payload: ResearchCompareRequest) -> dict:
    left = payload.left
    right = payload.right
    shared_authors = sorted(set((left.research_metadata.authors if left.research_metadata else [])) & set((right.research_metadata.authors if right.research_metadata else [])))
    return {
        "left_title": left.title,
        "right_title": right.title,
        "same_theme": (left.research_metadata.theme if left.research_metadata else None) == (right.research_metadata.theme if right.research_metadata else None),
        "left_theme": left.research_metadata.theme if left.research_metadata else None,
        "right_theme": right.research_metadata.theme if right.research_metadata else None,
        "shared_authors": shared_authors,
        "code_comparison": {
            "left": left.research_metadata.code_available if left.research_metadata else None,
            "right": right.research_metadata.code_available if right.research_metadata else None,
        },
    }




