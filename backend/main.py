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


class FeeRequest(BaseModel):
    amount_sats: int = None  # optional override


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
            "total_sat": int(ln.get("balance", 0))
            + int(onchain.get("confirmed_balance", 0)),
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/invoices")
async def create_invoice(req: InvoiceRequest):
    try:
        result = client._run(
            "addinvoice", "--memo", req.memo, "--amt", str(req.amount_sats)
        )

        return {
            "payment_request": result.get("payment_request"),
            "r_hash": result.get("r_hash"),
            "amount_sats": req.amount_sats,
            "memo": req.memo,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/pay")
async def pay_invoice(req: PayRequest):
    """Pay Lightning invoice from AWS node"""
    last_error = None

    for attempt in range(3):  # Try up to 3 times
        try:
            result = client._run(
                "sendpayment",
                "--pay_req",
                req.payment_request,
                "--fee_limit",
                str(req.fee_limit_sats),
                "--json",
                "--force",
            )
            return {
                "success": True,
                "payment_hash": result.get("payment_hash"),
                "fee_sent": FEE_SATS,
                "fee_address": FEE_ADDRESS,
                "attempts": attempt + 1,
            }
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ sendpayment attempt {attempt + 1} failed: {last_error}")
            if attempt < 2:
                time.sleep(5)

    raise HTTPException(
        status_code=400,
        detail=f"Payment failed after 3 attempts. Last error: {last_error}",
    )


@app.post("/send-fee")
async def send_fee(req: FeeRequest = None):
    """Dedicated endpoint to send fee to Bitcoin wallet"""
    amount = req.amount_sats if req and req.amount_sats else FEE_SATS
    if not FEE_ADDRESS or amount <= 0:
        raise HTTPException(status_code=400, detail="Fee configuration missing")

    try:
        print(f"DEBUG: Sending fee {amount} sats to {FEE_ADDRESS}")
        fee_tx = client._run("sendcoins", "--addr", FEE_ADDRESS, "--amt", str(amount))
        print(f"✅ Fee sent! TXID: {fee_tx.get('txid')}")
        return {
            "success": True,
            "txid": fee_tx.get("txid"),
            "amount_sats": amount,
            "address": FEE_ADDRESS,
        }
    except Exception as e:
        print(f"⚠️ Fee failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
