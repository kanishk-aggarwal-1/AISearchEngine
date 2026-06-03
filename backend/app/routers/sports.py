from collections import Counter

from fastapi import APIRouter

from backend.app.container import enricher, store
from backend.app.models import SourceDoc
from backend.app.routers.browse import filter_recent_docs, latest_headlines_for_category

router = APIRouter(prefix="/sports")


@router.get("/insights")
async def sports_insights(query: str = "NBA") -> dict:
    docs = store.search_documents(query, ["sports"], limit=15)
    if not docs:
        docs = store.all_recent_documents(["sports"], limit=15)
    leagues = Counter(
        doc.sports_metadata.league
        for doc in docs
        if doc.sports_metadata and doc.sports_metadata.league
    )
    statuses = Counter(
        doc.sports_metadata.status
        for doc in docs
        if doc.sports_metadata and doc.sports_metadata.status
    )
    impacts = [
        doc.sports_metadata.injury_trade_impact
        for doc in docs
        if doc.sports_metadata and doc.sports_metadata.injury_trade_impact
    ]
    return {
        "query": query,
        "top_leagues": dict(leagues.most_common(5)),
        "status_breakdown": dict(statuses.most_common(5)),
        "trend_summary": [
            doc.sports_metadata.trend
            for doc in docs
            if doc.sports_metadata and doc.sports_metadata.trend
        ][:5],
        "injury_trade_impacts": impacts[:5],
        "sample_events": [doc.model_dump(mode="json") for doc in docs[:5]],
    }


@router.get("/dashboard")
async def sports_dashboard(team: str = "", recency_days: int = 7) -> dict:
    items = await latest_headlines_for_category("sports", 12, max(1, min(recency_days, 30)))
    docs = [SourceDoc.model_validate(item) for item in items]
    if team.strip():
        lower_team = team.lower()
        docs = [
            doc for doc in docs
            if lower_team in doc.title.lower()
            or lower_team in doc.summary.lower()
            or (
                doc.sports_metadata
                and (
                    (doc.sports_metadata.team or "").lower() == lower_team
                    or (doc.sports_metadata.opponent or "").lower() == lower_team
                )
            )
        ]
    latest_scores = [
        doc.model_dump(mode="json")
        for doc in docs
        if doc.sports_metadata and doc.sports_metadata.scoreline
    ][:6]
    upcoming = [
        doc.model_dump(mode="json")
        for doc in docs
        if doc.sports_metadata and not doc.sports_metadata.scoreline
    ][:6]
    return {
        "team": team,
        "news": [doc.model_dump(mode="json") for doc in docs[:8]],
        "latest_scores": latest_scores,
        "upcoming": upcoming,
        "top_leagues": Counter(
            doc.sports_metadata.league
            for doc in docs
            if doc.sports_metadata and doc.sports_metadata.league
        ).most_common(6),
    }


@router.get("/team/{team}")
async def sports_team_page(team: str, recency_days: int = 14) -> dict:
    docs = filter_recent_docs(store.all_recent_documents(["sports"], limit=80), recency_days)
    lower_team = team.lower()
    team_docs = [
        doc for doc in docs
        if lower_team in doc.title.lower()
        or lower_team in doc.summary.lower()
        or (
            doc.sports_metadata
            and (
                (doc.sports_metadata.team or "").lower() == lower_team
                or (doc.sports_metadata.opponent or "").lower() == lower_team
            )
        )
    ]
    return {
        "team": team,
        "latest": [doc.model_dump(mode="json") for doc in team_docs[:10]],
        "timeline": [
            item.model_dump(mode="json")
            for item in enricher.timeline(team_docs, max_points=8)
        ],
        "leagues": Counter(
            doc.sports_metadata.league
            for doc in team_docs
            if doc.sports_metadata and doc.sports_metadata.league
        ).most_common(5),
    }
