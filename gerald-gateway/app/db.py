from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    create_engine,
    select,
)
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class BnplDecision(Base):
    __tablename__ = "bnpl_decision"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Text, nullable=False)
    requested_cents = Column(BigInteger, nullable=False)
    approved = Column(Boolean, nullable=False)
    credit_limit_cents = Column(BigInteger, nullable=False)
    amount_granted_cents = Column(BigInteger, nullable=False)
    score_numeric = Column(Float, nullable=True)
    score_band = Column(Text, nullable=True)
    risk_factors = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    plan = relationship("BnplPlan", back_populates="decision", uselist=False)


class BnplPlan(Base):
    __tablename__ = "bnpl_plan"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_id = Column(UUID(as_uuid=True), ForeignKey("bnpl_decision.id"), nullable=False)
    user_id = Column(Text, nullable=False)
    total_cents = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    decision = relationship("BnplDecision", back_populates="plan")
    installments = relationship("BnplInstallment", back_populates="plan", cascade="all, delete-orphan")


class BnplInstallment(Base):
    __tablename__ = "bnpl_installment"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("bnpl_plan.id"), nullable=False)
    due_date = Column(Date, nullable=False)
    amount_cents = Column(BigInteger, nullable=False)
    status = Column(Text, nullable=False, default="scheduled")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    plan = relationship("BnplPlan", back_populates="installments")


class OutboundWebhook(Base):
    __tablename__ = "outbound_webhook"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(Text, nullable=False)
    payload = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    target_url = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_installment_schedule(total_cents: int, interval_days: int) -> list[tuple[date, int]]:
    """Four equal installments; remainder goes to the first payment."""
    today = datetime.now(timezone.utc).date()
    base = total_cents // 4
    remainder = total_cents % 4
    amounts = [base + remainder, base, base, base]
    return [
        (today + timedelta(days=interval_days * (i + 1)), amounts[i])
        for i in range(4)
    ]
