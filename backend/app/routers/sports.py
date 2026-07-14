from collections import Counter

from fastapi import APIRouter
import httpx

from backend.app.config import settings
from backend.app.container import enricher, store
from backend.app.models import SourceDoc
from backend.app.routers.browse import filter_recent_docs, latest_headlines_for_category

router = APIRouter(prefix="/sports")


async def _sportsdb(path: str, **params: object) -> dict:
    url = f"https://www.thesportsdb.com/api/v1/json/3/{path}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
    return response.json()


@router.get("/teams/search")
async def sports_team_search(name: str) -> dict:
    teams = (await _sportsdb("searchteams.php", t=name)).get("teams") or []
    return {"teams": [{
        "team_id": team.get("idTeam"), "name": team.get("strTeam"),
        "league": team.get("strLeague"), "sport": team.get("strSport"),
        "country": team.get("strCountry"), "stadium": team.get("strStadium"),
        "badge": team.get("strBadge"),
    } for team in teams]}


@router.get("/team/{team_id}/roster")
async def sports_team_roster(team_id: int) -> dict:
    players = (await _sportsdb("lookup_all_players.php", id=team_id)).get("player") or []
    return {"team_id": team_id, "players": [{
        "player_id": player.get("idPlayer"), "name": player.get("strPlayer"),
        "position": player.get("strPosition"), "nationality": player.get("strNationality"),
        "number": player.get("strNumber"), "status": player.get("strStatus"),
        "signed": player.get("dateSigned"), "thumbnail": player.get("strThumb"),
    } for player in players]}


@router.get("/players/search")
async def sports_player_search(name: str) -> dict:
    players = (await _sportsdb("searchplayers.php", p=name)).get("player") or []
    return {"players": [{
        "player_id": player.get("idPlayer"), "name": player.get("strPlayer"),
        "team": player.get("strTeam"), "sport": player.get("strSport"),
        "position": player.get("strPosition"), "nationality": player.get("strNationality"),
    } for player in players]}


@router.get("/updates/{update_type}")
async def sports_updates(update_type: str, team: str = "", limit: int = 20) -> dict:
    if update_type not in {"injuries", "transactions"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="update_type must be injuries or transactions")
    terms = "injury injured questionable out" if update_type == "injuries" else "trade transfer signed waived transaction"
    query = " ".join(filter(None, [team, terms]))
    docs = store.search_documents(query, ["sports"], limit=max(1, min(limit, 50)))
    return {"type": update_type, "team": team, "updates": [doc.model_dump(mode="json") for doc in docs]}


@router.get("/schedule")
async def sports_schedule(league_id: int) -> dict:
    url = "https://www.thesportsdb.com/api/v1/json/3/eventsnextleague.php"
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
        response = await client.get(url, params={"id": league_id})
        response.raise_for_status()
    events = response.json().get("events") or []
    return {
        "league_id": league_id,
        "events": [{
            "event_id": item.get("idEvent"), "name": item.get("strEvent"),
            "league": item.get("strLeague"), "date": item.get("dateEvent"),
            "time": item.get("strTime"), "home": item.get("strHomeTeam"),
            "away": item.get("strAwayTeam"), "venue": item.get("strVenue"),
        } for item in events],
    }


@router.get("/standings")
async def sports_standings(league_id: int, season: str) -> dict:
    url = "https://www.thesportsdb.com/api/v1/json/3/lookuptable.php"
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
        response = await client.get(url, params={"l": league_id, "s": season})
        response.raise_for_status()
    rows = response.json().get("table") or []
    return {
        "league_id": league_id, "season": season,
        "standings": [{
            "rank": item.get("intRank"), "team": item.get("strTeam"),
            "played": item.get("intPlayed"), "wins": item.get("intWin"),
            "draws": item.get("intDraw"), "losses": item.get("intLoss"),
            "points": item.get("intPoints"),
        } for item in rows],
    }


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
