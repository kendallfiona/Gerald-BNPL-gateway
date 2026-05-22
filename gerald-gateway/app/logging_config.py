from __future__ import annotations

import logging
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter


class GeraldJsonFormatter(JsonFormatter):
    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["service"] = log_record.get("service", "gerald-gateway")
        log_record["event"] = log_record.get("event", record.getMessage())


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        GeraldJsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    request_id: str | None = None,
    user_id: str | None = None,
    duration_ms: float | None = None,
    level: int = logging.INFO,
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {"event": event}
    if request_id:
        payload["request_id"] = request_id
    if user_id:
        payload["user_id"] = user_id
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 2)
    payload.update(extra)
    logger.log(level, event, extra=payload)
