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
    BookmarkItem,
    BookmarkRequest,
    Category,
    CompareRequest,
    FollowRequest,
    FollowResponse,
    FollowUpRequest,
    FollowUpResponse,
    SearchRequest,
    SearchResponse,
    SourceDoc,
    UserProfile,
)
from backend.app.services.document_store import DocumentStore
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.enrichment_service import EnrichmentService
from backend.app.services.explainer import ExplainerService
from backend.app.services.ingestion import IngestionService
from backend.app.services.logging_service import get_logger, setup_logging
from backend.app.services.observability_service import MetricsService
from backend.app.services.retriever import RetrieverService
from backend.app.services.scheduler import SchedulerService
from backend.app.services.source_registry import SourceRegistry
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

app = FastAPI(title="AI Search Retriever", version="0.7.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = DocumentStore(settings.db_path)
registry = SourceRegistry()
enricher = EnrichmentService()
embedding_service = EmbeddingService()
retriever = RetrieverService(embedding_service)
explainer = ExplainerService()
vector_index = VectorIndexService()
ingestion = IngestionService(registry, store, enricher, settings.max_fetch_per_source)
scheduler = SchedulerService(ingestion, settings.scheduler_interval_minutes)


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


@app.on_event("startup")
async def startup_event() -> None:
    await scheduler.start()
    logger.info(
        "startup_complete vector_enabled=%s real_embeddings=%s strict_real_embeddings=%s",
        vector_index.enabled,
        embedding_service.real_embeddings_enabled,
        settings.strict_real_embeddings,
    )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await scheduler.stop()


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
    }


@app.get("/metrics")
async def get_metrics() -> JSONResponse:
    return JSONResponse(metrics.snapshot())


@app.get("/metrics/prometheus")
async def get_metrics_prometheus() -> PlainTextResponse:
    return PlainTextResponse(metrics.as_prometheus_text(), media_type="text/plain; version=0.0.4")


@app.post("/ingest/run")
async def run_ingestion() -> dict:
    start = time.perf_counter()
    inserted = await ingestion.ingest_seed_topics()
    metrics.inc("ingestion.run.calls")
    metrics.observe("ingestion.run.latency", time.perf_counter() - start)
    metrics.inc("ingestion.documents_inserted", inserted)
    return {"ok": True, "inserted": inserted}


@app.post("/ingest/webhook")
async def ingest_webhook(payload: IngestEventRequest) -> dict:
    start = time.perf_counter()
    inserted = await ingestion.ingest_event(payload.topic, payload.categories)
    metrics.inc("ingestion.webhook.calls")
    metrics.observe("ingestion.webhook.latency", time.perf_counter() - start)
    metrics.inc("ingestion.documents_inserted", inserted)
    return {"ok": True, "inserted": inserted, "topic": payload.topic}


@app.get("/users/{user_id}/profile", response_model=UserProfile)
async def get_user_profile(user_id: str) -> UserProfile:
    return store.get_profile(user_id)


@app.put("/users/{user_id}/profile", response_model=UserProfile)
async def put_user_profile(user_id: str, profile: UserProfile) -> UserProfile:
    if profile.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.upsert_profile(profile)


@app.post("/users/{user_id}/follows", response_model=FollowResponse)
async def add_follow(user_id: str, payload: FollowRequest) -> FollowResponse:
    if payload.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    entities = store.add_follow(user_id, payload.entity)
    return FollowResponse(user_id=user_id, entities=entities)


@app.get("/users/{user_id}/follows", response_model=FollowResponse)
async def get_follows(user_id: str) -> FollowResponse:
    return FollowResponse(user_id=user_id, entities=store.get_follows(user_id))


@app.post("/users/{user_id}/alerts", response_model=AlertRule)
async def add_alert(user_id: str, rule: AlertRule) -> AlertRule:
    if rule.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.add_alert(rule)


@app.get("/users/{user_id}/alerts", response_model=List[AlertRule])
async def get_alerts(user_id: str) -> List[AlertRule]:
    return store.get_alerts(user_id)


@app.get("/users/{user_id}/alert-delivery", response_model=AlertDeliverySettings)
async def get_alert_delivery(user_id: str) -> AlertDeliverySettings:
    return store.get_alert_delivery(user_id)


@app.put("/users/{user_id}/alert-delivery", response_model=AlertDeliverySettings)
async def put_alert_delivery(user_id: str, payload: AlertDeliverySettings) -> AlertDeliverySettings:
    if payload.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.upsert_alert_delivery(payload)


@app.post("/users/{user_id}/alert-delivery/test")
async def test_alert_delivery(user_id: str) -> dict:
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
async def add_bookmark(user_id: str, payload: BookmarkRequest) -> BookmarkItem:
    if payload.user_id != user_id:
        raise HTTPException(status_code=400, detail="Path user_id must match payload user_id")
    return store.add_bookmark(user_id, payload.source)


