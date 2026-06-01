import time
from typing import List

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.app.container import ingestion, metrics, store
from backend.app.dependencies import current_admin
from backend.app.models import Category, IngestionRunRecord, SourceStatus, SourceToggleRequest

router = APIRouter()


class IngestEventRequest(BaseModel):
    topic: str = Field(min_length=2)
    categories: List[Category] = Field(
        default_factory=lambda: ["tech", "research", "sports", "general"]
    )


# ── Admin ────────────────────────────────────────────────────────────────────

@router.get("/admin/dashboard")
async def admin_dashboard(request: Request, limit: int = 10) -> dict:
    current_admin(request)
    return {
        "snapshot": store.admin_snapshot(limit=max(1, min(limit, 50))),
        "metrics": metrics.snapshot(),
    }


@router.get("/admin/sources", response_model=List[SourceStatus])
async def admin_sources(request: Request, category: Category | None = None) -> List[SourceStatus]:
    current_admin(request)
    return store.get_source_statuses(category=category)


@router.put("/admin/sources/{source_name}", response_model=SourceStatus)
async def admin_toggle_source(
    request: Request,
    source_name: str,
    payload: SourceToggleRequest,
    category: str = "unknown",
) -> SourceStatus:
    current_admin(request)
    return store.set_source_enabled(source_name, payload.enabled, category=category)


@router.get("/admin/ingestion-runs", response_model=List[IngestionRunRecord])
async def admin_ingestion_runs(request: Request, limit: int = 20) -> List[IngestionRunRecord]:
    current_admin(request)
    return store.recent_ingestion_runs(limit=max(1, min(limit, 100)))


@router.post("/admin/reingest")
async def admin_reingest(request: Request, payload: IngestEventRequest) -> dict:
    current_admin(request)
    start = time.perf_counter()
    inserted = await ingestion.ingest_event(payload.topic, payload.categories)
    metrics.inc("ingestion.reingest.calls")
    metrics.observe("ingestion.reingest.latency", time.perf_counter() - start)
    metrics.inc("ingestion.documents_inserted", inserted)
    return {"ok": True, "inserted": inserted, "topic": payload.topic, "categories": payload.categories}


# ── Ingest triggers ───────────────────────────────────────────────────────────

@router.post("/ingest/run")
async def run_ingestion(request: Request) -> dict:
    current_admin(request)
    start = time.perf_counter()
    inserted = await ingestion.ingest_seed_topics()
    metrics.inc("ingestion.run.calls")
    metrics.observe("ingestion.run.latency", time.perf_counter() - start)
    metrics.inc("ingestion.documents_inserted", inserted)
    return {"ok": True, "inserted": inserted}


@router.post("/ingest/webhook")
async def ingest_webhook(request: Request, payload: IngestEventRequest) -> dict:
    current_admin(request)
    start = time.perf_counter()
    inserted = await ingestion.ingest_event(payload.topic, payload.categories)
    metrics.inc("ingestion.webhook.calls")
    metrics.observe("ingestion.webhook.latency", time.perf_counter() - start)
    metrics.inc("ingestion.documents_inserted", inserted)
    return {"ok": True, "inserted": inserted, "topic": payload.topic}
