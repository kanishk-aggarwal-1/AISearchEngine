import asyncio
import json
import re
import time
import uuid
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.app.config import settings
from backend.app.container import (
    cache,
    embedding_service,
    enricher,
    explainer,
    logger,
    metrics,
    metrics_store,
    registry,
    retriever,
    store,
    vector_index,
)
from backend.app.models import (
    AppliedFilters,
    CompareRequest,
    ConversationCreateRequest,
    ConversationMessageRequest,
    FollowUpRequest,
    FollowUpResponse,
    SearchRequest,
    SearchFeedbackRequest,
    SearchResponse,
    SourceDoc,
)
from backend.app.dependencies import current_user, resolve_search_user

router = APIRouter()


# ── Internal helpers ─────────────────────────────────────────────────────────


def _apply_search_filters(docs: List[SourceDoc], payload: SearchRequest) -> List[SourceDoc]:
    filtered = docs
    if payload.recency_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=payload.recency_days)
        filtered = [
            doc
            for doc in filtered
            if doc.published_at
            and (doc.published_at if doc.published_at.tzinfo else doc.published_at.replace(tzinfo=timezone.utc))
            >= cutoff
        ]
    if payload.source_filter:
        wanted = {item.lower() for item in payload.source_filter if item.strip()}
        filtered = [doc for doc in filtered if doc.source.lower() in wanted]
    if payload.source_type_filter:
        allowed = set(payload.source_type_filter)
        filtered = [doc for doc in filtered if doc.source_type in allowed]
    if payload.domain_filter:
        domains = {item.lower().removeprefix("www.") for item in payload.domain_filter if item.strip()}
        filtered = [doc for doc in filtered if urlparse(doc.url).netloc.lower().removeprefix("www.") in domains]
    if payload.author_filter:
        wanted_authors = {item.lower() for item in payload.author_filter if item.strip()}
        filtered = [
            doc
            for doc in filtered
            if doc.research_metadata
            and wanted_authors.intersection(author.lower() for author in doc.research_metadata.authors)
        ]
    if payload.min_credibility is not None:
        filtered = [doc for doc in filtered if doc.credibility_score >= payload.min_credibility]
    if payload.language_filter:
        languages = {item.lower() for item in payload.language_filter}
        filtered = [doc for doc in filtered if doc.language.lower() in languages]
    if payload.region_filter:
        regions = {item.lower() for item in payload.region_filter}
        filtered = [doc for doc in filtered if doc.region.lower() in regions]
    if payload.date_from:
        start = payload.date_from if payload.date_from.tzinfo else payload.date_from.replace(tzinfo=timezone.utc)
        filtered = [
            doc
            for doc in filtered
            if doc.published_at
            and (doc.published_at if doc.published_at.tzinfo else doc.published_at.replace(tzinfo=timezone.utc))
            >= start
        ]
    if payload.date_to:
        end = payload.date_to if payload.date_to.tzinfo else payload.date_to.replace(tzinfo=timezone.utc)
        filtered = [
            doc
            for doc in filtered
            if doc.published_at
            and (doc.published_at if doc.published_at.tzinfo else doc.published_at.replace(tzinfo=timezone.utc)) <= end
        ]
    return filtered


def _citation_warnings(explanation: str) -> List[str]:
    warnings = []
    for sentence in re.split(r"(?<=[.!?])\s+", explanation):
        clean = sentence.strip()
        if len(clean.split()) >= 8 and not re.search(r"\[\d+\]", clean):
            warnings.append(f"Uncited claim: {clean[:180]}")
    return warnings[:5]


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


def _suggested_queries(payload: SearchRequest) -> List[str]:
    raw = payload.query.strip()
    tokens = [
        token
        for token in raw.split()
        if token.lower() not in {"latest", "news", "what", "happening", "today", "this", "week"}
    ]
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
    seen: set = set()
    for item in suggestions:
        clean = " ".join(item.split()).strip()
        if clean and clean.lower() not in seen and clean.lower() != raw.lower():
            seen.add(clean.lower())
            unique.append(clean)
    return unique[:4]


