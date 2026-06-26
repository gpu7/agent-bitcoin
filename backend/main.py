from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

# Import the SDK
from agent_bitcoin import create_client
from agent_bitcoin.models import PaymentResult

app = FastAPI(
    title="Agent-Bitcoin Backend",
    description="Enforced Lightning payments with mandatory transaction fee",
    version="0.1.0"
)

# Initialize SDK client
client = create_client()

# ====================== MODELS ======================
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
    message: str

# ====================== ROUTES ======================
@app.get("/")
async def health():
    return {"status": "healthy", "service": "agent-bitcoin-backend"}

@app.post("/invoices", response_model=dict)
async def create_invoice(req: CreateInvoiceRequest):
    """Create a Lightning invoice"""
    invoice = client.create_invoice(
        memo=req.memo,
        amount_sats=req.amount_sats,
        expiry_seconds=req.expiry_seconds
    )
    return invoice.model_dump()

@app.post("/payments", response_model=PaymentResponse)
async def pay_invoice(req: PayInvoiceRequest):
    """Pay a Lightning invoice + ENFORCE 1000 sat fee"""
    
    if not req.payment_request:
        raise HTTPException(400, "payment_request is required")

    # Step 1: Pay the Lightning invoice
    result: PaymentResult = client.pay_invoice(req.payment_request)
    
    if not result.success:
        return PaymentResponse(
            success=False,
            message=f"Lightning payment failed: {result.status}"
        )

    # Step 2: ENFORCE on-chain fee (this cannot be easily bypassed)
    try:
        fee_txid = client.send_onchain(
            address=os.getenv("FEE_WALLET_ADDRESS"),
            amount_sats=int(os.getenv("FEE_AMOUNT_SATS", 1000))
        )
        fee_message = f"Fee sent on-chain. TXID: {fee_txid}"
    except Exception as e:
        fee_message = f"Fee collection failed: {str(e)} (but Lightning payment succeeded)"

    return PaymentResponse(
        success=True,
        payment_hash=result.payment_hash,
        amount_sats=result.amount,
        fee_sats=1000,
        message=fee_message
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
