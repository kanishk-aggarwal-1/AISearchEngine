from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.app.config import settings
from backend.app.container import cache, embedding_service, metrics, store, vector_index

router = APIRouter()


@router.get("/health")
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


@router.get("/health/deep")
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
        "fallback_explainer": {"configured": True, "status": "ready"},
    }

    components = {
        "api": {"status": "ok", "app_name": "SignalScope AI"},
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

    return {
        "ok": db_ok and (redis_ok or not cache.using_redis),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }


@router.get("/metrics")
async def get_metrics() -> JSONResponse:
    return JSONResponse(
        {
            **metrics.snapshot(),
            "source_freshness": store.source_freshness_summary(),
            "last_successful_ingestion_at": store.last_successful_ingestion_at(),
        }
    )


@router.get("/metrics/prometheus")
async def get_metrics_prometheus() -> PlainTextResponse:
    lines = [metrics.as_prometheus_text().rstrip()]
    for key, value in store.source_freshness_summary().items():
        lines.append(f"signalscope_source_freshness_{key} {value}")
    last_ingestion = store.last_successful_ingestion_at()
    ts = 0.0
    if last_ingestion:
        try:
            ts = datetime.fromisoformat(last_ingestion).timestamp()
        except Exception:
            ts = 0.0
    lines.append(f"signalscope_ingestion_last_successful_timestamp {ts}")
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