def _citation_coverage(sources: list) -> float:
    """Fraction (0..1) of returned SourceDoc objects that carry a citation snippet.

    Always called with a list of SourceDoc models (either from a live search or
    after SearchResponse.model_validate on a cached payload) so no isinstance
    branching is needed.
    """
    if not sources:
        return 0.0
    return sum(1 for s in sources if bool((getattr(s, "citation_snippet", "") or "").strip())) / len(sources)


async def _search_core(payload: SearchRequest, use_cache: bool = True) -> SearchResponse:
    start = time.perf_counter()
    profile, follows = await asyncio.gather(
        asyncio.to_thread(store.get_profile, payload.user_id),
        asyncio.to_thread(store.get_follows, payload.user_id),
    )
    mode = payload.explanation_mode or profile.explanation_mode

    categories = payload.categories
    if profile.preferred_categories:
        categories = list(dict.fromkeys([*categories, *profile.preferred_categories]))
    query_analysis = retriever.analyze_query(payload.query, categories)
    search_query = str(query_analysis["rewritten_query"])

    cache_key = (
        f"v5::{payload.user_id}::{payload.query.lower().strip()}::{search_query.lower().strip()}::{','.join(sorted(categories))}"
        f"::{payload.top_k}::{mode}::{payload.explanation_format}::{payload.compare_against or ''}"
        f"::{payload.recency_days or 0}::{payload.sort_by}::{','.join(sorted(payload.source_filter))}"
        f"::{','.join(sorted(payload.source_type_filter))}"
        f"::{','.join(sorted(payload.domain_filter))}::{','.join(sorted(payload.author_filter))}"
        f"::{payload.min_credibility if payload.min_credibility is not None else ''}"
        f"::{','.join(sorted(payload.language_filter))}::{','.join(sorted(payload.region_filter))}"
        f"::{payload.date_from or ''}::{payload.date_to or ''}"
    )

    if use_cache:
        cached = await cache.get_query_cache(cache_key)
        if cached:
            metrics.inc("search.cache_hit.redis")
            p = json.loads(cached)
            p.setdefault("explanation_provider", "fallback")
            p.setdefault("applied_filters", AppliedFilters().model_dump())
            p.setdefault("suggested_queries", [])
            # Validate first so _citation_coverage always receives SourceDoc objects.
            response = SearchResponse.model_validate(p)
            await metrics_store.record_search(
                latency_ms=(time.perf_counter() - start) * 1000,
                cache_hit=True,
                citation_coverage=_citation_coverage(response.sources),
                no_result=not response.sources,
            )
            return response

        cached = await asyncio.to_thread(store.get_query_cache, cache_key, settings.query_cache_minutes)
        if cached:
            metrics.inc("search.cache_hit.sqlite")
            p = json.loads(cached)
            p.setdefault("explanation_provider", "fallback")
            p.setdefault("applied_filters", AppliedFilters().model_dump())
            p.setdefault("suggested_queries", [])
            await cache.put_query_cache(cache_key, p, settings.query_cache_minutes)
            # Validate first so _citation_coverage always receives SourceDoc objects.
            response = SearchResponse.model_validate(p)
            await metrics_store.record_search(
                latency_ms=(time.perf_counter() - start) * 1000,
                cache_hit=True,
                citation_coverage=_citation_coverage(response.sources),
                no_result=not response.sources,
            )
            return response

    metrics.inc("search.cache_miss")

    retrieval_started = time.perf_counter()
    live_docs = await registry.gather(search_query, categories, settings.max_fetch_per_source)
    live_docs = enricher.enrich(search_query, live_docs)
    if live_docs:
        await asyncio.to_thread(store.upsert_documents, live_docs)

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

    candidate_docs = await asyncio.to_thread(store.all_recent_documents, categories, 180)
    merged_docs: dict[str, SourceDoc] = {}
    for doc in [*candidate_docs, *vector_docs, *live_docs]:
        key = store.canonicalize_url(doc.url, doc.source, doc.title)
        if key not in merged_docs:
            merged_docs[key] = doc

    chunk_hits_by_doc = {}
    chunk_candidates, cached_chunk_embeddings = await asyncio.gather(
        asyncio.to_thread(
            store.search_chunks,
            search_query,
            categories,
            max(settings.chunk_top_k * 4, payload.top_k * 8),
        ),
        asyncio.to_thread(store.chunk_embedding_map, categories, 800),
    )
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

    cached_embeddings = await asyncio.to_thread(store.embedding_map, categories, 300)
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
        await asyncio.to_thread(store.upsert_documents, live_docs, new_embeddings, new_chunk_embeddings)

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
                domain_filter=payload.domain_filter,
                author_filter=payload.author_filter,
                min_credibility=payload.min_credibility,
                language_filter=payload.language_filter,
                region_filter=payload.region_filter,
                date_from=payload.date_from,
                date_to=payload.date_to,
            ),
            use_cache=False,
        )
        comparison = enricher.compare(payload.query, ranked, payload.compare_against, other.sources)

    context_id = uuid.uuid4().hex
    await asyncio.gather(
        asyncio.to_thread(store.save_context, context_id, payload.user_id, payload.query, ranked),
        asyncio.to_thread(store.add_search_history, payload.user_id, payload.query, categories, context_id),
    )

    response = SearchResponse(
        query=payload.query,
        explanation_provider=str(explanation_pack.get("provider", "fallback")),
        explanation=str(explanation_pack.get("explanation", "")),
        key_takeaways=[str(i) for i in explanation_pack.get("key_takeaways", [])][:6],
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
            domain_filter=payload.domain_filter,
            author_filter=payload.author_filter,
            min_credibility=payload.min_credibility,
            language_filter=payload.language_filter,
            region_filter=payload.region_filter,
            date_from=payload.date_from,
            date_to=payload.date_to,
        ),
        suggested_queries=(_suggested_queries(payload) if not ranked else []),
        search_mode="semantic" if embedding_service.real_embeddings_enabled else "keyword",
        citation_warnings=_citation_warnings(str(explanation_pack.get("explanation", ""))),
    )

    payload_json = response.model_dump(mode="json")
    await cache.put_query_cache(cache_key, payload_json, settings.query_cache_minutes)
    await asyncio.to_thread(store.put_query_cache, cache_key, payload_json)
    metrics.inc("search.calls")
    if not ranked:
        metrics.inc("search.no_result")
    metrics.observe("search.latency", time.perf_counter() - start)
    await metrics_store.record_search(
        latency_ms=(time.perf_counter() - start) * 1000,
        cache_hit=False,
        citation_coverage=_citation_coverage(ranked),
        no_result=not ranked,
    )
    return response


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("/search", response_model=SearchResponse)
async def search(request: Request, payload: SearchRequest) -> SearchResponse:
    user_id = resolve_search_user(request, payload.user_id)
    return await _search_core(payload.model_copy(update={"user_id": user_id}), use_cache=True)


