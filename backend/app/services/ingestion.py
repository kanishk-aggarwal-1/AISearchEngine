import asyncio
from typing import List

from backend.app.models import Category
from backend.app.services.document_store import DocumentStore
from backend.app.services.enrichment_service import EnrichmentService
from backend.app.services.source_registry import SourceRegistry


class IngestionService:
    def __init__(
        self,
        registry: SourceRegistry,
        store: DocumentStore,
        enricher: EnrichmentService,
        per_source_limit: int,
    ):
        self.registry = registry
        self.store = store
        self.enricher = enricher
        self.per_source_limit = per_source_limit

    async def ingest_query(self, query: str, categories: List[Category]) -> int:
        docs = await self.registry.gather(query, categories, self.per_source_limit)
        docs = self.enricher.enrich(query, docs)
        return self.store.upsert_documents(docs)

    async def ingest_seed_topics(self) -> int:
        seeds = [
            ("AI agents", ["tech", "research"]),
            ("cybersecurity", ["tech", "general"]),
            ("NVIDIA", ["tech", "general"]),
            ("open-source LLM", ["tech", "research"]),
            ("NFL", ["sports"]),
            ("NBA", ["sports"]),
        ]

        total = 0
        for query, categories in seeds:
            total += await self.ingest_query(query, categories)
            await asyncio.sleep(0.2)

        return total

    async def ingest_event(self, topic: str, categories: List[Category]) -> int:
        return await self.ingest_query(topic, categories)
