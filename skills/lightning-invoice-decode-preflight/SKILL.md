---
name: lightning invoice decode preflight
description: Walks a BOLT11 invoice in process and stops when it has no single payment hash.
summary: Read a Lightning invoice with the agent-bitcoin SDK before any payment.
version: 1.0.0
tags: lightning, bolt11, payments
keywords: bolt11, invoice, preflight, agent-bitcoin
use_cases: Check a Lightning invoice before any payment is attempted.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-invoice-decode-preflight-deployment-test.md
---

# Lightning invoice decode and preflight

Read one BOLT11 invoice with the agent-bitcoin SDK. Stop before any payment.

## Requirements

- Python 3.10+
- `pip install agent-bitcoin` with no version pin
- No LND unlock
- This path does not read `AGENT_BITCOIN_ALLOW_MAINNET`

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin.bolt11_invoice import inspect_payment_hashes

seen = inspect_payment_hashes(invoice)
```

`seen is None` means the invoice cannot be walked. Stop.
`seen[0] != 1` means the payment hash is missing or duplicated. Stop.

Do not print the invoice or the hash.

Amount, expiry, network, a missing amount, an amount under 100 sats, and an amount above the caller's max are `l402.ln_invoice_preflight.handle_request`. A plain `pip install agent-bitcoin` does not provide that module. A single payment hash from this walk is not clearance to pay.

## What to keep private

Do not print wallet secrets, macaroons, preimages, or BOLT11 invoices.
