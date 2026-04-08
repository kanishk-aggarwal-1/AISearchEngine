from datetime import datetime
from typing import List

import httpx

from backend.app.config import settings
from backend.app.models import SourceDoc, SportsMetadata
from backend.app.sources.base import SourceProvider


class SportsDbSourceProvider(SourceProvider):
    BASE_URL = "https://www.thesportsdb.com/api/v1/json/3/searchevents.php"

    async def search(self, query: str, limit: int) -> List[SourceDoc]:
        timeout = httpx.Timeout(settings.http_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(self.BASE_URL, params={"e": query})
            if response.status_code >= 400:
                return []
            payload = response.json()

        docs: List[SourceDoc] = []
        for event in payload.get("event", []) or []:
            published = None
            date = event.get("dateEvent")
            time = event.get("strTime")
            if date:
                try:
                    raw = f"{date}T{time or '00:00:00'}"
                    published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except Exception:
                    published = None

            home_team = event.get("strHomeTeam", "")
            away_team = event.get("strAwayTeam", "")
            home_score = event.get("intHomeScore")
            away_score = event.get("intAwayScore")
            scoreline = None
            if home_score is not None and away_score is not None:
                scoreline = f"{home_score}-{away_score}"

            league = event.get("strLeague", "Unknown")
            status = event.get("strStatus", "Unknown")
            title = event.get("strEvent", "")
            trend = "Momentum unclear"
            if "Final" in status and scoreline:
                trend = f"Final result recorded: {scoreline}."
            elif "Postponed" in status:
                trend = "Schedule volatility may impact team rhythm."
            elif "Live" in status or "In Progress" in status:
                trend = "Live action is underway."

            summary = " | ".join(
                [
                    f"League: {league}",
                    f"Status: {status}",
                    f"Matchup: {home_team} vs {away_team}",
                    f"Venue: {event.get('strVenue', 'Unknown')}",
                    f"Score: {scoreline or 'TBD'}",
                ]
            )

            docs.append(
                SourceDoc(
                    title=title,
                    summary=summary,
                    url=event.get("strVideo", "") or "https://www.thesportsdb.com/",
                    source="TheSportsDB",
                    category="sports",
                    published_at=published,
                    source_type="sports",
                    bias_label="reporting",
                    sports_metadata=SportsMetadata(
                        league=league,
                        status=status,
                        scoreline=scoreline,
                        trend=trend,
                        injury_trade_impact="No direct injury/trade signal in this source.",
                        team=home_team or None,
                        opponent=away_team or None,
                    ),
                )
            )

            if len(docs) >= limit:
                break

        return docs
