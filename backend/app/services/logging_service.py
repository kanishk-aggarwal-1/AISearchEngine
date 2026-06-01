import logging
from typing import Optional

from backend.app.config import settings

try:
    from pythonjsonlogger import jsonlogger as _jsonlogger
    _JSON_AVAILABLE = True
except ImportError:  # pragma: no cover
    _JSON_AVAILABLE = False


def setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        return  # already configured (e.g., by a test runner)

    handler = logging.StreamHandler()
    handler.setLevel(level)

    if settings.log_format == "json" and _JSON_AVAILABLE:
        formatter = _jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s"
        )

    handler.setFormatter(formatter)
    root.addHandler(handler)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    return logging.getLogger(name or "signalscope")
