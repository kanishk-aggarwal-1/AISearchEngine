import asyncio
import time
from typing import Dict, List

from backend.app.models import Category, SourceDoc
from backend.app.services.document_store import DocumentStore
from backend.app.sources.arxiv import ArxivSourceProvider
from backend.app.sources.base import SourceProvider
from backend.app.sources.newsapi import NewsApiSourceProvider
from backend.app.sources.rss import RssSourceProvider
from backend.app.sources.sports import SportsDbSourceProvider


class SourceRegistry:
    MAX_ATTEMPTS = 3

    def __init__(self, store: DocumentStore | None = None) -> None:
        self.store = store
        self.providers: Dict[Category, List[SourceProvider]] = {
            "tech": [
                RssSourceProvider("https://techcrunch.com/feed/", "TechCrunch", "tech"),
                RssSourceProvider("https://www.theverge.com/rss/index.xml", "The Verge", "tech"),
                RssSourceProvider("https://feeds.arstechnica.com/arstechnica/index", "Ars Technica", "tech"),
                RssSourceProvider("https://www.wired.com/feed/rss", "Wired", "tech"),
            ],
            "research": [
                ArxivSourceProvider(),
                RssSourceProvider("https://news.mit.edu/rss/research", "MIT Research", "research"),
            ],
            "sports": [
                RssSourceProvider("https://www.espn.com/espn/rss/news", "ESPN Headlines", "sports"),
                RssSourceProvider("https://feeds.bbci.co.uk/sport/rss.xml", "BBC Sport", "sports"),
                SportsDbSourceProvider(),
            ],
            "general": [
                RssSourceProvider("https://feeds.bbci.co.uk/news/world/rss.xml", "BBC World", "general"),
                RssSourceProvider("https://feeds.npr.org/1004/rss.xml", "NPR World", "general"),
                RssSourceProvider("https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "NYT World", "general"),
                NewsApiSourceProvider(),
            ],
        }

    async def gather(self, query: str, categories: List[Category], per_source_limit: int) -> List[SourceDoc]:
        tasks = []
        for category in categories:
            for provider in self.providers.get(category, []):
                source_name = getattr(provider, "source_name", provider.__class__.__name__)
                if self.store and not self.store.source_enabled(source_name):
                    continue
                tasks.append(self._provider_search(provider, category, query, per_source_limit))

        if not tasks:
            return []

        settled = await asyncio.gather(*tasks, return_exceptions=True)

        docs: List[SourceDoc] = []
        for result in settled:
            if isinstance(result, Exception):
                continue
            docs.extend(result)

        unique: dict[str, SourceDoc] = {}
        for doc in docs:
            key = doc.url.strip() or f"{doc.source}:{doc.title}"
            if key not in unique:
                unique[key] = doc

        return list(unique.values())

    async def _provider_search(self, provider: SourceProvider, category: Category, query: str, limit: int) -> List[SourceDoc]:
        source_name = getattr(provider, "source_name", provider.__class__.__name__)
        last_error = ""
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            started = time.perf_counter()
            try:
                docs = await provider.search(query=query, limit=limit)
                if self.store:
                    self.store.record_source_result(
                        source_name,
                        category,
                        len(docs),
                        error="",
                        latency_ms=(time.perf_counter() - started) * 1000.0,
                    )
                return docs
            except Exception as exc:
                last_error = f"attempt {attempt}/{self.MAX_ATTEMPTS}: {exc}"
                if attempt < self.MAX_ATTEMPTS:
                    await asyncio.sleep(0.35 * attempt)
                    continue
                if self.store:
                    self.store.record_source_result(
                        source_name,
                        category,
                        0,
                        error=last_error,
                        latency_ms=(time.perf_counter() - started) * 1000.0,
                    )
                return []
        return []
