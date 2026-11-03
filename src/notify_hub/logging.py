"""Structured logging: structlog, JSON lines in the cluster so Loki can filter by field.

Example:
    >>> from notify_hub.logging import configure_logging, get_logger
    >>> configure_logging(level="INFO")  # doctest: +SKIP
    >>> get_logger(__name__).info("notify.sent", app="alfred", sent=1)  # doctest: +SKIP
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_configured = False


def configure_logging(*, level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog and the stdlib root logger. Idempotent."""
    global _configured
    if _configured:
        return

    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=numeric)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer(),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> Any:
    """Return a bound logger for a module."""
    return structlog.get_logger(name)


__all__ = ["configure_logging", "get_logger"]
