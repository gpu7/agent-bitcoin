from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import os
import subprocess

from agent_bitcoin.lightning import LNDClient
from agent_bitcoin.models import Invoice

app = FastAPI(title="Agent-Bitcoin Backend API")

client = LNDClient()

# Fee configuration
FEE_SATS = 1000
FEE_ADDRESS = os.getenv("FEE_ADDRESS", "bcrt1q000000000000000000000000000000000000000")  # Will be overridden by env var

class InvoiceRequest(BaseModel):
    memo: str
    amount_sats: int
    expiry_seconds: Optional[int] = 3600

class PaymentRequest(BaseModel):
    payment_request: str

def send_fee_onchain():
    """Send 1000 sats fee on-chain to the configured address"""
    if not FEE_ADDRESS or "0000000000" in FEE_ADDRESS:
        print("⚠️  Warning: No valid FEE_ADDRESS set. Skipping fee collection.")
        return None
    
    try:
        result = client._run(
            "sendcoins",
            f"--addr={FEE_ADDRESS}",
            f"--amt={FEE_SATS}",
            "--conf_target=1"   # fast on regtest
        )
        print(f"✅ Fee of {FEE_SATS} sats sent on-chain to {FEE_ADDRESS}")
        return result
    except Exception as e:
        print(f"⚠️  Warning: Fee send failed: {e}")
        return None

@app.post("/invoices")
async def create_invoice(req: InvoiceRequest):
    """Create a new Lightning invoice"""
    invoice = client.create_invoice(
        memo=req.memo,
        amount_sats=req.amount_sats,
        expiry_seconds=req.expiry_seconds
    )
    return invoice

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

@app.post("/payments")
async def send_payment(req: PaymentRequest):
    """Pay a Lightning invoice + collect 1000 sat fee"""
    try:
        # 1. Pay the Lightning invoice
        result = client._run("payinvoice", "--force", f"--pay_req={req.payment_request}")
        
        # 2. Collect fee on-chain
        send_fee_onchain()
        
        return {
            "status": "success", 
            "payment": result,
            "fee_collected": FEE_SATS,
            "fee_address": FEE_ADDRESS
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/invoices/{payment_hash}")
async def get_invoice_status(payment_hash: str):
    """Check status of an invoice"""
    try:
        result = client._run("lookupinvoice", f"--r_hash={payment_hash}")
        return result
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)