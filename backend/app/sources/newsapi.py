from datetime import datetime
from typing import List

import httpx

from backend.app.config import settings
from backend.app.models import SourceDoc
from backend.app.sources.base import SourceProvider


class NewsApiSourceProvider(SourceProvider):
    BASE_URL = "https://newsapi.org/v2/everything"

    async def search(self, query: str, limit: int) -> List[SourceDoc]:
        if not settings.newsapi_key:
            return []

        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": min(limit, 20),
            "apiKey": settings.newsapi_key,
        }

        timeout = httpx.Timeout(settings.http_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        docs: List[SourceDoc] = []
        for article in payload.get("articles", []):
            published = None
            raw_published = article.get("publishedAt")
            if raw_published:
                try:
                    published = datetime.fromisoformat(raw_published.replace("Z", "+00:00"))
                except Exception:
                    published = None

            source_name = (article.get("source") or {}).get("name", "NewsAPI")
            docs.append(
                SourceDoc(
                    title=article.get("title", ""),
                    summary=article.get("description", "") or "",
                    url=article.get("url", ""),
                    source=source_name,
                    category="general",
                    published_at=published,
                    source_type="news",
                    bias_label="analysis" if "opinion" in source_name.lower() else "reporting",
                )
            )

        return docs[:limit]
