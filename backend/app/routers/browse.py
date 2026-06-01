import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter

from backend.app.config import settings
from backend.app.container import cache, enricher, metrics, registry, store
from backend.app.models import Category, SearchRequest, SourceDoc
from backend.app.routers.search import _search_core

router = APIRouter()


# ── Shared helpers used by browse, sports, and research ──────────────────────

def topic_summary(docs: List[SourceDoc]) -> List[str]:
    counter: Counter = Counter()
    for doc in docs[:20]:
        for tag in doc.entity_tags[:4]:
            if len(tag) >= 3:
                counter[tag] += 1
    return [item for item, _ in counter.most_common(8)]


def filter_recent_docs(docs: List[SourceDoc], recency_days: int) -> List[SourceDoc]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, recency_days))
    filtered = []
    for doc in docs:
        if not doc.published_at:
            continue
        published = (
            doc.published_at if doc.published_at.tzinfo
            else doc.published_at.replace(tzinfo=timezone.utc)
        )
        if published >= cutoff:
            filtered.append(doc)
    return filtered


def _headline_cache_key(category: str, limit: int, recency_days: int) -> str:
    return f"{category}:{limit}:{recency_days}"


async def latest_headlines_for_category(
    category: Category, limit: int, recency_days: int = 7
) -> List[dict]:
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
        published_at = (
            doc.published_at if doc.published_at.tzinfo
            else doc.published_at.replace(tzinfo=timezone.utc)
        )
        if published_at >= cutoff:
            fresh_docs.append(doc)

    fresh_docs.sort(
        key=lambda item: item.published_at.isoformat() if item.published_at else "",
        reverse=True,
    )
    return [doc.model_dump(mode="json") for doc in fresh_docs[:limit]]


def _trending_payload(categories: List[Category], recency_days: int = 7, limit: int = 10) -> dict:
    docs = filter_recent_docs(
        store.all_recent_documents(categories, limit=200), recency_days
    )
    topic_counter: Counter = Counter()
    for doc in docs:
        for tag in doc.entity_tags[:5]:
            if len(tag) >= 3:
                topic_counter[tag] += 1
    return {
        "categories": categories,
        "recency_days": recency_days,
        "topics": [{"topic": t, "count": c} for t, c in topic_counter.most_common(limit)],
        "sample_sources": [doc.model_dump(mode="json") for doc in docs[: min(limit, 8)]],
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/headlines")
async def headlines(per_category: int = 4, recency_days: int = 7) -> dict:
    limit = max(1, min(per_category, 8))
    recency = max(1, min(recency_days, 30))
    cache_key = _headline_cache_key("all", limit, recency)
    cached = await cache.get("headlines", cache_key)
    if cached:
        metrics.inc("headlines.cache_hit")
        return json.loads(cached)

    all_categories: List[Category] = ["tech", "research", "sports", "general"]
    payload = {}
    for category in all_categories:
        payload[category] = await latest_headlines_for_category(category, limit, recency)
    response = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "categories": payload,
        "recency_days": recency,
    }
    await cache.set_json("headlines", cache_key, response, max(5, min(recency * 60, 180)))
    return response


@router.get("/headlines/{category}")
async def headlines_by_category(
    category: Category, limit: int = 10, recency_days: int = 7
) -> dict:
    normalized_limit = max(1, min(limit, 20))
    normalized_recency = max(1, min(recency_days, 30))
    cache_key = _headline_cache_key(category, normalized_limit, normalized_recency)
    cached = await cache.get("headline_category", cache_key)
    if cached:
        metrics.inc("headlines.category_cache_hit")
        return json.loads(cached)

    items = await latest_headlines_for_category(category, normalized_limit, normalized_recency)
    docs = [SourceDoc.model_validate(item) for item in items]
    response = {
        "category": category,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "headlines": items,
        "trending_topics": topic_summary(docs),
    }
    await cache.set_json(
        "headline_category", cache_key, response, max(5, min(normalized_recency * 60, 180))
    )
    return response


@router.get("/category/{category}")
async def category_page(category: Category, recency_days: int = 7) -> dict:
    normalized_recency = max(1, min(recency_days, 30))
    cache_key = _headline_cache_key(category, 12, normalized_recency)
    cached = await cache.get("category_page", cache_key)
    if cached:
        metrics.inc("category_page.cache_hit")
        return json.loads(cached)

    items = await latest_headlines_for_category(category, 12, normalized_recency)
    docs = [SourceDoc.model_validate(item) for item in items]
    response = {
        "category": category,
        "hero_headline": items[0] if items else None,
        "secondary_headlines": items[1:5],
        "latest": items,
        "trending_topics": topic_summary(docs),
        "top_sources": Counter(doc.source for doc in docs).most_common(5),
    }
    await cache.set_json(
        "category_page", cache_key, response, max(5, min(normalized_recency * 60, 180))
    )
    return response


@router.get("/trending")
async def trending(
    category: Category | None = None, recency_days: int = 7, limit: int = 10
) -> dict:
    categories = [category] if category else ["tech", "research", "sports", "general"]
    return _trending_payload(
        categories,
        recency_days=max(1, min(recency_days, 30)),
        limit=max(1, min(limit, 20)),
    )


@router.get("/topic/{topic}")
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
        "related_topics": topic_summary(docs),
        "top_sources": Counter(doc.source for doc in docs).most_common(6),
    }
