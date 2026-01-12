"""
Structured logging configuration using structlog.

Provides JSON-formatted logs for latency analysis and debugging in production.
All log entries include timestamps and can be easily parsed by log aggregators.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(
    level: str = "INFO",
    json_output: bool = True,
    include_timestamps: bool = True,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, output JSON formatted logs. If False, use
                    console-friendly colored output.
        include_timestamps: Whether to include timestamps in log entries.
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    # Common processors for all configurations
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if include_timestamps:
        shared_processors.insert(0, structlog.processors.TimeStamper(fmt="iso"))

    if json_output:
        # JSON output for production
        processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console output for development
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a configured logger instance.

    Args:
        name: Optional logger name. If not provided, the caller's module
              name will be used.

    Returns:
        A bound structlog logger instance.

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing order", order_id="abc123", amount=50.0)
    """
    return structlog.get_logger(name)


# Pre-configure with sensible defaults for import convenience
configure_logging(level="INFO", json_output=False)
