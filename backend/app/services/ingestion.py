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
        run_id = self.store.create_ingestion_run("query", query=query, categories=categories)
        try:
            docs = await self.registry.gather(query, categories, self.per_source_limit)
            docs = self.enricher.enrich(query, docs)
            inserted = self.store.upsert_documents(docs)
            self.store.finish_ingestion_run(
                run_id,
                status="completed",
                inserted_count=inserted,
                source_count=len({doc.source for doc in docs}),
                error_count=0,
            )
            return inserted
        except Exception as exc:
            self.store.finish_ingestion_run(
                run_id,
                status="failed",
                inserted_count=0,
                source_count=0,
                error_count=1,
                error_message=str(exc),
            )
            raise

    async def ingest_seed_topics(self) -> int:
        run_id = self.store.create_ingestion_run("scheduled", query="seed_topics", categories=[])
        seeds = [
            ("AI agents", ["tech", "research"]),
            ("cybersecurity", ["tech", "general"]),
            ("NVIDIA", ["tech", "general"]),
            ("open-source LLM", ["tech", "research"]),
            ("NFL", ["sports"]),
            ("NBA", ["sports"]),
        ]

        total = 0
        error_count = 0
        source_count = 0
        try:
            for query, categories in seeds:
                docs = await self.registry.gather(query, categories, self.per_source_limit)
                docs = self.enricher.enrich(query, docs)
                total += self.store.upsert_documents(docs)
                source_count += len({doc.source for doc in docs})
                await asyncio.sleep(0.2)
            self.store.finish_ingestion_run(
                run_id,
                status="completed",
                inserted_count=total,
                source_count=source_count,
                error_count=error_count,
            )
            return total
        except Exception as exc:
            self.store.finish_ingestion_run(
                run_id,
                status="failed",
                inserted_count=total,
                source_count=source_count,
                error_count=error_count + 1,
                error_message=str(exc),
            )
            raise

    async def ingest_event(self, topic: str, categories: List[Category]) -> int:
        return await self.ingest_query(topic, categories)
