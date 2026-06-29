from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import os
import subprocess

from agent_bitcoin.lightning import LNDClient

app = FastAPI(title="Agent-Bitcoin Backend API")

# === Configuration ===
FEE_SATS = int(os.getenv("FEE_SATS", 1000))
FEE_ADDRESS = os.getenv("FEE_ADDRESS")

# Simple client for now
client = LNDClient()

if not FEE_ADDRESS:
    print("⚠️  WARNING: FEE_ADDRESS environment variable is not set!")

class InvoiceRequest(BaseModel):
    memo: str
    amount_sats: int
    expiry_seconds: Optional[int] = 3600

class PaymentRequest(BaseModel):
    payment_request: str

@app.get("/balance")
async def get_balance():
    """Get Lightning + on-chain balance"""
    try:
        ln_balance = client._run("channelbalance")
        wallet_balance = client._run("walletbalance")
        return {
            "lightning": ln_balance,
            "onchain": wallet_balance,
            "total_sat": int(ln_balance.get("balance", 0)) + int(wallet_balance.get("confirmed_balance", 0))
        }
    except Exception as e:
        return {"error": str(e)}

# TODO: Add other endpoints later

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
