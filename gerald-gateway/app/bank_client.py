from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.logging_config import log_event

logger = logging.getLogger(__name__)


class BankClientError(Exception):
    pass


class BankUserNotFoundError(BankClientError):
    pass


async def fetch_transactions(user_id: str, request_id: str | None = None) -> list[dict[str, Any]]:
    url = f"{settings.bank_api_base.rstrip('/')}/bank/transactions"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params={"user_id": user_id})
    except httpx.ConnectError as exc:
        raise BankClientError(
            f"bank unreachable at {settings.bank_api_base}: {exc}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise BankClientError(f"bank request timed out: {exc}") from exc

    if response.status_code == 404:
        raise BankUserNotFoundError(f"user not found: {user_id}")
    if response.status_code >= 400:
        raise BankClientError(f"bank api error: {response.status_code}")

    payload = response.json()
    transactions = payload.get("transactions", [])
    log_event(
        logger,
        "bank_transactions_fetched",
        request_id=request_id,
        user_id=user_id,
        transaction_count=len(transactions),
    )
    return transactions
