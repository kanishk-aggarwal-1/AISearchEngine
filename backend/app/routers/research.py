from collections import Counter
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
import httpx
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.container import explainer, registry, store
from backend.app.models import SearchRequest, SourceDoc
from backend.app.routers.search import _search_core

router = APIRouter(prefix="/research")


class ResearchExplainRequest(BaseModel):
    source: SourceDoc
    explanation_mode: str = "beginner"


class ResearchCompareRequest(BaseModel):
    left: SourceDoc
    right: SourceDoc


@router.get("/external-papers")
async def external_research_papers(query: str = "AI", limit: int = 20) -> dict:
    docs = await registry.gather(query, ["research"], max(1, min(limit, 25)))
    papers = sorted(
        docs,
        key=lambda item: item.research_metadata.citations
        if item.research_metadata and item.research_metadata.citations is not None else -1,
        reverse=True,
    )
    return {
        "query": query,
        "providers": sorted({paper.source for paper in papers}),
        "papers": [paper.model_dump(mode="json") for paper in papers[:limit]],
    }


@router.get("/citation-graph/{paper_id}")
async def research_citation_graph(paper_id: str) -> dict:
    identifier = paper_id if paper_id.startswith(("W", "https://")) else f"https://doi.org/{paper_id}"
    base = "https://api.openalex.org/works"
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
        response = await client.get(f"{base}/{identifier}")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Paper not found in OpenAlex")
        response.raise_for_status()
        work = response.json()
        openalex_id = (work.get("id") or "").rsplit("/", 1)[-1]
        citing_response = await client.get(base, params={"filter": f"cites:{openalex_id}", "per-page": 20})
        citing = citing_response.json().get("results", []) if citing_response.status_code < 400 else []
    return {
        "paper": {"id": openalex_id, "title": work.get("display_name"), "doi": work.get("doi")},
        "cited_by_count": work.get("cited_by_count", 0),
        "references": work.get("referenced_works", [])[:50],
        "citing_works": [{
            "id": item.get("id"), "title": item.get("display_name"),
            "year": item.get("publication_year"), "doi": item.get("doi"),
        } for item in citing],
        "full_text": {
            "open_access": (work.get("open_access") or {}).get("is_oa", False),
            "url": ((work.get("best_oa_location") or {}).get("pdf_url")
                    or (work.get("best_oa_location") or {}).get("landing_page_url")),
            "license": (work.get("best_oa_location") or {}).get("license"),
        },
    }


@router.get("/insights")
async def research_insights(query: str = "AI") -> dict:
    docs = store.search_documents(query, ["research"], limit=25)
    if not docs:
        docs = store.all_recent_documents(["research"], limit=25)
    themes = Counter(
        doc.research_metadata.theme
        for doc in docs
        if doc.research_metadata and doc.research_metadata.theme
    )
    venues = Counter(
        doc.research_metadata.venue
        for doc in docs
        if doc.research_metadata and doc.research_metadata.venue
    )
    code_count = sum(
        1 for doc in docs if doc.research_metadata and bool(doc.research_metadata.code_available)
    )
    return {
        "query": query,
        "theme_clusters": dict(themes.most_common(8)),
        "top_venues": dict(venues.most_common(8)),
        "code_available_count": code_count,
        "sample_papers": [doc.model_dump(mode="json") for doc in docs[:6]],
    }


@router.get("/papers")
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


@router.get("/paper/{paper_id}")
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

    related: List[SourceDoc] = []
    for doc in docs:
        if doc.url == match.url or not doc.research_metadata or not match.research_metadata:
            continue
        same_theme = doc.research_metadata.theme == match.research_metadata.theme
        shared_authors = set(doc.research_metadata.authors).intersection(
            match.research_metadata.authors
        )
        if same_theme or shared_authors:
            related.append(doc)

    explanation = await explainer.explain(match.title, [match], "deep", [], "bullet")
    return {
        "paper": match.model_dump(mode="json"),
        "summary": explanation,
        "related_papers": [doc.model_dump(mode="json") for doc in related[:6]],
    }


@router.get("/paper/{paper_id}/bibtex", response_class=PlainTextResponse)
async def research_paper_bibtex(paper_id: str) -> str:
    docs = store.all_recent_documents(["research"], limit=500)
    match = next((doc for doc in docs if doc.research_metadata and (doc.research_metadata.paper_id or "").lower() == paper_id.lower()), None)
    if not match:
        raise HTTPException(status_code=404, detail="Paper not found")
    metadata = match.research_metadata
    authors = " and ".join(metadata.authors) if metadata else "Unknown"
    year = match.published_at.year if match.published_at else "n.d."
    venue = metadata.venue if metadata and metadata.venue else ""
    key = "".join(ch for ch in paper_id if ch.isalnum())[:32] or "signalscope"
    return f"@article{{{key},\n  title={{{match.title}}},\n  author={{{authors}}},\n  year={{{year}}},\n  journal={{{venue}}},\n  url={{{match.url}}}\n}}"


@router.post("/explain-paper")
async def research_explain_paper(payload: ResearchExplainRequest) -> dict:
    explanation = await explainer.explain(
        payload.source.title, [payload.source], payload.explanation_mode, [], "bullet"
    )
    return {
        "paper": payload.source.model_dump(mode="json"),
        "summary": explanation["explanation"],
        "key_takeaways": explanation["key_takeaways"],
    }


@router.post("/compare-papers")
async def research_compare_papers(payload: ResearchCompareRequest) -> dict:
    left, right = payload.left, payload.right
    shared_authors = sorted(
        set(left.research_metadata.authors if left.research_metadata else [])
        & set(right.research_metadata.authors if right.research_metadata else [])
    )
    return {
        "left_title": left.title,
        "right_title": right.title,
        "same_theme": (
            (left.research_metadata.theme if left.research_metadata else None)
            == (right.research_metadata.theme if right.research_metadata else None)
        ),
        "left_theme": left.research_metadata.theme if left.research_metadata else None,
        "right_theme": right.research_metadata.theme if right.research_metadata else None,
        "shared_authors": shared_authors,
        "code_comparison": {
            "left": left.research_metadata.code_available if left.research_metadata else None,
            "right": right.research_metadata.code_available if right.research_metadata else None,
        },
    }
