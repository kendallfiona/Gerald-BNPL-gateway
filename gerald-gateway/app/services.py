from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app import metrics
from app.bank_client import BankClientError, BankUserNotFoundError, fetch_transactions
from app.db import BnplDecision, BnplInstallment, BnplPlan, build_installment_schedule
from app.logging_config import log_event
from app.scoring import (
    credit_limit_bucket_label,
    make_decision,
)
from app.webhook import deliver_ledger_webhook
from app.config import settings

logger = logging.getLogger(__name__)


async def process_decision(
    db: Session,
    *,
    user_id: str,
    amount_cents_requested: int,
    request_id: str,
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        transactions = await fetch_transactions(user_id, request_id=request_id)
    except BankUserNotFoundError:
        metrics.BANK_FETCH_FAILURES.inc()
        raise
    except BankClientError:
        metrics.BANK_FETCH_FAILURES.inc()
        raise

    approved, credit_limit, amount_granted, factors, band = make_decision(
        transactions, amount_cents_requested
    )

    decision = BnplDecision(
        id=uuid.uuid4(),
        user_id=user_id,
        requested_cents=amount_cents_requested,
        approved=approved,
        credit_limit_cents=credit_limit,
        amount_granted_cents=amount_granted,
        score_numeric=float(factors.risk_score),
        score_band=band,
        risk_factors=factors.as_dict(),
    )
    db.add(decision)

    plan_id: str | None = None
    if approved and amount_granted > 0:
        plan = BnplPlan(
            id=uuid.uuid4(),
            decision_id=decision.id,
            user_id=user_id,
            total_cents=amount_granted,
        )
        db.add(plan)
        db.flush()
        plan_id = str(plan.id)

        for due_date, amount in build_installment_schedule(
            amount_granted, settings.installment_interval_days
        ):
            db.add(
                BnplInstallment(
                    id=uuid.uuid4(),
                    plan_id=plan.id,
                    due_date=due_date,
                    amount_cents=amount,
                    status="scheduled",
                )
            )

        await deliver_ledger_webhook(
            db,
            event_type="bnpl.approved",
            payload={
                "event": "bnpl.approved",
                "user_id": user_id,
                "decision_id": str(decision.id),
                "plan_id": plan_id,
                "amount_granted_cents": amount_granted,
                "credit_limit_cents": credit_limit,
            },
            request_id=request_id,
        )

    db.commit()

    if approved:
        metrics.APPROVED.inc()
    else:
        metrics.DECLINED.inc()
    metrics.CREDIT_LIMIT_BUCKET.labels(
        bucket=credit_limit_bucket_label(credit_limit)
    ).inc()

    duration_ms = (time.perf_counter() - start) * 1000
    log_event(
        logger,
        "decision_completed",
        request_id=request_id,
        user_id=user_id,
        duration_ms=duration_ms,
        approved=approved,
        risk_score=factors.risk_score,
        credit_limit_cents=credit_limit,
    )

    response: dict[str, Any] = {
        "approved": approved,
        "credit_limit_cents": credit_limit,
        "amount_granted_cents": amount_granted,
        "decision_factors": factors.as_dict(),
    }
    if plan_id:
        response["plan_id"] = plan_id
    return response


def get_plan(db: Session, plan_id: uuid.UUID) -> dict[str, Any] | None:
    plan = db.scalar(
        select(BnplPlan)
        .where(BnplPlan.id == plan_id)
        .options(joinedload(BnplPlan.installments))
    )
    if not plan:
        return None
    installments = sorted(plan.installments, key=lambda i: i.due_date)
    return {
        "plan_id": str(plan.id),
        "user_id": plan.user_id,
        "total_cents": plan.total_cents,
        "installments": [
            {
                "installment_id": str(inst.id),
                "due_date": inst.due_date.isoformat(),
                "amount_cents": inst.amount_cents,
                "status": inst.status,
            }
            for inst in installments
        ],
    }


def get_decision_history(db: Session, user_id: str) -> list[dict[str, Any]]:
    decisions = db.scalars(
        select(BnplDecision)
        .where(BnplDecision.user_id == user_id)
        .order_by(BnplDecision.created_at.desc())
    ).all()
    return [
        {
            "decision_id": str(d.id),
            "user_id": d.user_id,
            "requested_cents": d.requested_cents,
            "approved": d.approved,
            "credit_limit_cents": d.credit_limit_cents,
            "amount_granted_cents": d.amount_granted_cents,
            "risk_score": float(d.score_numeric) if d.score_numeric else None,
            "score_band": d.score_band,
            "decision_factors": d.risk_factors,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in decisions
    ]
