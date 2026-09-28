import asyncio
import uuid
from contextlib import suppress

from backend.app.config import settings
from backend.app.services.alert_service import AlertService
from backend.app.services.ingestion import IngestionService
from backend.app.services.logging_service import get_logger


class SchedulerService:
    def __init__(
        self,
        ingestion: IngestionService,
        interval_minutes: int,
        alerts: AlertService | None = None,
        cache=None,
    ):
        self.ingestion = ingestion
        self.alerts = alerts
        self.cache = cache
        self.interval_seconds = max(5, interval_minutes * 60)
        self._task: asyncio.Task | None = None
        self.owner = uuid.uuid4().hex
        self.logger = get_logger("signalscope.scheduler")

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="ingestion-scheduler")
        self.logger.info("scheduler_started interval_seconds=%s", self.interval_seconds)

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self.logger.info("scheduler_stopped")

    async def _run_loop(self) -> None:
        await self._run_once("first")
        while True:
            await asyncio.sleep(self.interval_seconds)
            await self._run_once("scheduled")

    async def _run_once(self, trigger: str) -> None:
        acquired = True
        store = getattr(self.ingestion, "store", None)
        using_redis = bool(self.cache and getattr(self.cache, "using_redis", False))
        if using_redis:
            acquired = await self.cache.acquire_lock("scheduler", self.owner, settings.scheduler_lock_seconds)
        elif store and hasattr(store, "acquire_scheduler_lock"):
            acquired = await asyncio.to_thread(
                store.acquire_scheduler_lock,
                "scheduler",
                self.owner,
                settings.scheduler_lock_seconds,
            )
        if not acquired:
            self.logger.info("scheduler_skipped trigger=%s reason=lock_held", trigger)
            return
        try:
            inserted = await self.ingestion.ingest_seed_topics()
            self.logger.info("scheduler_ingest_completed trigger=%s inserted=%s", trigger, inserted)
            if self.alerts:
                delivered = await self.alerts.process_alerts()
                self.logger.info("scheduler_alerts_completed trigger=%s delivered=%s", trigger, delivered)
            if store and hasattr(store, "cleanup_expired"):
                await asyncio.to_thread(store.cleanup_expired)
        except Exception as exc:
            self.logger.warning("scheduler_run_failed trigger=%s error=%s", trigger, exc)
        finally:
            if using_redis:
                await self.cache.release_lock("scheduler", self.owner)
            elif acquired and store and hasattr(store, "release_scheduler_lock"):
                await asyncio.to_thread(store.release_scheduler_lock, "scheduler", self.owner)
