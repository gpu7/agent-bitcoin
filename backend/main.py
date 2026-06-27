from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import os

from agent_bitcoin.lightning import LNDClient
from agent_bitcoin.models import Invoice

app = FastAPI(title="Agent-Bitcoin Backend API")

client = LNDClient()

class InvoiceRequest(BaseModel):
    memo: str
    amount_sats: int
    expiry_seconds: Optional[int] = 3600

class PaymentRequest(BaseModel):
    payment_request: str

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
    """Pay a Lightning invoice"""
    try:
        result = client._run("payinvoice", "--force", f"--pay_req={req.payment_request}")
        return {"status": "success", "result": result}
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