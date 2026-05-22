"""BNPL risk scoring from 90-day bank transaction history.

Threshold rationale (see README for stakeholder context):
- Average daily balance: measures liquidity cushion for four biweekly installments.
- Income/spend ratio: credits vs debits; >1.0 means inflows exceed outflows.
- NSF / negative balance: proxies for payment stress and overdraft behavior.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


LOOKBACK_DAYS = 90

# Credit limit buckets in cents ($0 .. $600+)
LIMIT_BUCKETS_CENTS = [0, 10_000, 20_000, 30_000, 40_000, 50_000, 60_000]
# Minimum composite score (0-100) for each bucket above $0
_BUCKET_MIN_SCORE = [0, 25, 40, 55, 65, 75, 85]

# Hard declines regardless of score
MAX_NSF_FOR_APPROVAL = 5
MAX_NEGATIVE_BALANCE_TX_FOR_APPROVAL = 40
MIN_TRANSACTIONS_FOR_SCORING = 3


@dataclass(frozen=True)
class RiskFactors:
    risk_score: int
    avg_daily_balance_cents: int
    income_spend_ratio: float
    nsf_count: int
    negative_balance_tx_count: int
    transaction_count: int
    balance_component: int
    ratio_component: int
    stability_penalty: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "avg_daily_balance_cents": self.avg_daily_balance_cents,
            "avg_daily_balance": round(self.avg_daily_balance_cents / 100, 2),
            "income_spend_ratio": round(self.income_spend_ratio, 3),
            "nsf_count": self.nsf_count,
            "negative_balance_tx_count": self.negative_balance_tx_count,
            "transaction_count": self.transaction_count,
            "balance_component": self.balance_component,
            "ratio_component": self.ratio_component,
            "stability_penalty": self.stability_penalty,
        }


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def average_daily_balance_cents(transactions: list[dict[str, Any]]) -> tuple[int, int]:
    """Mean end-of-day balance over the last 90 days; carry forward last known balance."""
    if not transactions:
        return 0, 0

    sorted_txs = sorted(transactions, key=lambda t: (t["date"], t.get("transaction_id", "")))
    end = _parse_date(sorted_txs[-1]["date"])
    start = end - timedelta(days=LOOKBACK_DAYS - 1)

    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for tx in sorted_txs:
        by_date[tx["date"]].append(tx)

    balances: list[int] = []
    last_balance: int | None = None
    current = start
    while current <= end:
        day_key = current.isoformat()
        if day_key in by_date:
            last_balance = by_date[day_key][-1]["balance_cents"]
        if last_balance is not None:
            balances.append(last_balance)
        current += timedelta(days=1)

    if not balances:
        return 0, 0
    return int(sum(balances) / len(balances)), len(balances)


def income_spend_ratio(transactions: list[dict[str, Any]]) -> float:
    credits = sum(t["amount_cents"] for t in transactions if t["type"] == "credit")
    debits = sum(t["amount_cents"] for t in transactions if t["type"] == "debit")
    if debits == 0:
        return float("inf") if credits > 0 else 0.0
    return credits / debits


def count_incidents(transactions: list[dict[str, Any]]) -> tuple[int, int]:
    nsf = sum(1 for t in transactions if t.get("nsf"))
    negative = sum(1 for t in transactions if t["balance_cents"] < 0)
    return nsf, negative


def _balance_component(avg_daily_balance_cents: int) -> int:
    """0-35 points. $200+ avg (~20k cents) earns full balance points."""
    if avg_daily_balance_cents < 0:
        return 0
    if avg_daily_balance_cents < 5_000:
        return 5
    if avg_daily_balance_cents < 20_000:
        return 15
    if avg_daily_balance_cents < 50_000:
        return 25
    return 35


def _ratio_component(ratio: float) -> int:
    """0-30 points. Ratio >1.0 is positive cash flow."""
    if ratio == float("inf"):
        return 30
    if ratio >= 1.0:
        return 30
    if ratio >= 0.85:
        return 20
    if ratio >= 0.70:
        return 10
    if ratio >= 0.55:
        return 5
    return 0


def _stability_penalty(nsf_count: int, negative_count: int) -> int:
    """0-35 penalty. NSF events weigh more than incidental negative EOD balances."""
    penalty = min(35, nsf_count * 4 + int(negative_count * 0.25))
    return penalty


def compute_risk_score(transactions: list[dict[str, Any]]) -> RiskFactors:
    if len(transactions) < MIN_TRANSACTIONS_FOR_SCORING:
        return RiskFactors(
            risk_score=0,
            avg_daily_balance_cents=0,
            income_spend_ratio=0.0,
            nsf_count=0,
            negative_balance_tx_count=0,
            transaction_count=len(transactions),
            balance_component=0,
            ratio_component=0,
            stability_penalty=0,
        )

    avg_bal, _ = average_daily_balance_cents(transactions)
    ratio = income_spend_ratio(transactions)
    nsf, negative = count_incidents(transactions)

    balance_pts = _balance_component(avg_bal)
    ratio_pts = _ratio_component(ratio)
    penalty = _stability_penalty(nsf, negative)

    raw = 35 + balance_pts + ratio_pts - penalty
    score = max(0, min(100, raw))

    return RiskFactors(
        risk_score=score,
        avg_daily_balance_cents=avg_bal,
        income_spend_ratio=ratio if ratio != float("inf") else 999.0,
        nsf_count=nsf,
        negative_balance_tx_count=negative,
        transaction_count=len(transactions),
        balance_component=balance_pts,
        ratio_component=ratio_pts,
        stability_penalty=penalty,
    )


def score_to_credit_limit_cents(risk_score: int) -> int:
    """Map composite score to Gerald limit buckets."""
    limit = 0
    for bucket, min_score in zip(LIMIT_BUCKETS_CENTS, _BUCKET_MIN_SCORE):
        if risk_score >= min_score:
            limit = bucket
    return limit


def score_band(risk_score: int) -> str:
    if risk_score >= 85:
        return "excellent"
    if risk_score >= 65:
        return "good"
    if risk_score >= 40:
        return "fair"
    if risk_score > 0:
        return "limited"
    return "none"


def credit_limit_bucket_label(limit_cents: int) -> str:
    if limit_cents >= 60_000:
        return "600_plus"
    if limit_cents >= 50_000:
        return "500"
    if limit_cents >= 40_000:
        return "400"
    if limit_cents >= 30_000:
        return "300"
    if limit_cents >= 20_000:
        return "200"
    if limit_cents >= 10_000:
        return "100"
    return "0"


def should_hard_decline(factors: RiskFactors) -> bool:
    if factors.transaction_count < MIN_TRANSACTIONS_FOR_SCORING:
        return True
    if factors.avg_daily_balance_cents < 0:
        return True
    if factors.nsf_count > MAX_NSF_FOR_APPROVAL:
        return True
    if factors.negative_balance_tx_count > MAX_NEGATIVE_BALANCE_TX_FOR_APPROVAL:
        return True
    if factors.income_spend_ratio < 0.50 and factors.income_spend_ratio != 999.0:
        return True
    return False


def make_decision(
    transactions: list[dict[str, Any]], amount_requested_cents: int
) -> tuple[bool, int, int, RiskFactors, str]:
    factors = compute_risk_score(transactions)
    band = score_band(factors.risk_score)

    if should_hard_decline(factors):
        return False, 0, 0, factors, band

    credit_limit = score_to_credit_limit_cents(factors.risk_score)
    if credit_limit == 0:
        return False, 0, 0, factors, band

    amount_granted = min(amount_requested_cents, credit_limit)
    approved = amount_granted > 0
    return approved, credit_limit, amount_granted, factors, band
