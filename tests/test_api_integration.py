import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, BnplDecision, BnplInstallment, BnplPlan, get_db
from app.main import app

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _load_txs(user_id: str):
    path = ROOT / "bank_stub" / f"transactions_{user_id}.json"
    return json.loads(path.read_text())["transactions"]


def test_decision_endpoint_user_good(client, db_session):
    with patch(
        "app.services.fetch_transactions",
        new=AsyncMock(return_value=_load_txs("user_good")),
    ), patch("app.services.deliver_ledger_webhook", new=AsyncMock(return_value=True)):
        response = client.post(
            "/v1/decision",
            json={"user_id": "user_good", "amount_cents_requested": 40000},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["approved"] is True
    assert body["credit_limit_cents"] == 60000
    assert body["amount_granted_cents"] == 40000
    assert "plan_id" in body
    assert body["decision_factors"]["risk_score"] >= 85

    plan = client.get(f"/v1/plan/{body['plan_id']}")
    assert plan.status_code == 200
    installments = plan.json()["installments"]
    assert len(installments) == 4
    assert sum(i["amount_cents"] for i in installments) == 40000

    history = client.get("/v1/decision/history", params={"user_id": "user_good"})
    assert history.status_code == 200
    assert len(history.json()["decisions"]) == 1


def test_decision_decline_overdraft(client):
    with patch(
        "app.services.fetch_transactions",
        new=AsyncMock(return_value=_load_txs("user_overdraft")),
    ), patch("app.services.deliver_ledger_webhook", new=AsyncMock(return_value=True)):
        response = client.post(
            "/v1/decision",
            json={"user_id": "user_overdraft", "amount_cents_requested": 40000},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["approved"] is False
    assert body.get("plan_id") is None


def test_plan_not_found(client):
    response = client.get(f"/v1/plan/{uuid.uuid4()}")
    assert response.status_code == 404