@app.get("/users/{user_id}/bookmarks", response_model=List[BookmarkItem])
async def get_bookmarks(user_id: str) -> List[BookmarkItem]:
    return store.get_bookmarks(user_id)


@app.delete("/users/{user_id}/bookmarks/{bookmark_id}")
async def delete_bookmark(user_id: str, bookmark_id: int) -> dict:
    store.delete_bookmark(user_id, bookmark_id)
    return {"ok": True}


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
    categories: List[Category] = ["tech", "research", "sports", "general"]
    payload = {}
    for category in categories:
        payload[category] = await _latest_headlines_for_category(category, limit, recency)
    return {"updated_at": datetime.now(timezone.utc).isoformat(), "categories": payload, "recency_days": recency}


@app.get("/headlines/{category}")
async def headlines_by_category(category: Category, limit: int = 10, recency_days: int = 7) -> dict:
    items = await _latest_headlines_for_category(category, max(1, min(limit, 20)), max(1, min(recency_days, 30)))
    docs = [SourceDoc.model_validate(item) for item in items]
    return {
        "category": category,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "headlines": items,
        "trending_topics": _topic_summary(docs),
    }


@app.get("/category/{category}")
async def category_page(category: Category, recency_days: int = 7) -> dict:
    items = await _latest_headlines_for_category(category, 12, max(1, min(recency_days, 30)))
    docs = [SourceDoc.model_validate(item) for item in items]
    return {
        "category": category,
        "hero_headline": items[0] if items else None,
        "secondary_headlines": items[1:5],
        "latest": items,
        "trending_topics": _topic_summary(docs),
        "top_sources": Counter(doc.source for doc in docs).most_common(5),
    }


async def _search_core(payload: SearchRequest, use_cache: bool = True) -> SearchResponse:
    start = time.perf_counter()
    profile = store.get_profile(payload.user_id)
    follows = store.get_follows(payload.user_id)
    mode = payload.explanation_mode or profile.explanation_mode

    categories = payload.categories
    if profile.preferred_categories:
        categories = list(dict.fromkeys([*categories, *profile.preferred_categories]))

    cache_key = (
        f"v3::{payload.user_id}::{payload.query.lower().strip()}::{','.join(sorted(categories))}::"
        f"{payload.top_k}::{mode}::{payload.explanation_format}::{payload.compare_against or ''}::"
        f"{payload.recency_days or 0}::{payload.sort_by}::{','.join(sorted(payload.source_filter))}::"
        f"{','.join(sorted(payload.source_type_filter))}"
    )

    if use_cache:
        cached = store.get_query_cache(cache_key, max_age_minutes=settings.query_cache_minutes)
        if cached:
            metrics.inc("search.cache_hit")
            cached_payload = json.loads(cached)
            cached_payload.setdefault("explanation_provider", "fallback")
            cached_payload.setdefault("applied_filters", AppliedFilters().model_dump())
            return SearchResponse.model_validate(cached_payload)
    metrics.inc("search.cache_miss")

    live_docs = await registry.gather(payload.query, categories, settings.max_fetch_per_source)
    live_docs = enricher.enrich(payload.query, live_docs)

    vector_docs: List[SourceDoc] = []
    try:
        query_embedding_for_vector = await embedding_service.embed(payload.query)
        vector_docs = await vector_index.search(query_embedding_for_vector, categories, settings.vector_top_k)
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

    docs = enricher.enrich(payload.query, list(merged_docs.values()))
    docs = _apply_search_filters(docs, payload)

    cached_embeddings = store.embedding_map(categories, limit=300)
    ranked, new_embeddings, query_embedding = await retriever.rank(
        payload.query,
        docs,
        payload.top_k if payload.sort_by == "relevance" else max(payload.top_k * 3, payload.top_k),
        profile=profile,
        follows=follows,
        cached_embeddings=cached_embeddings,
    )
    ranked = _sort_docs(ranked, payload.sort_by)[: payload.top_k]

    try:
        if query_embedding:
            await vector_index.ensure_collection(len(query_embedding))
        upserted = await vector_index.upsert_documents(live_docs, new_embeddings)
        metrics.inc("vector.upsert.points", upserted)
    except Exception as exc:
        logger.warning("vector_upsert_failed error=%s", exc)
        metrics.inc("vector.upsert.error")

    contradictions = enricher.contradictions(ranked)
    claim_confidence = enricher.claim_confidence(ranked, contradictions)
    for doc in ranked:
        confidence = (0.5 * doc.credibility_score) + (0.5 * min(doc.total_score / 8.0, 1.0))
        doc.confidence_score = round(max(0.05, min(0.99, confidence)), 4)

    explanation_pack = await explainer.explain(payload.query, ranked, mode, contradictions, payload.explanation_format)
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
    )

    store.put_query_cache(cache_key, response.model_dump(mode="json"))
    metrics.inc("search.calls")
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
    answer, key_points = await explainer.followup(query, docs, payload.question, payload.explanation_mode)
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
