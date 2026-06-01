import random
import time

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

app = FastAPI(title="AI Search Retriever", version="0.7.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(search.router)
app.include_router(browse.router)
app.include_router(sports.router)
app.include_router(research.router)


def _security_headers() -> dict:
    return {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "Cache-Control": "no-store",
    }


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


@app.on_event("startup")
async def startup_event() -> None:
    if settings.strict_real_embeddings and not embedding_service.real_embeddings_enabled:
        raise RuntimeError(
            "strict_real_embeddings=True but no embedding provider is configured. "
            "Set GEMINI_API_KEY or OPENAI_API_KEY in your .env, "
            "or set STRICT_REAL_EMBEDDINGS=false to allow hash-based fallback."
        )
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
