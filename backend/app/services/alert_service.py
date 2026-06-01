import time
from datetime import datetime, timedelta, timezone

import httpx

from backend.app.config import settings
from backend.app.services.document_store import DocumentStore
from backend.app.services.logging_service import get_logger


class AlertService:
    def __init__(self, store: DocumentStore, metrics=None):
        self.store = store
        self.metrics = metrics
        self.logger = get_logger("signalscope.alerts")

    async def process_alerts(self) -> int:
        delivered = 0
        alerts = self.store.get_enabled_alerts()
        now = datetime.now(timezone.utc)

        for alert in alerts:
            if not alert["delivery_enabled"] or not alert["webhook_url"]:
                continue

            last_triggered = self._parse_dt(alert["last_triggered_at"])
            if alert["digest_mode"] == "daily" and last_triggered and now - last_triggered < timedelta(hours=24):
                continue

            docs = self.store.search_documents(alert["query"], alert["categories"], limit=6)
            if not docs:
                docs = self.store.all_recent_documents(alert["categories"], limit=6)
            if not docs:
                continue

            if last_triggered:
                fresh_docs = []
                for doc in docs:
                    if not doc.published_at:
                        continue
                    published = doc.published_at if doc.published_at.tzinfo else doc.published_at.replace(tzinfo=timezone.utc)
                    if published > last_triggered:
                        fresh_docs.append(doc)
                docs = fresh_docs

            if not docs:
                continue

            payload = {
                "alert_id": alert["id"],
                "user_id": alert["user_id"],
                "query": alert["query"],
                "categories": alert["categories"],
                "generated_at": now.isoformat(),
                "sources": [doc.model_dump(mode="json") for doc in docs[:5]],
            }

            try:
                started = time.perf_counter()
                async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
                    response = await client.post(alert["webhook_url"], json=payload)
                if self.metrics:
                    self.metrics.observe("alerts.delivery_latency", time.perf_counter() - started)
                if response.status_code < 400:
                    self.store.mark_alert_triggered(alert["id"])
                    delivered += 1
                    if self.metrics:
                        self.metrics.inc("alerts.delivery_success")
                else:
                    self.logger.warning("alert_delivery_failed alert_id=%s status=%s", alert["id"], response.status_code)
                    if self.metrics:
                        self.metrics.inc("alerts.delivery_failure")
            except Exception as exc:
                self.logger.warning("alert_delivery_failed alert_id=%s error=%s", alert["id"], exc)
                if self.metrics:
                    self.metrics.inc("alerts.delivery_failure")

        return delivered

    def _parse_dt(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
