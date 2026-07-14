"""Validation for outbound user-configured webhook destinations."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from backend.app.config import settings


class UnsafeWebhookURL(ValueError):
    pass


def _is_public_address(raw: str) -> bool:
    address = ipaddress.ip_address(raw)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


async def validate_webhook_url(url: str) -> str:
    clean = url.strip()
    if not clean or len(clean) > 2048:
        raise UnsafeWebhookURL("A valid webhook URL is required")
    parsed = urlparse(clean)
    if settings.webhook_require_https and parsed.scheme.lower() != "https":
        raise UnsafeWebhookURL("Webhook URLs must use HTTPS")
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeWebhookURL("Webhook URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise UnsafeWebhookURL("Webhook URLs cannot contain credentials")

    hostname = parsed.hostname.rstrip(".").lower()
    allowed = {item.strip().lower() for item in settings.webhook_allowed_hosts.split(",") if item.strip()}
    if allowed and hostname not in allowed:
        raise UnsafeWebhookURL("Webhook host is not allowed")

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeWebhookURL("Webhook host could not be resolved") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise UnsafeWebhookURL("Webhook host resolves to a non-public address")
    return clean
