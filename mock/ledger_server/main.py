from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Ledger Server", version="1.0.0")

@app.get("/health")
def health(): return {"status": "ok"}

@app.post("/mock-ledger")
async def mock_ledger(request: Request, mode: str = "ok"):
    payload = await request.json()
    if mode == "fail":
        return JSONResponse(content={"status":"error","received":payload}, status_code=500)
    return {"status": "ok", "received": payload}
