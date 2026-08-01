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
import logging
import os
import time
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from agent_bitcoin.constants import (
    DEFAULT_FEE_AMOUNT_SATS,
    max_fee_send_sats,
    max_invoice_sats,
    min_payment_sats,
)
from agent_bitcoin.lightning import LNDClient

load_dotenv()

logger = logging.getLogger("agent_bitcoin.backend")
logging.basicConfig(
    level=os.getenv("BACKEND_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="Agent-Bitcoin Backend API",
    description="Lightning helpers for agents. Protected routes require X-API-Key.",
)


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log method/path/status only — never headers or bodies (may contain keys/BOLT11)."""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        ms = int((time.time() - start) * 1000)
        logger.info(
            "http %s %s -> %s %sms",
            request.method,
            request.url.path,
            response.status_code,
            ms,
        )
        return response


app.add_middleware(AccessLogMiddleware)

FEE_SATS = int(os.getenv("FEE_SATS", str(DEFAULT_FEE_AMOUNT_SATS)))
FEE_ADDRESS = os.getenv("FEE_ADDRESS")
MIN_PAYMENT_SATS = min_payment_sats()
MAX_INVOICE_SATS = max_invoice_sats()
MAX_FEE_SEND_SATS = max_fee_send_sats()
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
        logger.warning("auth failed for protected route")
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
        ch = client.get_channel_balance()
        onchain = client.get_balance()
        ln = {
            "balance": str(ch.local_balance),
            "local_balance": {"sat": str(ch.local_balance)},
            "remote_balance": {"sat": str(ch.remote_balance)},
        }
        onchain_dict = {
            "total_balance": onchain.total_balance,
            "confirmed_balance": onchain.confirmed_balance,
            "unconfirmed_balance": onchain.unconfirmed_balance,
        }
        return {
            "lightning": ln,
            "onchain": onchain_dict,
            "total_sat": int(ch.local_balance) + int(onchain.confirmed_balance or 0),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/invoices", dependencies=[Depends(require_api_key)])
async def create_invoice(req: InvoiceRequest):
    _validate_invoice_amount(req.amount_sats)
    try:
        inv = client.create_invoice(req.memo, req.amount_sats)
        logger.info("invoice created amount_sats=%s", req.amount_sats)
        return {
            "payment_request": inv.payment_request,
            "r_hash": inv.r_hash,
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
            result = client.pay_invoice(
                req.payment_request.strip(),
                fee_limit_sats=req.fee_limit_sats,
            )
            if not result.success:
                raise RuntimeError(result.status or "payment failed")
            logger.info(
                "payment success attempt=%s payment_hash=%s",
                attempt + 1,
                result.payment_hash,
            )
            return {
                "success": True,
                "payment_hash": result.payment_hash,
                "fee_sent": FEE_SATS,
                "fee_address": FEE_ADDRESS,
                "attempts": attempt + 1,
            }
        except Exception as e:
            last_error = str(e)
            logger.warning("sendpayment attempt %s failed: %s", attempt + 1, last_error)
            if attempt < 2:
                time.sleep(5)

    logger.error("payment failed after 3 attempts")
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
        logger.info("fee send amount_sats=%s", amount)
        fee_tx = client.send_coins(FEE_ADDRESS, amount)
        logger.info("fee sent txid=%s", fee_tx.txid)
        return {
            "success": True,
            "txid": fee_tx.txid,
            "amount_sats": amount,
            "address": FEE_ADDRESS,
        }
    except Exception as e:
        logger.error("fee send failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    if not API_KEY:
        print(
            "WARNING: AGENT_BITCOIN_API_KEY is not set. "
            "Protected routes will return 503 until it is configured."
        )
    uvicorn.run(app, host="0.0.0.0", port=8000)
