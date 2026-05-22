import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Bank Server", version="1.0.0")


def _resolve_data_dir() -> Path:
    """Docker uses BANK_STUB_DIR=/bank_stub; locally use repo bank_stub/."""
    env_dir = os.getenv("BANK_STUB_DIR")
    if env_dir:
        return Path(env_dir)
    # Local dev: .../mock/bank_server/main.py -> repo/bank_stub
    here = Path(__file__).resolve().parent
    repo_stub = here.parent.parent / "bank_stub"
    if repo_stub.is_dir():
        return repo_stub
    return Path("/bank_stub")


DATA_DIR = _resolve_data_dir()

@app.get("/health")
def health():
    sample = DATA_DIR / "transactions_user_good.json"
    return {
        "status": "ok",
        "bank_stub_dir": str(DATA_DIR),
        "stub_accessible": sample.exists(),
    }

@app.get("/bank/transactions")
def get_transactions(user_id: str):
    file = DATA_DIR / f"transactions_{user_id}.json"
    if not file.exists():
        raise HTTPException(status_code=404, detail="user not found")
    return JSONResponse(content=json.loads(file.read_text()))
