"""Product glue: PaymentDecisionAgent recommend → NWC client execute (N5).

Decision remains non-executing. Callers pass an explicit PAY/REJECT (or agent
result dict); this module only invokes NWC when approved.
"""

from __future__ import annotations

from typing import Any, Mapping

from agent_bitcoin.nwc.errors import NWCPolicyError


def decision_is_pay(decision: str | Mapping[str, Any] | Any) -> bool:
    """Return True if *decision* means the payer may proceed.

    Accepts:
    - str: ``"PAY"`` / ``"REJECT"`` (case-insensitive)
    - dict with ``decision`` or ``pay`` key
    - object with ``.pay`` (bool) or ``.decision`` (str)
    """
    if isinstance(decision, str):
        return decision.strip().upper() == "PAY"
    if isinstance(decision, Mapping):
        if "pay" in decision:
            return bool(decision["pay"])
        dec = str(decision.get("decision", "")).strip().upper()
        return dec == "PAY"
    if hasattr(decision, "pay"):
        return bool(getattr(decision, "pay"))
    if hasattr(decision, "decision"):
        return str(getattr(decision, "decision")).strip().upper() == "PAY"
    return False


def nwc_pay_if_approved(
    client: Any,
    decision: str | Mapping[str, Any] | Any,
    invoice: str,
    *,
    amount_sats: int | None = None,
) -> dict[str, Any] | None:
    """Call ``client.pay_invoice`` only when *decision* is PAY.

    Returns:
        NWC ``pay_invoice`` result dict, or ``None`` if rejected (no pay).

    Raises:
        NWCError / NWCPolicyError from the client on failed pays.
        TypeError if *client* has no ``pay_invoice``.
    """
    if not decision_is_pay(decision):
        return None
    if not invoice:
        raise NWCPolicyError("invoice required for approved pay")
    if not hasattr(client, "pay_invoice"):
        raise TypeError("client must provide pay_invoice()")
    return client.pay_invoice(invoice, amount_sats=amount_sats)


def rule_based_decision(
    amount_sats: int,
    *,
    max_sats: int | None = None,
    min_sats: int | None = None,
    context: str = "",
) -> dict[str, Any]:
    """Conservative offline decision (no LLM) for demos and CI.

    Uses project min/max when *min_sats* / *max_sats* are omitted.
    """
    from agent_bitcoin.constants import max_payment_sats, min_payment_sats

    lo = min_payment_sats() if min_sats is None else int(min_sats)
    hi = max_payment_sats() if max_sats is None else int(max_sats)
    amt = int(amount_sats)
    if amt < lo:
        return {
            "decision": "REJECT",
            "pay": False,
            "reason": f"amount {amt} below minimum {lo}",
            "amount_sats": amt,
            "context": context,
        }
    if amt > hi:
        return {
            "decision": "REJECT",
            "pay": False,
            "reason": f"amount {amt} exceeds maximum {hi}",
            "amount_sats": amt,
            "context": context,
        }
    return {
        "decision": "PAY",
        "pay": True,
        "reason": "within configured min/max (rule-based)",
        "amount_sats": amt,
        "context": context,
    }
