import asyncio
import smtplib
from email.message import EmailMessage

from backend.app.config import settings
from backend.app.services.logging_service import get_logger


class EmailService:
    def __init__(self) -> None:
        self.logger = get_logger("signalscope.email")

    @property
    def enabled(self) -> bool:
        return bool(settings.smtp_host and settings.smtp_from_email)

    async def send(self, recipient: str, subject: str, text_body: str, html_body: str = "") -> bool:
        if not self.enabled or not recipient.strip():
            return False
        return await asyncio.to_thread(self._send_sync, recipient.strip(), subject, text_body, html_body)

    def _send_sync(self, recipient: str, subject: str, text_body: str, html_body: str) -> bool:
        message = EmailMessage()
        message["Subject"] = subject
        from_label = f"{settings.smtp_from_name} <{settings.smtp_from_email}>" if settings.smtp_from_name else settings.smtp_from_email
        message["From"] = from_label
        message["To"] = recipient
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        try:
            if settings.smtp_use_ssl:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=settings.http_timeout_seconds) as server:
                    self._login_if_needed(server)
                    server.send_message(message)
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.http_timeout_seconds) as server:
                    server.ehlo()
                    if settings.smtp_use_tls:
                        server.starttls()
                        server.ehlo()
                    self._login_if_needed(server)
                    server.send_message(message)
            return True
        except Exception as exc:  # pragma: no cover - exercised in integration use
            self.logger.warning("smtp_send_failed recipient=%s error=%s", recipient, exc)
            return False

    @staticmethod
    def _login_if_needed(server: smtplib.SMTP) -> None:
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
