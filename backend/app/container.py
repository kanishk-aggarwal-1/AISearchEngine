"""
Singleton service instances shared across all routers.
Import from here rather than instantiating services in individual modules.
"""
from backend.app.services.alert_service import AlertService
from backend.app.services.cache_service import CacheService
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.email_service import EmailService
from backend.app.services.enrichment_service import EnrichmentService
from backend.app.services.explainer import ExplainerService
from backend.app.services.ingestion import IngestionService
from backend.app.services.logging_service import get_logger, setup_logging
from backend.app.services.observability_service import MetricsService
from backend.app.services.retriever import RetrieverService
from backend.app.services.scheduler import SchedulerService
from backend.app.services.source_registry import SourceRegistry
from backend.app.services.store_factory import create_store
from backend.app.services.vector_index_service import VectorIndexService
from backend.app.config import settings

setup_logging()
logger = get_logger("signalscope.api")
metrics = MetricsService()

store = create_store()
cache = CacheService()
registry = SourceRegistry(store)
enricher = EnrichmentService()
embedding_service = EmbeddingService()
retriever = RetrieverService(embedding_service)
explainer = ExplainerService()
vector_index = VectorIndexService()
ingestion = IngestionService(registry, store, enricher, settings.max_fetch_per_source)
alerts = AlertService(store, metrics=metrics)
scheduler = SchedulerService(ingestion, settings.scheduler_interval_minutes, alerts=alerts)
email_service = EmailService()
