from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Import SDK
from agent_bitcoin import create_client
from agent_bitcoin.models import PaymentResult, OnChainSendResult

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-bitcoin-backend")

app = FastAPI(
    title="Agent-Bitcoin Backend",
    description="Secure Lightning payments with mandatory 1000 sat transaction fee",
    version="0.1.0"
)

# Initialize SDK client
client = create_client()

# ====================== REQUEST / RESPONSE MODELS ======================
class CreateInvoiceRequest(BaseModel):
    memo: str
    amount_sats: int
    expiry_seconds: Optional[int] = 3600

class PayInvoiceRequest(BaseModel):
    payment_request: str
    description: Optional[str] = None

class PaymentResponse(BaseModel):
    success: bool
    payment_hash: Optional[str] = None
    amount_sats: Optional[int] = None
    fee_sats: int = 1000
    fee_txid: Optional[str] = None
    message: str

# ====================== ROUTES ======================
@app.get("/")
async def health():
    return {"status": "healthy", "service": "agent-bitcoin-backend"}

@app.post("/invoices", response_model=dict)
async def create_invoice(req: CreateInvoiceRequest):
    """Create Lightning invoice"""
    if req.amount_sats < client.min_payment_sats:
        raise HTTPException(400, f"Minimum payment is {client.min_payment_sats} sats")
    
    invoice = client.create_invoice(
        memo=req.memo,
        amount_sats=req.amount_sats,
        expiry_seconds=req.expiry_seconds
    )
    return invoice.model_dump()

@app.post("/payments", response_model=PaymentResponse)
async def pay_invoice(req: PayInvoiceRequest):
    """Pay Lightning invoice + **MANDATORY** 1000 sat on-chain fee"""
    
    if not req.payment_request:
        raise HTTPException(400, "payment_request is required")

    logger.info(f"Processing payment: {req.description or 'No description'}")

    # Step 1: Execute Lightning payment
    lightning_result: PaymentResult = client.pay_invoice(req.payment_request)

    if not lightning_result.success:
        logger.warning(f"Lightning payment failed: {lightning_result.status}")
        return PaymentResponse(
            success=False,
            message=f"Lightning payment failed: {lightning_result.status}"
        )

    # Step 2: ENFORCE fee collection (critical)
    fee_txid = None
    try:
        fee_result: OnChainSendResult = client.collect_transaction_fee()
        fee_txid = fee_result.txid
        logger.info(f"✅ Fee collected successfully. TXID: {fee_txid}")
        fee_message = f"Fee sent on-chain (TXID: {fee_txid[:12]}...)"
    except Exception as e:
        logger.error(f"❌ Fee collection failed: {str(e)}")
        fee_message = f"Lightning payment succeeded but fee collection failed: {str(e)}"

    return PaymentResponse(
        success=True,
        payment_hash=lightning_result.payment_hash,
        amount_sats=lightning_result.amount,
        fee_sats=client.fee_amount_sats,
        fee_txid=fee_txid,
        message=fee_message
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)