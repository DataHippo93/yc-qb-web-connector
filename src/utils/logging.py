"""
Structured logging setup using structlog.

Includes a PII-redaction processor that masks SSN-shaped patterns
(\d{3}-\d{2}-\d{4} or 9 raw digits in SSN-likely contexts) before
the line ever reaches stdout/JSON output. See outputs/yc-qb-pii-policy.md.
"""
from __future__ import annotations

import logging
import re
import sys

import structlog


# SSN-shaped patterns (dashed and 9-raw-digit). 9-raw-digit can also be EIN
# but at log level we err on the side of masking. Production data should be
# in the structured fields, not in formatted log strings.
_SSN_DASHED = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DIGITS_9   = re.compile(r"\b\d{9}\b")


def _redact_pii(_, __, event_dict):
    """structlog processor: mask SSN-like substrings in any string value."""
    for k, v in list(event_dict.items()):
        if isinstance(v, str):
            v = _SSN_DASHED.sub("[REDACTED-SSN]", v)
            v = _DIGITS_9.sub("[REDACTED-9DIGITS]", v)
            event_dict[k] = v
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog with JSON output for production."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Silence noisy libraries
    logging.getLogger("spyne").setLevel(logging.WARNING)
    logging.getLogger("spyne.server").setLevel(logging.WARNING)
    logging.getLogger("lxml").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _redact_pii,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
