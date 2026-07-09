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
    return {"status": "running", "message": "Backend is up. LND may still be starting."}

@app.get("/balance")
async def get_balance():
    try:
        for _ in range(5):
            try:
                ln = client._run("channelbalance")
                onchain = client._run("walletbalance")
                return {
                    "lightning": ln,
                    "onchain": onchain,
                    "total_sat": int(ln.get("balance", 0)) + int(onchain.get("confirmed_balance", 0))
                }
            except Exception as e:
                if "starting up" in str(e).lower() or "not yet ready" in str(e).lower():
                    time.sleep(3)
                    continue
                raise
        return {"status": "starting", "message": "LND is still starting up. Please wait and try again."}
    except Exception as e:
        return {"error": str(e)}

@app.post("/invoices")
async def create_invoice(req: InvoiceRequest):
    """Create a Lightning invoice on the AWS LND node"""
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
    """Pay Lightning invoice + enforce fee to Bitcoin wallet"""
    try:
        # Lightning payment with retry
        for attempt in range(5):
            try:
                result = client._run(
                    "sendpayment",
                    "--pay_req", req.payment_request,
                    "--fee_limit", str(req.fee_limit_sats),
                    "--json",
                    "--force"
                )
                break
            except Exception as e:
                if attempt < 4:
                    time.sleep(8)
                    continue
                raise

        lightning_success = True

        # === Fee enforcement to Bitcoin wallet ===
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
                print(f"⚠️ Fee send failed (non-critical): {fee_e}")

        return {
            "success": True,
            "payment_hash": result.get("payment_hash"),
            "amount": result.get("amount"),
            "fee_sent": FEE_SATS if FEE_ADDRESS else 0,
            "fee_address": FEE_ADDRESS,
            "status": result.get("status")
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)