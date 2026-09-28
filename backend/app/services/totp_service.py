"""Small RFC 6238 implementation used for authenticator-app MFA."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int, digits: int = 6) -> str:
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded.upper())
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def verify_code(secret: str, code: str, now: int | None = None, window: int = 1) -> bool:
    if not code.isdigit() or len(code) != 6:
        return False
    counter = int(now or time.time()) // 30
    return any(hmac.compare_digest(_code(secret, counter + offset), code) for offset in range(-window, window + 1))


def provisioning_uri(secret: str, email: str, issuer: str = "SignalScope AI") -> str:
    label = quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
