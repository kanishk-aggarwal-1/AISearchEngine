from datetime import datetime
from typing import List

import httpx

from backend.app.config import settings
from backend.app.models import ResearchMetadata, SourceDoc
from backend.app.sources.base import SourceProvider


def _abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    words = []
    for word, positions in inverted.items():
        words.extend((position, word) for position in positions)
    return " ".join(word for _, word in sorted(words))[:1500]


class OpenAlexSourceProvider(SourceProvider):
    BASE_URL = "https://api.openalex.org/works"

    async def search(self, query: str, limit: int) -> List[SourceDoc]:
        params = {"search": query or "artificial intelligence", "per-page": min(limit, 25)}
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
            response = await client.get(self.BASE_URL, params=params)
            if response.status_code >= 400:
                return []
            results = response.json().get("results", [])
        docs: List[SourceDoc] = []
        for work in results:
            title = work.get("display_name") or work.get("title") or "Untitled research work"
            published = None
            try:
                if work.get("publication_date"):
                    published = datetime.fromisoformat(work["publication_date"])
            except ValueError:
                pass
            authors = [
                item.get("author", {}).get("display_name", "")
                for item in work.get("authorships", [])
                if item.get("author", {}).get("display_name")
            ]
            source = (work.get("primary_location") or {}).get("source") or {}
            doi = work.get("doi") or ""
            docs.append(SourceDoc(
                title=title,
                summary=_abstract(work.get("abstract_inverted_index")) or f"Research work indexed by OpenAlex: {title}",
                url=doi or work.get("id", "https://openalex.org"),
                source="OpenAlex",
                category="research",
                published_at=published,
                source_type="research",
                bias_label="research",
                credibility_score=0.82,
                research_metadata=ResearchMetadata(
                    citations=work.get("cited_by_count"),
                    venue=source.get("display_name"),
                    theme=(work.get("primary_topic") or {}).get("display_name"),
                    authors=authors[:20],
                    paper_id=(work.get("id") or "").rsplit("/", 1)[-1] or None,
                ),
            ))
        return docs
