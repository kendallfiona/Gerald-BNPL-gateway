import pytest

from app.scoring import (
    average_daily_balance_cents,
    compute_risk_score,
    income_spend_ratio,
    make_decision,
    score_to_credit_limit_cents,
)


def test_score_to_limit_buckets():
    assert score_to_credit_limit_cents(0) == 0
    assert score_to_credit_limit_cents(24) == 0
    assert score_to_credit_limit_cents(25) == 10_000
    assert score_to_credit_limit_cents(84) == 50_000
    assert score_to_credit_limit_cents(85) == 60_000
    assert score_to_credit_limit_cents(100) == 60_000


def test_user_good_approved_at_600(load_user_transactions):
    txs = load_user_transactions("user_good")
    approved, limit, granted, factors, _ = make_decision(txs, 40_000)
    assert approved is True
    assert limit == 60_000
    assert granted == 40_000
    assert factors.risk_score >= 85
    assert factors.nsf_count == 0
    assert income_spend_ratio(txs) > 1.0


def test_user_overdraft_declined(load_user_transactions):
    txs = load_user_transactions("user_overdraft")
    approved, limit, granted, factors, _ = make_decision(txs, 40_000)
    assert approved is False
    assert limit == 0
    assert granted == 0
    assert factors.nsf_count > 5


def test_user_thin_no_history(load_user_transactions):
    txs = load_user_transactions("user_thin")
    approved, limit, _, factors, _ = make_decision(txs, 10_000)
    assert approved is False
    assert limit == 0
    assert factors.transaction_count == 0


def test_user_gig_declined(load_user_transactions):
    txs = load_user_transactions("user_gig")
    approved, _, _, factors, _ = make_decision(txs, 40_000)
    assert approved is False
    assert factors.income_spend_ratio < 0.55


def test_user_highutil_declined(load_user_transactions):
    txs = load_user_transactions("user_highutil")
    approved, limit, _, _, _ = make_decision(txs, 40_000)
    assert approved is False
    assert limit == 0


def test_average_daily_balance_carry_forward():
    txs = [
        {"date": "2025-01-01", "balance_cents": 10_000, "type": "credit", "amount_cents": 1},
        {"date": "2025-01-03", "balance_cents": 20_000, "type": "credit", "amount_cents": 1},
    ]
    avg, days = average_daily_balance_cents(txs)
    assert days == 3
    assert avg == 13333
