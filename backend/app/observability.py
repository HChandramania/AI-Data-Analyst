"""Allowlisted telemetry: never serialize arbitrary messages or exceptions."""

import json
import logging
from collections import Counter
from contextvars import ContextVar
from threading import Lock

request_id = ContextVar("request_id", default=None)
database_stats = ContextVar("database_stats", default=None)
logger = logging.getLogger("dbo.operations")
OPERATIONS = {
    "request",
    "ingestion",
    "analysis",
    "query",
    "search",
    "index",
    "cache",
    "dashboard",
    "export",
    "provider",
}
FIELDS = {"duration_ms", "status", "cache_hit", "reason", "db_ms", "db_queries", "outcome", "route", "provider"}
REASONS = {
    "hit",
    "expired",
    "not_found_or_changed",
    "source_deleted",
    "bypass",
    "provider_api_error",
    "provider_transport_timeout",
    "provider_deadline",
    "provider_unexpected_error",
}
counters = Counter()
lock = Lock()


def emit(operation, **fields):
    if operation not in OPERATIONS:
        return
    safe = {"event": operation, "request_id": request_id.get()}
    for key, value in fields.items():
        if key not in FIELDS:
            continue
        if (
            isinstance(value, (int, float, bool))
            or (key == "reason" and value in REASONS)
            or (key == "outcome" and value in {"success", "failure", "unavailable"})
            or (key == "provider" and value in {"gemini", "openrouter", "groq"})
            or (key == "route" and isinstance(value, str) and value.startswith("/api/v1/") and len(value) < 130)
        ):
            safe[key] = value
    with lock:
        counters[operation] += 1
    logger.info(json.dumps(safe))


class SafeJsonFormatter(logging.Formatter):
    def format(self, record):
        # Third-party logs may contain URLs, prompts or credentials. Never forward their text.
        if record.name == "dbo.operations":
            return record.getMessage()
        return json.dumps({"event": "runtime", "level": record.levelname})
