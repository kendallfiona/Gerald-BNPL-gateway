import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gerald-gateway"))

BANK_STUB = ROOT / "bank_stub"


@pytest.fixture
def load_user_transactions():
    def _load(user_id: str) -> list[dict]:
        path = BANK_STUB / f"transactions_{user_id}.json"
        return json.loads(path.read_text())["transactions"]

    return _load
