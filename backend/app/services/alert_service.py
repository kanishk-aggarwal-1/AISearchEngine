import asyncio
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from backend.app.config import settings
from backend.app.services.document_store import DocumentStore
from backend.app.services.logging_service import get_logger
from backend.app.services.webhook_security import validate_webhook_url


class AlertService:
    def __init__(self, store: DocumentStore, metrics=None, email_service=None):
        self.store = store
        self.metrics = metrics
        self.email_service = email_service
        self.logger = get_logger("signalscope.alerts")

    async def process_alerts(self) -> int:
        delivered = 0
        now = datetime.now(timezone.utc)
        for alert in self.store.get_enabled_alerts():
            if not alert["delivery_enabled"]:
                continue
            if not alert["webhook_url"] and not alert["email_enabled"]:
                continue
            last_triggered = self._parse_dt(alert["last_triggered_at"])
            if not self._is_due(alert, now, last_triggered):
                continue
            docs = self.store.search_documents(alert["query"], alert["categories"], limit=6)
            if not docs:
                docs = self.store.all_recent_documents(alert["categories"], limit=6)
            if last_triggered:
                docs = [doc for doc in docs if doc.published_at and self._aware(doc.published_at) > last_triggered]
            if not docs:
                continue
            payload = {
                "alert_id": alert["id"], "user_id": alert["user_id"], "query": alert["query"],
                "categories": alert["categories"], "generated_at": now.isoformat(),
                "sources": [doc.model_dump(mode="json") for doc in docs[:5]],
            }
            channel_success = False
            if alert["webhook_url"]:
                channel_success = await self._deliver_webhook(alert, payload) or channel_success
            if alert["email_enabled"] and self.email_service:
                channel_success = await self._deliver_email(alert, docs) or channel_success
            if channel_success:
                self.store.mark_alert_triggered(alert["id"])
                delivered += 1
                if self.metrics:
                    self.metrics.inc("alerts.delivery_success")
            elif self.metrics:
                self.metrics.inc("alerts.delivery_failure")
        return delivered

    def _is_due(self, alert: dict, now: datetime, last_triggered: datetime | None) -> bool:
        if alert["digest_mode"] != "daily":
            return True
        if last_triggered and now - last_triggered < timedelta(hours=20):
            return False
        try:
            local_now = now.astimezone(ZoneInfo(alert["timezone"]))
        except ZoneInfoNotFoundError:
            local_now = now
        return local_now.hour >= alert["delivery_hour"]

    async def _deliver_webhook(self, alert: dict, payload: dict) -> bool:
        started = time.perf_counter()
        try:
            target = await validate_webhook_url(alert["webhook_url"])
            async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds), follow_redirects=False) as client:
                response = None
                for attempt in range(max(1, settings.webhook_delivery_attempts)):
                    try:
                        target = await validate_webhook_url(alert["webhook_url"])
                        response = await client.post(target, json=payload)
                        if response.status_code < 500:
                            break
                    except httpx.HTTPError:
                        if attempt + 1 >= settings.webhook_delivery_attempts:
                            raise
                    await asyncio.sleep(0.25 * (2 ** attempt))
            ok = response is not None and response.status_code < 400
            self.store.record_alert_delivery(
                alert["id"], alert["user_id"], "webhook", "delivered" if ok else "dead_letter",
                response.status_code if response else None,
                "" if ok else "Webhook rejected the delivery",
            )
            return ok
        except Exception as exc:
            self.store.record_alert_delivery(alert["id"], alert["user_id"], "webhook", "dead_letter", error=str(exc))
            self.logger.warning("alert_webhook_failed alert_id=%s error=%s", alert["id"], exc)
            return False
        finally:
            if self.metrics:
                self.metrics.observe("alerts.delivery_latency", time.perf_counter() - started)

    async def _deliver_email(self, alert: dict, docs: list) -> bool:
        lines = [f"SignalScope alert: {alert['query']}", ""]
        lines.extend(f"- {doc.title}: {doc.url}" for doc in docs[:5])
        try:
            ok = False
            for attempt in range(max(1, settings.webhook_delivery_attempts)):
                ok = await self.email_service.send(
                    recipient=alert["email"], subject=f"SignalScope alert: {alert['query']}",
                    text_body="\n".join(lines),
                    html_body="<h2>SignalScope alert</h2><ul>" + "".join(
                        f'<li><a href="{doc.url}">{doc.title}</a></li>' for doc in docs[:5]
                    ) + "</ul>",
                )
                if ok:
                    break
                if attempt + 1 < settings.webhook_delivery_attempts:
                    await asyncio.sleep(0.25 * (2 ** attempt))
            self.store.record_alert_delivery(
                alert["id"], alert["user_id"], "email", "delivered" if ok else "dead_letter",
                error="" if ok else "Email provider unavailable",
            )
            return ok
        except Exception as exc:
            self.store.record_alert_delivery(alert["id"], alert["user_id"], "email", "dead_letter", error=str(exc))
            return False

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _parse_dt(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return self._aware(datetime.fromisoformat(value))
        except Exception:
            return None
