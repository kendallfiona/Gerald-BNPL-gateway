from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _running_in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _host_defaults() -> dict[str, str]:
    """URLs when gateway runs on your Mac (mocks exposed on localhost ports)."""
    return {
        "DATABASE_URL": "postgresql+psycopg://postgres:postgres@localhost:5433/gerald",
        "BANK_API_BASE": "http://localhost:8001",
        "LEDGER_WEBHOOK_URL": "http://localhost:8002/mock-ledger",
    }


def _docker_defaults() -> dict[str, str]:
    """URLs when gateway runs inside docker compose network."""
    return {
        "DATABASE_URL": "postgresql+psycopg://postgres:postgres@postgres:5432/gerald",
        "BANK_API_BASE": "http://bank:8000",
        "LEDGER_WEBHOOK_URL": "http://ledger:8000/mock-ledger",
    }


def _pick_env(key: str, runtime_defaults: dict[str, str]) -> str:
    """Use env var if set; rewrite docker-only hostnames when running on host."""
    value = os.getenv(key)
    if not value:
        return runtime_defaults[key]
    if not _running_in_docker() and key in ("BANK_API_BASE", "LEDGER_WEBHOOK_URL", "DATABASE_URL"):
        # e.g. BANK_API_BASE=http://bank:8000 does not resolve outside Docker
        if "://bank:" in value or value.startswith("http://bank/"):
            return runtime_defaults[key]
        if "://ledger:" in value or value.startswith("http://ledger/"):
            return runtime_defaults[key]
        if "://postgres:" in value or "@postgres:" in value:
            return runtime_defaults[key]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5433/gerald",
        alias="DATABASE_URL",
    )
    bank_api_base: str = Field(
        default="http://localhost:8001",
        alias="BANK_API_BASE",
    )
    ledger_webhook_url: str = Field(
        default="http://localhost:8002/mock-ledger",
        alias="LEDGER_WEBHOOK_URL",
    )
    service_name: str = Field(default="gerald-gateway", alias="SERVICE_NAME")
    webhook_max_attempts: int = Field(default=3, alias="WEBHOOK_MAX_ATTEMPTS")
    installment_interval_days: int = Field(default=14, alias="INSTALLMENT_INTERVAL_DAYS")


def load_settings() -> Settings:
    runtime = _docker_defaults() if _running_in_docker() else _host_defaults()
    return Settings(
        DATABASE_URL=_pick_env("DATABASE_URL", runtime),
        BANK_API_BASE=_pick_env("BANK_API_BASE", runtime),
        LEDGER_WEBHOOK_URL=_pick_env("LEDGER_WEBHOOK_URL", runtime),
        SERVICE_NAME=os.getenv("SERVICE_NAME", "gerald-gateway"),
    )


settings = load_settings()
