from __future__ import annotations

import logging
import time
import uuid
from uuid import UUID

from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import metrics
from app.bank_client import BankClientError, BankUserNotFoundError
from app.config import settings
from app.db import Base, BnplDecision, BnplPlan, SessionLocal, engine, get_db
from app.logging_config import configure_logging, log_event
from app.services import get_decision_history, get_plan, process_decision

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Gerald BNPL Gateway", version="1.0.0")


@app.on_event("startup")
def init_database():
    """Ensure tables exist (init SQL only runs on first Postgres volume create)."""
    for attempt in range(1, 16):
        try:
            Base.metadata.create_all(bind=engine)
            with SessionLocal() as db:
                n = db.scalar(select(func.count()).select_from(BnplDecision)) or 0
            logger.info(
                "database_ready",
                extra={
                    "event": "database_ready",
                    "database": _public_database_url(),
                    "decision_rows": n,
                },
            )
            return
        except OperationalError:
            if attempt == 15:
                raise
            time.sleep(2)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception(
        "unhandled_error",
        extra={
            "event": "unhandled_error",
            "request_id": getattr(request.state, "request_id", None),
            "path": request.url.path,
        },
    )
    metrics.ERRORS.labels(
        endpoint=request.url.path, error_type=type(exc).__name__
    ).inc()
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "error": type(exc).__name__},
    )


def _public_database_url() -> str:
    parsed = urlparse(settings.database_url)
    host = parsed.hostname or "unknown"
    port = parsed.port or 5432
    db = parsed.path or "/gerald"
    scheme = parsed.scheme.split("+")[0]
    return f"{scheme}://{host}:{port}{db}"


class DecisionRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    amount_cents_requested: int = Field(..., gt=0)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    endpoint = request.url.path
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        metrics.ERRORS.labels(endpoint=endpoint, error_type="unhandled").inc()
        raise
    finally:
        duration = time.perf_counter() - start
        metrics.REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)
        metrics.REQUESTS.labels(
            method=request.method, endpoint=endpoint, status=str(status_code)
        ).inc()
        log_event(
            logger,
            "http_request",
            request_id=request_id,
            duration_ms=duration * 1000,
            method=request.method,
            path=endpoint,
            status_code=status_code,
        )


@app.get("/health")
def health():
    payload = {
        "status": "ok",
        "service": settings.service_name,
        "database_url": _public_database_url(),
        "bank_api_base": settings.bank_api_base,
        "ledger_webhook_url": settings.ledger_webhook_url,
        "decision_rows_visible": 0,
        "plan_rows_visible": 0,
        "db_reachable": False,
    }
    try:
        with SessionLocal() as db:
            payload["decision_rows_visible"] = (
                db.scalar(select(func.count()).select_from(BnplDecision)) or 0
            )
            payload["plan_rows_visible"] = (
                db.scalar(select(func.count()).select_from(BnplPlan)) or 0
            )
            payload["db_reachable"] = True
    except OperationalError as exc:
        payload["status"] = "degraded"
        payload["db_error"] = str(exc)
    return payload


@app.get("/metrics")
def prometheus_metrics():
    payload, content_type = metrics.metrics_payload()
    return Response(content=payload, media_type=content_type)


@app.post("/v1/decision")
async def create_decision(
    body: DecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    request_id = request.state.request_id
    try:
        return await process_decision(
            db,
            user_id=body.user_id,
            amount_cents_requested=body.amount_cents_requested,
            request_id=request_id,
        )
    except BankUserNotFoundError:
        metrics.ERRORS.labels(endpoint="/v1/decision", error_type="user_not_found").inc()
        raise HTTPException(status_code=404, detail="user not found")
    except BankClientError as exc:
        metrics.ERRORS.labels(endpoint="/v1/decision", error_type="bank_unavailable").inc()
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
    except Exception:
        db.rollback()
        raise


@app.get("/v1/plan/{plan_id}")
def fetch_plan(plan_id: UUID, db: Session = Depends(get_db)):
    plan = get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    return plan


@app.get("/v1/decision/history")
def decision_history(
    user_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    return {"user_id": user_id, "decisions": get_decision_history(db, user_id)}
