from fastapi import FastAPI, HTTPException
import os
import time
from pydantic import BaseModel

from agent_bitcoin.lightning import LNDClient

app = FastAPI(title="Agent-Bitcoin Backend API")

FEE_SATS = int(os.getenv("FEE_SATS", 1000))
FEE_ADDRESS = os.getenv("FEE_ADDRESS")

client = LNDClient()

class InvoiceRequest(BaseModel):
    memo: str = "Agent-Bitcoin Test"
    amount_sats: int

class PayRequest(BaseModel):
    payment_request: str
    fee_limit_sats: int = 500

@app.get("/")
async def root():
    return {"status": "running", "message": "Backend is up."}

@app.get("/balance")
async def get_balance():
    try:
        ln = client._run("channelbalance")
        onchain = client._run("walletbalance")
        return {
            "lightning": ln,
            "onchain": onchain,
            "total_sat": int(ln.get("balance", 0)) + int(onchain.get("confirmed_balance", 0))
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/invoices")
async def create_invoice(req: InvoiceRequest):
    try:
        result = client._run("addinvoice", "--memo", req.memo, "--amt", str(req.amount_sats))
        return {
            "payment_request": result.get("payment_request"),
            "r_hash": result.get("r_hash"),
            "amount_sats": req.amount_sats,
            "memo": req.memo
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/pay")
async def pay_invoice(req: PayRequest):
    """Pay Lightning invoice"""
    try:
        result = client._run(
            "sendpayment",
            "--pay_req", req.payment_request,
            "--fee_limit", str(req.fee_limit_sats),
            "--json",
            "--force"
        )

        # Fee enforcement (always attempt)
        if FEE_ADDRESS and FEE_SATS > 0:
            try:
                print(f"DEBUG: Sending fee {FEE_SATS} sats to {FEE_ADDRESS}")
                fee_tx = client._run(
                    "sendcoins",
                    "--addr", FEE_ADDRESS,
                    "--amt", str(FEE_SATS)
                )
                print(f"✅ Fee sent! TXID: {fee_tx.get('txid')}")
            except Exception as fee_e:
                print(f"⚠️ Fee failed: {fee_e}")

        return {
            "success": True,
            "payment_hash": result.get("payment_hash"),
            "fee_sent": FEE_SATS,
            "fee_address": FEE_ADDRESS
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)