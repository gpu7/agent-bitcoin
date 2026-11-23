# Agensi invoice decode buyer check

Skill: `skills/lightning-invoice-decode-preflight/SKILL.md`.

The check follows the requirements that skill documents. It does not sign in to Agensi, it does not need an unlocked node, and it does not pay.

## What the buyer runs

Python 3.10+, from a checkout:

```bash
./examples/agensi-invoice-buyer-check.sh
```

The script changes to `/tmp` and runs the listing install with no version pin:

```bash
python3 -m venv /tmp/agensi-invoice-buyer
/tmp/agensi-invoice-buyer/bin/pip install --upgrade pip
/tmp/agensi-invoice-buyer/bin/pip install agent-bitcoin
```

The same install with uv:

```bash
uv venv /tmp/agensi-invoice-buyer
uv pip install --python /tmp/agensi-invoice-buyer/bin/python agent-bitcoin
```

The in-process check is:

```python
from agent_bitcoin.bolt11_invoice import inspect_payment_hashes

seen = inspect_payment_hashes(invoice)
```

`None` means the invoice cannot be walked. A count other than 1 means the payment hash is missing or duplicated. `AGENT_BITCOIN_ALLOW_MAINNET` is not required. Amount, expiry, network, a missing amount, an amount under 100 sats, and an amount above the caller's max are `l402.ln_invoice_preflight.handle_request`. That module is not in the pip package.

## What success looks like

The script prints the package version, `inspect_payment_hashes present`, `mainnet_latch=unset`, and `bad_invoice`. It exits 0. The invalid samples are `lnbc1notvalid` and an empty string. Both return `None`.

`tests/test_agensi_invoice_buyer.py` covers the same checks in the normal pytest run.
