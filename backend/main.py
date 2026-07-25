"""
Agent-Bitcoin Backend API

Security (Step 5):
  Mutating and sensitive routes require header:
    X-API-Key: <AGENT_BITCOIN_API_KEY>
  or:
    Authorization: Bearer <AGENT_BITCOIN_API_KEY>

  Set AGENT_BITCOIN_API_KEY in the environment (e.g. .env). If unset,
  protected routes return 503 so the API cannot run open by accident.
"""

from __future__ import annotations

import hmac
import os
import time
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from agent_bitcoin.lightning import LNDClient

load_dotenv()

app = FastAPI(
    title="Agent-Bitcoin Backend API",
    description="Lightning helpers for agents. Protected routes require X-API-Key.",
)

FEE_SATS = int(os.getenv("FEE_SATS", "1000"))
FEE_ADDRESS = os.getenv("FEE_ADDRESS")
MIN_PAYMENT_SATS = int(os.getenv("MIN_PAYMENT_SATS", "2000"))
MAX_INVOICE_SATS = int(os.getenv("MAX_INVOICE_SATS", "1000000"))
MAX_FEE_SEND_SATS = int(os.getenv("MAX_FEE_SEND_SATS", "100000"))
API_KEY = (os.getenv("AGENT_BITCOIN_API_KEY") or "").strip()

client = LNDClient()


class InvoiceRequest(BaseModel):
    memo: str = "Agent-Bitcoin Test"
    amount_sats: int = Field(..., ge=1)


class PayRequest(BaseModel):
    payment_request: str
    fee_limit_sats: int = 500


class FeeRequest(BaseModel):
    amount_sats: Optional[int] = None


def _extract_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> Optional[str]:
    if x_api_key:
        return x_api_key.strip()
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return authorization.strip()
    return None


async def require_api_key(
    provided: Optional[str] = Depends(_extract_api_key),
) -> None:
    """Require a configured API key on sensitive routes."""
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "API key not configured on server. "
                "Set AGENT_BITCOIN_API_KEY in the environment and restart the backend."
            ),
        )
    if not provided or not hmac.compare_digest(provided, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _validate_invoice_amount(amount_sats: int) -> None:
    if amount_sats < MIN_PAYMENT_SATS:
        raise HTTPException(
            status_code=400,
            detail=f"amount_sats must be >= {MIN_PAYMENT_SATS}",
        )
    if amount_sats > MAX_INVOICE_SATS:
        raise HTTPException(
            status_code=400,
            detail=f"amount_sats must be <= {MAX_INVOICE_SATS}",
        )


@app.get("/")
async def root():
    """Liveness only — no secrets, no balances."""
    return {
        "status": "running",
        "message": "Backend is up.",
        "auth_required": True,
        "auth_header": "X-API-Key",
    }


@app.get("/balance", dependencies=[Depends(require_api_key)])
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
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/invoices", dependencies=[Depends(require_api_key)])
async def create_invoice(req: InvoiceRequest):
    _validate_invoice_amount(req.amount_sats)
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
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/pay", dependencies=[Depends(require_api_key)])
async def pay_invoice(req: PayRequest):
    """Pay Lightning invoice from AWS node."""
    if not req.payment_request or not req.payment_request.strip():
        raise HTTPException(status_code=400, detail="payment_request is required")

    last_error = None
    for attempt in range(3):
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
            print(f"sendpayment attempt {attempt + 1} failed: {last_error}")
            if attempt < 2:
                time.sleep(5)

    raise HTTPException(
        status_code=400,
        detail=f"Payment failed after 3 attempts. Last error: {last_error}",
    )


@app.post("/send-fee", dependencies=[Depends(require_api_key)])
async def send_fee(req: Optional[FeeRequest] = None):
    """On-chain fee send to configured fee address."""
    amount = req.amount_sats if req and req.amount_sats is not None else FEE_SATS
    if not FEE_ADDRESS or amount <= 0:
        raise HTTPException(status_code=400, detail="Fee configuration missing")
    if amount > MAX_FEE_SEND_SATS:
        raise HTTPException(
            status_code=400,
            detail=f"amount_sats must be <= {MAX_FEE_SEND_SATS}",
        )

    try:
        print(f"Sending fee {amount} sats to configured FEE_ADDRESS")
        fee_tx = client._run("sendcoins", "--addr", FEE_ADDRESS, "--amt", str(amount))
        print(f"Fee sent TXID: {fee_tx.get('txid')}")
        return {
            "success": True,
            "txid": fee_tx.get("txid"),
            "amount_sats": amount,
            "address": FEE_ADDRESS,
        }
    except Exception as e:
        print(f"Fee failed: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    if not API_KEY:
        print(
            "WARNING: AGENT_BITCOIN_API_KEY is not set. "
            "Protected routes will return 503 until it is configured."
        )
    uvicorn.run(app, host="0.0.0.0", port=8000)
