"""Structured JSON logging for the Python services.

Mirrors ``go/internal/logging``: JSON output, an ``arrival_id`` bound to every
line for the life of an arrival, and account identifiers loggable only through
a masking helper. There is no unmasked variant on purpose.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

from inspector import masking


def configure(component: str) -> None:
    """Install JSON logging. Call once at process start."""
    level = getattr(logging, os.environ.get("HM_LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(component=component)


def bind_arrival(arrival_id: str, correlation_id: str = "") -> None:
    """Bind identifiers for the remainder of this arrival's processing."""
    structlog.contextvars.bind_contextvars(arrival_id=arrival_id)
    if correlation_id:
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


def clear_arrival() -> None:
    structlog.contextvars.unbind_contextvars("arrival_id", "correlation_id")


def get(name: str = "inspector") -> Any:
    return structlog.get_logger(name)


def account(number: str, name: str) -> dict[str, str]:
    """The only sanctioned way to log an account identifier."""
    return {"number": masking.account_number(number), "name": masking.account_name(name)}
