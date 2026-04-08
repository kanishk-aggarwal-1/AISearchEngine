import asyncio
from typing import Dict, List

from backend.app.models import Category, SourceDoc
from backend.app.sources.arxiv import ArxivSourceProvider
from backend.app.sources.base import SourceProvider
from backend.app.sources.newsapi import NewsApiSourceProvider
from backend.app.sources.rss import RssSourceProvider
from backend.app.sources.sports import SportsDbSourceProvider


class SourceRegistry:
    def __init__(self) -> None:
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
                tasks.append(provider.search(query=query, limit=per_source_limit))

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
