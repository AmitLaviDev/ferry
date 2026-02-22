"""Structured JSON logging configuration for AWS Lambda.

Uses structlog to produce JSON-formatted log lines that are natively
compatible with CloudWatch Logs Insights. Outputs to stdout via
PrintLoggerFactory (Lambda captures stdout as log lines).
"""

import logging

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for AWS Lambda JSON output.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
