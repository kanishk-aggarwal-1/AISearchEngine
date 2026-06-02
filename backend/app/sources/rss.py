import asyncio
from datetime import datetime
from typing import List

import feedparser

from backend.app.models import SourceDoc
from backend.app.sources.base import SourceProvider

_RSS_TIMEOUT_SECONDS = 8


class RssSourceProvider(SourceProvider):
    def __init__(self, feed_url: str, source_name: str, category: str):
        self.feed_url = feed_url
        self.source_name = source_name
        self.category = category

    async def search(self, query: str, limit: int) -> List[SourceDoc]:
        loop = asyncio.get_event_loop()
        try:
            parsed = await asyncio.wait_for(
                loop.run_in_executor(None, feedparser.parse, self.feed_url),
                timeout=_RSS_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return []
        terms = [term.strip().lower() for term in query.split() if term.strip()]
        docs: List[SourceDoc] = []

        for entry in parsed.entries:
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "")
            haystack = f"{title} {summary}".lower()
            if terms and not any(term in haystack for term in terms):
                continue

            published = None
            if getattr(entry, "published_parsed", None):
                try:
                    published = datetime(*entry.published_parsed[:6])
                except Exception:
                    published = None

            docs.append(
                SourceDoc(
                    title=title,
                    summary=summary[:900],
                    url=getattr(entry, "link", ""),
                    source=self.source_name,
                    category=self.category,
                    published_at=published,
                    source_type="news",
                    bias_label="reporting",
                )
            )

            if len(docs) >= limit:
                break

        return docs