@router.post("/search/stream")
async def search_stream(request: Request, payload: SearchRequest) -> StreamingResponse:
    user_id = resolve_search_user(request, payload.user_id)

    async def events():
        yield 'event: status\ndata: {"stage":"retrieving"}\n\n'
        result = await _search_core(payload.model_copy(update={"user_id": user_id}), use_cache=True)
        metadata = result.model_dump(mode="json")
        explanation = metadata.pop("explanation", "")
        yield f"event: result\ndata: {json.dumps(metadata)}\n\n"
        for chunk in re.findall(r".{1,80}(?:\s+|$)", explanation):
            yield f"event: explanation\ndata: {json.dumps({'text': chunk})}\n\n"
        yield 'event: done\ndata: {"ok":true}\n\n'

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/search/feedback")
async def search_feedback(request: Request, payload: SearchFeedbackRequest) -> dict:
    user_id = resolve_search_user(request, "default")
    if not await asyncio.to_thread(store.get_context, payload.context_id, user_id):
        raise HTTPException(status_code=404, detail="Context not found")
    await asyncio.to_thread(store.add_search_feedback, user_id, payload.context_id, payload.helpful, payload.comment)
    return {"ok": True}


@router.post("/conversations")
async def create_conversation(request: Request, payload: ConversationCreateRequest) -> dict:
    user = current_user(request)
    conversation = await asyncio.to_thread(store.create_conversation, user.user_id, payload.context_id, payload.title)
    if not conversation:
        raise HTTPException(status_code=404, detail="Context not found")
    return conversation


