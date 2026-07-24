"""Structlog-based JSON logging configuration."""

from __future__ import annotations

import logging
from typing import Any

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure stdlib + structlog to emit JSON to stdout.

    Called once at process start. Idempotent: subsequent calls just update the
    log level without re-installing processors.
    """
    numeric_level = logging.getLevelName(level.upper())
    logging.basicConfig(level=numeric_level, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_context: Any) -> Any:
    """Return a bound structlog logger. Typed loosely so callers aren't locked
    to a specific structlog version."""
    return structlog.get_logger().bind(**initial_context)
