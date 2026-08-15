"""
Agent-Bitcoin Backend API

Security:
  Mutating and sensitive routes require header:
    X-API-Key: <AGENT_BITCOIN_API_KEY>
  or:
    Authorization: Bearer <AGENT_BITCOIN_API_KEY>

  Set AGENT_BITCOIN_API_KEY in the environment (e.g. .env). If unset,
  protected routes return 503 so the API cannot run open by accident.

  Bind: BACKEND_HOST (default 127.0.0.1) — do not expose publicly without TLS.
  Soft rate limit: BACKEND_RATE_LIMIT_PER_MIN (default 60; 0 = off).
"""

from __future__ import annotations

import hmac
import logging
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from agent_bitcoin.client import AgentBitcoinClient
from agent_bitcoin.constants import (
    max_invoice_sats,
    min_payment_sats,
)

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

BACKEND_HOST = (os.getenv("BACKEND_HOST") or "127.0.0.1").strip() or "127.0.0.1"
BACKEND_PORT = int(os.getenv("BACKEND_PORT") or "8000")
BACKEND_RATE_LIMIT_PER_MIN = int(os.getenv("BACKEND_RATE_LIMIT_PER_MIN") or "60")

_RATE_LIMITED_PATHS = frozenset({"/pay", "/invoices", "/balance"})
_rate_buckets: Dict[str, Deque[float]] = defaultdict(deque)


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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-client sliding window on sensitive paths (in-memory; single process)."""

    async def dispatch(self, request: Request, call_next):
        limit = BACKEND_RATE_LIMIT_PER_MIN
        path = request.url.path.rstrip("/") or "/"
        # normalize /balance etc
        check_path = path if path.startswith("/") else f"/{path}"
        if (
            limit > 0
            and request.method in ("GET", "POST")
            and (
                check_path in _RATE_LIMITED_PATHS
                or any(check_path.startswith(p) for p in _RATE_LIMITED_PATHS)
            )
        ):
            client = request.client.host if request.client else "unknown"
            key = f"{client}:{check_path}"
            now = time.time()
            window = 60.0
            bucket = _rate_buckets[key]
            while bucket and bucket[0] <= now - window:
                bucket.popleft()
            if len(bucket) >= limit:
                logger.warning(
                    "rate limit exceeded client=%s path=%s", client, check_path
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded; try again later."},
                )
            bucket.append(now)
        return await call_next(request)


app.add_middleware(RateLimitMiddleware)
app.add_middleware(AccessLogMiddleware)

MIN_PAYMENT_SATS = min_payment_sats()
MAX_INVOICE_SATS = max_invoice_sats()
API_KEY = (os.getenv("AGENT_BITCOIN_API_KEY") or "").strip()

# AgentBitcoinClient enforces min/max, daily spend, mainnet autopay
client = AgentBitcoinClient()


class InvoiceRequest(BaseModel):
    memo: str = "Agent-Bitcoin Test"
    amount_sats: int = Field(..., ge=1)


class PayRequest(BaseModel):
    payment_request: str
    fee_limit_sats: int = 500


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
    """
    Payee: create invoice + explicit quote package for independent payers.

    Returns BOLT11 for the requested amount (no platform fee).
    """
    _validate_invoice_amount(req.amount_sats)
    try:
        quote = client.create_invoice_quote(req.memo, req.amount_sats)
        logger.info(
            "invoice quote created amount_sats=%s total_cost_sats=%s",
            quote.amount_sats,
            quote.total_cost_sats,
        )
        return quote.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/pay", dependencies=[Depends(require_api_key)])
async def pay_invoice(req: PayRequest):
    """Pay Lightning invoice (policy: limits, daily cap, mainnet autopay flag)."""
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
                "attempts": attempt + 1,
            }
        except (ValueError, RuntimeError) as e:
            # Policy rejections — do not retry
            raise HTTPException(status_code=400, detail=str(e)) from e
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


if __name__ == "__main__":
    import uvicorn

    if not API_KEY:
        print(
            "WARNING: AGENT_BITCOIN_API_KEY is not set. "
            "Protected routes will return 503 until it is configured."
        )
    if BACKEND_HOST in ("0.0.0.0", "::"):
        print(
            "WARNING: BACKEND_HOST listens on all interfaces. "
            "Prefer 127.0.0.1 + SSH tunnel/TLS proxy for production."
        )
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)