@router.get("/conversations")
async def list_conversations(request: Request, limit: int = 50, offset: int = 0) -> list[dict]:
    user = current_user(request)
    return await asyncio.to_thread(store.list_conversations, user.user_id, max(1, min(limit, 100)), max(0, offset))


@router.get("/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str) -> dict:
    user = current_user(request)
    conversation = await asyncio.to_thread(store.get_conversation, conversation_id, user.user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("/conversations/{conversation_id}/messages")
async def add_conversation_message(request: Request, conversation_id: str, payload: ConversationMessageRequest) -> dict:
    user = current_user(request)
    context = await asyncio.to_thread(store.conversation_context, conversation_id, user.user_id)
    if not context:
        raise HTTPException(status_code=404, detail="Conversation not found")
    original_query, docs = context
    await asyncio.to_thread(store.add_conversation_message, conversation_id, user.user_id, "user", payload.question, [])
    answer, key_points = await explainer.followup(original_query, docs, payload.question, payload.explanation_mode)
    message = await asyncio.to_thread(
        store.add_conversation_message,
        conversation_id,
        user.user_id,
        "assistant",
        answer,
        key_points,
    )
    return message or {}


@router.post("/contexts/{context_id}/share")
async def share_context(request: Request, context_id: str, ttl_days: int = 7) -> dict:
    user = current_user(request)
    token = await asyncio.to_thread(store.share_context, context_id, user.user_id, max(1, min(ttl_days, 30)))
    if not token:
        raise HTTPException(status_code=404, detail="Context not found")
    return {"share_token": token, "expires_in_days": max(1, min(ttl_days, 30))}


@router.get("/shared/{share_token}")
async def shared_context(share_token: str) -> dict:
    result = await asyncio.to_thread(store.get_shared_context, share_token)
    if not result:
        raise HTTPException(status_code=404, detail="Shared context not found or expired")
    return result


@router.post("/compare")
async def compare(request: Request, payload: CompareRequest) -> dict:
    user_id = resolve_search_user(request, payload.user_id)
    request_a = SearchRequest(
        query=payload.query_a,
        user_id=user_id,
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
        user_id=user_id,
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
        "query_a_top_sources": [i.model_dump(mode="json") for i in result_a.sources[:4]],
        "query_b_top_sources": [i.model_dump(mode="json") for i in result_b.sources[:4]],
    }


@router.post("/followup", response_model=FollowUpResponse)
async def followup(request: Request, payload: FollowUpRequest) -> FollowUpResponse:
    user_id = resolve_search_user(request, payload.user_id)
    context = await asyncio.to_thread(store.get_context, payload.context_id, user_id)
    if not context:
        raise HTTPException(status_code=404, detail="Context not found for this user")
    query, docs = context
    started = time.perf_counter()
    answer, key_points = await explainer.followup(query, docs, payload.question, payload.explanation_mode)
    metrics.observe("llm.followup_latency", time.perf_counter() - started)
    return FollowUpResponse(context_id=payload.context_id, response=answer, key_points=key_points)
