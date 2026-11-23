# Agensi L402 merchant buyer check

Skill: `skills/agent-to-merchant-l402/SKILL.md`.

The check follows the requirements that skill documents. It does not sign in to Agensi, and it does not pay.

## What the buyer runs

Python 3.10+, from a checkout:

```bash
./examples/agensi-l402-buyer-check.sh
```

The script changes to `/tmp` and runs the listing install with no version pin:

```bash
python3 -m venv /tmp/agensi-l402-buyer
/tmp/agensi-l402-buyer/bin/pip install --upgrade pip
/tmp/agensi-l402-buyer/bin/pip install agent-bitcoin
```

The same install with uv:

```bash
uv venv /tmp/agensi-l402-buyer
uv pip install --python /tmp/agensi-l402-buyer/bin/python agent-bitcoin
```

The merchant call, once an unlocked node is available, is:

```python
from agent_bitcoin import L402Client, create_client

response = L402Client(create_client()).fetch(url)
```

Report `status_code` and `paid`. Regtest is the default network. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only for an intentional mainnet spend. Set `AGENT_BITCOIN_ALLOW_AUTOPAY=1` only when autopay was requested. The checklist does not set either variable.

## What success looks like

The script prints the package version, `L402Client.fetch present`, the SDK configuration error for mainnet without `AGENT_BITCOIN_ALLOW_MAINNET`, and the autopay `RuntimeError`. It exits 0. `fetch` is not called.

`tests/test_agensi_l402_buyer.py` covers the same checks in the normal pytest run. A real payment stays manual and prefers regtest.
