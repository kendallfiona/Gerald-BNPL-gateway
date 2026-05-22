from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.db import OutboundWebhook
from app.logging_config import log_event
from app import metrics

logger = logging.getLogger(__name__)


async def deliver_ledger_webhook(
    db: Session,
    *,
    event_type: str,
    payload: dict[str, Any],
    request_id: str | None = None,
) -> bool:
    webhook = OutboundWebhook(
        id=uuid.uuid4(),
        event_type=event_type,
        payload=payload,
        target_url=settings.ledger_webhook_url,
        status="pending",
    )
    db.add(webhook)
    db.flush()

    success = False
    for attempt in range(1, settings.webhook_max_attempts + 1):
        webhook.attempts = attempt
        webhook.last_attempt_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(settings.ledger_webhook_url, json=payload)
            elapsed = time.perf_counter() - start
            metrics.WEBHOOK_LATENCY.observe(elapsed)
            if response.status_code < 300:
                webhook.status = "delivered"
                success = True
                log_event(
                    logger,
                    "ledger_webhook_delivered",
                    request_id=request_id,
                    duration_ms=elapsed * 1000,
                    attempt=attempt,
                )
                break
            metrics.WEBHOOK_FAILURES.inc()
            webhook.status = "failed"
            log_event(
                logger,
                "ledger_webhook_failed",
                request_id=request_id,
                level=logging.WARNING,
                status_code=response.status_code,
                attempt=attempt,
            )
        except httpx.HTTPError as exc:
            metrics.WEBHOOK_FAILURES.inc()
            webhook.status = "failed"
            log_event(
                logger,
                "ledger_webhook_error",
                request_id=request_id,
                level=logging.WARNING,
                error=str(exc),
                attempt=attempt,
            )

    db.add(webhook)
    return success
