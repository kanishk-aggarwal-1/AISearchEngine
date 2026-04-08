from datetime import datetime
from typing import List

import feedparser

from backend.app.models import ResearchMetadata, SourceDoc
from backend.app.sources.base import SourceProvider


class ArxivSourceProvider(SourceProvider):
    BASE_URL = "http://export.arxiv.org/api/query"

    async def search(self, query: str, limit: int) -> List[SourceDoc]:
        query_term = query.strip() or "AI"
        api_url = (
            f"{self.BASE_URL}?search_query=all:{query_term}&start=0&max_results={limit}"
            "&sortBy=submittedDate&sortOrder=descending"
        )
        parsed = feedparser.parse(api_url)
        docs: List[SourceDoc] = []

        for entry in parsed.entries:
            published = None
            raw_published = getattr(entry, "published", "")
            if raw_published:
                try:
                    published = datetime.fromisoformat(raw_published.replace("Z", "+00:00"))
                except Exception:
                    published = None

            summary = getattr(entry, "summary", "").replace("\n", " ").strip()
            title = getattr(entry, "title", "").replace("\n", " ").strip()
            venue = getattr(entry, "arxiv_journal_ref", None)
            authors = [getattr(author, "name", "").strip() for author in getattr(entry, "authors", []) if getattr(author, "name", "").strip()]
            links = getattr(entry, "links", []) or []
            code_url = None
            for link in links:
                href = getattr(link, "href", "")
                if "github.com" in href or "gitlab.com" in href:
                    code_url = href
                    break
            code_available = bool(code_url) or "github" in summary.lower() or "code" in summary.lower()

            docs.append(
                SourceDoc(
                    title=title,
                    summary=summary[:1000],
                    url=getattr(entry, "id", ""),
                    source="arXiv",
                    category="research",
                    published_at=published,
                    source_type="research",
                    bias_label="research",
                    research_metadata=ResearchMetadata(
                        citations=None,
                        venue=venue,
                        code_available=code_available,
                        code_url=code_url,
                        authors=authors[:8],
                        paper_id=getattr(entry, "id", "").rsplit("/", 1)[-1] or None,
                    ),
                )
            )

        return docs
