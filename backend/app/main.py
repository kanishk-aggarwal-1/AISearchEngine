import random
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.config import settings
from backend.app.container import (
    cache, embedding_service, logger, metrics,
    scheduler, vector_index,
)
from backend.app.routers import admin, auth, browse, health, research, search, sports, users

# Fallback in-process buckets used only when Redis is unavailable (single-worker dev mode)
_RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
ALLOWED_ORIGINS = [
    settings.frontend_origin,
    *[item.strip() for item in settings.extra_frontend_origins.split(",") if item.strip()],
]


def _warn_missing_config() -> None:
    """Warn about missing optional but important configuration at startup."""
    if not settings.gemini_api_key and not settings.openai_api_key:
        logger.warning(
            "no_llm_key configured — explanations will use fallback mode. "
            "Set GEMINI_API_KEY or OPENAI_API_KEY for real AI explanations."
        )
    if not settings.newsapi_key:
        logger.warning(
            "no_newsapi_key configured — general news will rely on RSS feeds only. "
            "Set NEWSAPI_KEY for broader news coverage."
        )
    if not cache.using_redis:
        logger.warning(
            "redis_not_connected — caching and rate limiting are in-process only. "
            "Set REDIS_URL and CACHE_BACKEND=redis for production caching."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.strict_real_embeddings and not embedding_service.real_embeddings_enabled:
        raise RuntimeError(
            "strict_real_embeddings=True but no embedding provider is configured. "
            "Set GEMINI_API_KEY or OPENAI_API_KEY in your .env, "
            "or set STRICT_REAL_EMBEDDINGS=false to allow hash-based fallback."
        )
    worker_count = int(__import__("os").environ.get("WEB_CONCURRENCY", "1"))
    if worker_count > 1 and not cache.using_redis:
        logger.warning(
            "multi_worker_no_redis workers=%d — rate limiting is per-worker only. "
            "Set REDIS_URL and CACHE_BACKEND=redis for accurate rate limiting.",
            worker_count,
        )
    _warn_missing_config()
    try:
        await scheduler.start()
    except Exception as exc:
        logger.warning("scheduler_start_failed error=%s — continuing without scheduler", exc)
    logger.info(
        "startup_complete vector_enabled=%s real_embeddings=%s strict_real_embeddings=%s cache_backend=%s redis_enabled=%s",
        vector_index.enabled,
        embedding_service.real_embeddings_enabled,
        settings.strict_real_embeddings,
        settings.cache_backend,
        cache.using_redis,
    )
    yield
    try:
        await scheduler.stop()
    except Exception:
        pass
    await cache.close()


app = FastAPI(title="AI Search Retriever", version="0.7.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Unversioned: health and metrics endpoints stay at root for monitoring tools
app.include_router(health.router)

# Versioned API — all product endpoints under /v1/
_V1 = {"prefix": "/v1"}
app.include_router(auth.router, **_V1)
app.include_router(users.router, **_V1)
app.include_router(admin.router, **_V1)
app.include_router(search.router, **_V1)
app.include_router(browse.router, **_V1)
app.include_router(sports.router, **_V1)
app.include_router(research.router, **_V1)


def _security_headers() -> dict:
    return {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "Cache-Control": "no-store",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "   # Next.js requires unsafe-inline for hydration
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000; "
            "frame-ancestors 'none'"
        ),
    }


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    path = request.url.path
    method = request.method
    status_code = 500

    if settings.enable_metrics:
        metrics.inc("http.requests_total")
        metrics.inc(f"http.requests.{method}.{path}")

    try:
        response = await call_next(request)
        status_code = response.status_code
        if settings.enable_metrics:
            metrics.inc(f"http.responses.{status_code}")
    except Exception as exc:
        if settings.enable_metrics:
            metrics.inc("http.errors_total")
        logger.exception(
            "request_failed request_id=%s method=%s path=%s error=%s",
            request_id, method, path, exc,
        )
        raise
    finally:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        if settings.enable_metrics:
            metrics.observe("http.request_latency", latency_ms / 1000)
            metrics.observe(f"http.request_latency.{method}.{path}", latency_ms / 1000)
        logger.debug(
            "request_complete request_id=%s method=%s path=%s status=%s latency_ms=%s",
            request_id, method, path, status_code, latency_ms,
        )

    return response


async def _is_rate_limited(client_ip: str) -> bool:
    """
    Redis-backed rate limiter (works across multiple workers).
    Falls back to in-process sliding window when Redis is unavailable.
    """
    if cache.using_redis:
        count = await cache.incr(f"rl:{client_ip}", ttl_seconds=60)
        return count > settings.rate_limit_per_minute

    # In-process fallback — single-worker only
    now = time.time()
    window_start = now - 60
    bucket = [s for s in _RATE_LIMIT_BUCKETS.get(client_ip, []) if s >= window_start]
    if random.random() < 0.01:
        stale = [ip for ip, stamps in _RATE_LIMIT_BUCKETS.items() if not stamps or max(stamps) < window_start]
        for ip in stale:
            del _RATE_LIMIT_BUCKETS[ip]
    if len(bucket) >= settings.rate_limit_per_minute:
        return True
    bucket.append(now)
    _RATE_LIMIT_BUCKETS[client_ip] = bucket
    return False


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    client_host = request.client.host if request.client else "unknown"

    if await _is_rate_limited(client_host):
        metrics.inc("http.rate_limited")
        return JSONResponse(
            {"detail": "Rate limit exceeded. Please retry shortly."},
            status_code=429,
            headers=_security_headers(),
        )

    response = await call_next(request)
    for header, value in _security_headers().items():
        response.headers[header] = value
    return response


