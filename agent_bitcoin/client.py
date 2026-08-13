import os
from dotenv import load_dotenv

from .constants import (
    DEFAULT_FEE_AMOUNT_SATS,
    autopay_allowed,
    fee_amount_sats,
    fee_send_allowed,
    max_daily_payment_sats,
    max_payment_sats,
    min_payment_sats,
    current_network,
)
from .lightning import LNDClient
from .models import (
    Invoice,
    InvoiceQuote,
    PayerDecisionInputs,
    PaymentResult,
    OnChainSendResult,
    LightningBalance,
    ChannelBalance,
)
from .spend_ledger import assert_can_spend, record_spend

load_dotenv()


def _invoice_amount_sats(decoded: dict) -> int:
    """Extract sat amount from lncli/gRPC decodepayreq dict."""
    for key in ("num_satoshis", "num_sats", "amt_sat"):
        if decoded.get(key) is not None:
            try:
                return int(decoded[key])
            except (TypeError, ValueError):
                pass
    for key in ("num_msat", "amt_msat"):
        if decoded.get(key) is not None:
            try:
                return int(decoded[key]) // 1000
            except (TypeError, ValueError):
                pass
    return 0


class AgentBitcoinClient:
    def __init__(self):
        self.lnd = LNDClient()

        self.fee_amount_sats = fee_amount_sats()
        if (
            os.getenv("FEE_AMOUNT_SATS", "").strip() == ""
            and os.getenv("FEE_SATS", "").strip()
        ):
            self.fee_amount_sats = int(
                os.getenv("FEE_SATS", str(DEFAULT_FEE_AMOUNT_SATS))
            )
        self.min_payment_sats = min_payment_sats()
        self.max_payment_sats = max_payment_sats()
        self.max_daily_payment_sats = max_daily_payment_sats()

    def create_invoice(
        self, memo: str, amount_sats: int, expiry_seconds: int = 3600
    ) -> Invoice:
        if amount_sats < self.min_payment_sats:
            raise ValueError(f"Minimum payment is {self.min_payment_sats} sats")
        if amount_sats > self.max_payment_sats:
            raise ValueError(f"Maximum payment is {self.max_payment_sats} sats")
        total = int(amount_sats) + int(self.fee_amount_sats)
        return self.lnd.create_invoice(memo, total, expiry_seconds)

    def create_invoice_quote(
        self,
        memo: str,
        amount_sats: int,
        expiry_seconds: int = 3600,
        platform_fee_sats: int | None = None,
    ) -> InvoiceQuote:
        """
        Payee: create one BOLT11 for requested amount + platform fee.

        amount_sats is the service amount (min/max apply to this).
        BOLT11 and total_cost_sats are amount + fee (default FEE_AMOUNT_SATS).
        collection is lightning_bundled — no separate on-chain fee send.
        """
        if amount_sats < self.min_payment_sats:
            raise ValueError(f"Minimum payment is {self.min_payment_sats} sats")
        if amount_sats > self.max_payment_sats:
            raise ValueError(f"Maximum payment is {self.max_payment_sats} sats")
        fee = (
            self.fee_amount_sats
            if platform_fee_sats is None
            else int(platform_fee_sats)
        )
        if fee < 0:
            raise ValueError("platform_fee_sats must be >= 0")
        total = int(amount_sats) + fee
        inv = self.lnd.create_invoice(memo, total, expiry_seconds)
        return InvoiceQuote(
            payment_request=inv.payment_request,
            amount_sats=int(amount_sats),
            platform_fee_sats=fee,
            transaction_fee_sats=fee,
            total_cost_sats=total,
            collection="lightning_bundled",
            memo=memo or "",
            r_hash=inv.r_hash,
            payment_hash=inv.payment_hash,
            network=current_network(),
        )

    def validate_invoice_quote(self, quote: InvoiceQuote | dict) -> InvoiceQuote:
        """
        Payer: check quote internal consistency and BOLT11 amount match.
        Raises ValueError if invalid.
        """
        if isinstance(quote, dict):
            quote = InvoiceQuote.model_validate(quote)
        if quote.amount_sats < 0 or quote.platform_fee_sats < 0:
            raise ValueError("amount_sats and platform_fee_sats must be >= 0")
        if quote.transaction_fee_sats != quote.platform_fee_sats:
            raise ValueError(
                "transaction_fee_sats must equal platform_fee_sats "
                "(aliases for the same fee)"
            )
        expected_total = quote.amount_sats + quote.platform_fee_sats
        if quote.total_cost_sats != expected_total:
            raise ValueError(
                f"total_cost_sats={quote.total_cost_sats} != "
                f"amount_sats+platform_fee_sats={expected_total}"
            )
        if not quote.payment_request:
            raise ValueError("payment_request is required")

        decoded = self.lnd.decode_pay_req(quote.payment_request.strip())
        bolt_amt = _invoice_amount_sats(decoded)
        if bolt_amt != quote.total_cost_sats:
            raise ValueError(
                f"BOLT11 amount {bolt_amt} does not match quote total_cost_sats "
                f"{quote.total_cost_sats} (requested {quote.amount_sats} + "
                f"fee {quote.platform_fee_sats})"
            )
        return quote

    def build_payer_decision_inputs(
        self,
        quote: InvoiceQuote | dict,
        routing_fee_limit_sats: int = 200,
    ) -> PayerDecisionInputs:
        """
        Payer: produce decision inputs for PaymentDecisionAgent / budget checks.
        Does not pay. Sets quote_valid False on validation failure (no raise).
        """
        if isinstance(quote, dict):
            try:
                q = InvoiceQuote.model_validate(quote)
            except Exception as e:
                return PayerDecisionInputs(
                    payment_request=str(quote.get("payment_request") or ""),
                    amount_sats=int(quote.get("amount_sats") or 0),
                    platform_fee_sats=int(quote.get("platform_fee_sats") or 0),
                    transaction_fee_sats=int(
                        quote.get("transaction_fee_sats")
                        or quote.get("platform_fee_sats")
                        or 0
                    ),
                    total_cost_sats=int(quote.get("total_cost_sats") or 0),
                    routing_fee_limit_sats=int(routing_fee_limit_sats),
                    quote_valid=False,
                    validation_error=str(e),
                )
        else:
            q = quote

        try:
            q = self.validate_invoice_quote(q)
            decoded = self.lnd.decode_pay_req(q.payment_request.strip())
            dest = str(decoded.get("destination") or "")
            return PayerDecisionInputs(
                payment_request=q.payment_request,
                amount_sats=q.amount_sats,
                platform_fee_sats=q.platform_fee_sats,
                transaction_fee_sats=q.transaction_fee_sats,
                total_cost_sats=q.total_cost_sats,
                routing_fee_limit_sats=int(routing_fee_limit_sats),
                quote_valid=True,
                validation_error=None,
                memo=q.memo or str(decoded.get("description") or ""),
                destination=dest,
            )
        except Exception as e:
            return PayerDecisionInputs(
                payment_request=q.payment_request,
                amount_sats=q.amount_sats,
                platform_fee_sats=q.platform_fee_sats,
                transaction_fee_sats=q.transaction_fee_sats,
                total_cost_sats=q.total_cost_sats,
                routing_fee_limit_sats=int(routing_fee_limit_sats),
                quote_valid=False,
                validation_error=str(e),
                memo=q.memo,
            )

    def pay_invoice(
        self, payment_request: str, fee_limit_sats: int = 200
    ) -> PaymentResult:
        if not payment_request:
            raise ValueError("Payment request is required")
        if not autopay_allowed():
            raise RuntimeError(
                "Lightning pay blocked: set AGENT_BITCOIN_ALLOW_AUTOPAY=1 "
                "(required on mainnet; optional kill-switch on lab nets with =0). "
                "See docs/mainnet-pilot.md Phase 2."
            )

        amount_sats = 0
        try:
            decoded = self.lnd.decode_pay_req(payment_request.strip())
            amount_sats = _invoice_amount_sats(decoded)
        except Exception:
            decoded = {}

        if amount_sats > 0:
            if amount_sats < self.min_payment_sats:
                raise ValueError(
                    f"Invoice amount {amount_sats} below minimum {self.min_payment_sats}"
                )
            if amount_sats > self.max_payment_sats:
                raise ValueError(
                    f"Invoice amount {amount_sats} above maximum {self.max_payment_sats}"
                )
            assert_can_spend(amount_sats, self.max_daily_payment_sats)

        result = self.lnd.pay_invoice(
            payment_request.strip(), fee_limit_sats=fee_limit_sats
        )
        if result.success:
            recorded = amount_sats or int(result.amount or 0)
            if recorded > 0:
                record_spend(recorded, payment_hash=result.payment_hash)
        return result

    def pay_invoice_quote(
        self,
        quote: InvoiceQuote | dict,
        routing_fee_limit_sats: int = 200,
        collect_platform_fee: bool = False,
    ) -> PaymentResult:
        """
        Payer: validate quote, budget total_cost_sats, pay BOLT11 amount on LN.

        Platform fee is already inside the BOLT11 (lightning_bundled).
        collect_platform_fee is ignored (no separate on-chain send).
        Daily/deposit ledger uses total_cost_sats.
        """
        _ = collect_platform_fee
        q = self.validate_invoice_quote(quote)
        if not autopay_allowed():
            raise RuntimeError(
                "Lightning pay blocked: set AGENT_BITCOIN_ALLOW_AUTOPAY=1 "
                "(required on mainnet; optional kill-switch on lab nets with =0). "
                "See docs/mainnet-pilot.md Phase 2."
            )
        if q.amount_sats < self.min_payment_sats:
            raise ValueError(
                f"Invoice amount {q.amount_sats} below minimum {self.min_payment_sats}"
            )
        if q.amount_sats > self.max_payment_sats:
            raise ValueError(
                f"Invoice amount {q.amount_sats} above maximum {self.max_payment_sats}"
            )
        assert_can_spend(q.total_cost_sats, self.max_daily_payment_sats)

        result = self.lnd.pay_invoice(
            q.payment_request.strip(), fee_limit_sats=routing_fee_limit_sats
        )
        if result.success:
            record_spend(q.total_cost_sats, payment_hash=result.payment_hash)
        return result

    def send_onchain(self, address: str, amount_sats: int) -> OnChainSendResult:
        if not fee_send_allowed():
            raise RuntimeError(
                "On-chain fee/send blocked on mainnet unless "
                "AGENT_BITCOIN_ALLOW_MAINNET_FEE=1 (pilot default off)."
            )
        if not address:
            raise ValueError("Destination address is required")
        if amount_sats <= 0:
            raise ValueError("Amount must be positive")
        return self.lnd.send_coins(address, amount_sats)

    def get_balance(self) -> LightningBalance:
        return self.lnd.get_balance()

    def get_channel_balance(self) -> ChannelBalance:
        return self.lnd.get_channel_balance()


def create_client() -> AgentBitcoinClient:
    """Factory function"""
    return AgentBitcoinClient()
