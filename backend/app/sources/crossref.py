from datetime import datetime
from typing import List

import httpx

from backend.app.config import settings
from backend.app.models import ResearchMetadata, SourceDoc
from backend.app.sources.base import SourceProvider


class CrossrefSourceProvider(SourceProvider):
    source_name = "Crossref"
    BASE_URL = "https://api.crossref.org/works"

    async def search(self, query: str, limit: int) -> List[SourceDoc]:
        params = {
            "query.bibliographic": query or "artificial intelligence",
            "rows": min(limit, 25),
            "select": "DOI,title,abstract,author,published,container-title,is-referenced-by-count,URL",
        }
        headers = {"User-Agent": "SignalScope/1.0 (mailto:admin@localhost)"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
            response = await client.get(self.BASE_URL, params=params, headers=headers)
            if response.status_code >= 400:
                return []
            items = response.json().get("message", {}).get("items", [])
        docs: List[SourceDoc] = []
        for item in items:
            title = (item.get("title") or ["Untitled research work"])[0]
            parts = (item.get("published") or {}).get("date-parts", [[]])[0]
            published = None
            if parts:
                try:
                    published = datetime(
                        int(parts[0]), int(parts[1]) if len(parts) > 1 else 1, int(parts[2]) if len(parts) > 2 else 1
                    )
                except (TypeError, ValueError):
                    pass
            authors = [
                " ".join(filter(None, [author.get("given"), author.get("family")])) for author in item.get("author", [])
            ]
            doi = item.get("DOI") or ""
            abstract = (item.get("abstract") or "").replace("<jats:p>", "").replace("</jats:p>", "")
            docs.append(
                SourceDoc(
                    title=title,
                    summary=abstract[:1500] or f"Scholarly work registered with Crossref: {title}",
                    url=item.get("URL") or (f"https://doi.org/{doi}" if doi else "https://crossref.org"),
                    source="Crossref",
                    category="research",
                    published_at=published,
                    source_type="research",
                    bias_label="research",
                    credibility_score=0.8,
                    research_metadata=ResearchMetadata(
                        citations=item.get("is-referenced-by-count"),
                        venue=(item.get("container-title") or [None])[0],
                        authors=[author for author in authors if author][:20],
                        paper_id=doi or None,
                    ),
                )
            )
        return docs
