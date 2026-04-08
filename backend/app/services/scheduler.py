import asyncio
from contextlib import suppress

from backend.app.services.ingestion import IngestionService
from backend.app.services.logging_service import get_logger


class SchedulerService:
    def __init__(self, ingestion: IngestionService, interval_minutes: int):
        self.ingestion = ingestion
        self.interval_seconds = max(5, interval_minutes * 60)
        self._task: asyncio.Task | None = None
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
        while True:
            try:
                inserted = await self.ingestion.ingest_seed_topics()
                self.logger.info("scheduler_ingest_completed inserted=%s", inserted)
            except Exception as exc:
                self.logger.warning("scheduler_ingest_failed error=%s", exc)
            await asyncio.sleep(self.interval_seconds)
