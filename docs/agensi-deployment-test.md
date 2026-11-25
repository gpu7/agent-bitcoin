# Agensi public buyer check

Listing: [agent to agent lightning payment](https://www.agensi.io/skills/agent-to-agent-lightning-payment).

The check follows that page. It does not include the paid skill file, and it does not start LND, Docker, or a regtest chain.

## What the listing tells a buyer

| Listing step | What this check does |
|---|---|
| Connect an agent to `https://mcp.agensi.io/mcp/auth`, sign in, and click Allow | Not automated. The page requires an interactive sign-in. |
| Python 3.10+ and `pip install agent-bitcoin` | `examples/agensi-buyer-check.sh` creates a virtualenv and runs that install with no version pin. |
| Unlocked LND node | `--phase probe` calls `getinfo` on a node the operator already unlocked. The script does not create one. |
| `AGENT_BITCOIN_ALLOW_MAINNET` for mainnet | The checklist does not set this. Regtest is the default. A mainnet client without the variable raises the SDK configuration error. A mainnet pay also needs `AGENT_BITCOIN_ALLOW_AUTOPAY=1`. |
| SDK method `agent_bitcoin.pay_invoice` | `--phase install` calls `agent_bitcoin.pay_invoice("")`. A missing invoice raises `ValueError`. `AttributeError` fails the phase. |
| Nostr identities | The listing describes an identity check. This repo does not ship the paid skill. The probe refuses a value that starts with `nsec` and does not print it. |
| Create or fetch an invoice, pay, return a hash | `--phase pay` creates a 500 sat invoice, pays it, and requires status `SUCCEEDED` plus a payment hash. |

The worked example on the listing is 500 sats. The pay phase uses that amount.

A buyer pays with the function the listing names:

```python
from agent_bitcoin import pay_invoice

result = pay_invoice(payment_request)
```

`payment_request` is the BOLT11 invoice. The same amount checks and mainnet kill switches as `AgentBitcoinClient.pay_invoice` apply. An empty payment request raises `ValueError`.

## Checklist

From a checkout, on a machine with Python 3.10+:

```bash
./examples/agensi-buyer-check.sh
```

The script changes to `/tmp` before `pip install` so pip does not treat this checkout as the package. The listing install, copied on its own, is:

```bash
python3 -m venv /tmp/agensi-buyer
/tmp/agensi-buyer/bin/pip install --upgrade pip
/tmp/agensi-buyer/bin/pip install agent-bitcoin
```

The same install with uv:

```bash
uv venv /tmp/agensi-buyer
uv pip install --python /tmp/agensi-buyer/bin/python agent-bitcoin
```

Success prints the package version, then:

```text
imported agent-bitcoin <version>
--- listing call: agent_bitcoin.pay_invoice('') ---
ValueError: Payment request is required
```

The script exits 0. Nothing is paid. `AGENT_BITCOIN_ALLOW_MAINNET` is not set.

Pull requests also install this commit with `pip install .` and run `--phase install` in `.github/workflows/agensi-public-buyer.yml`. `tests/test_agensi_buyer.py` is part of the normal pytest run. The deployment script itself is not collected.

## LND probe

Manual. The operator already has the unlocked node. Regtest is the default. Do not set `AGENT_BITCOIN_ALLOW_MAINNET` for this command.

From the repo root:

```bash
/tmp/agensi-buyer/bin/python tests/deployment/agensi_public_buyer.py --phase probe
```

Success prints `lnd_reachable=yes`, `synced_to_chain`, the alias, and `identity=present` or `identity=absent`. The pubkey is not printed. A connection error is printed in full and the process exits 1. This command is not a pull-request check.

## Pay phase

Manual. The operator supplies the unlocked LND node the listing requires.

```bash
/tmp/agensi-buyer/bin/python tests/deployment/agensi_public_buyer.py --phase pay
```

Success prints `status=SUCCEEDED`, `success=True`, and `payment_hash=present`. The hash, the invoice, and the preimage are not printed. Any exception is printed in full and the process exits 1.

GitHub can start the same phase with `workflow_dispatch` and phase `pay`. A hosted runner has no LND node, so that run fails with the connection error a buyer would see. It is not a pull-request check.

## Skills

`skills/channel-status-balance/SKILL.md` reads Lightning channel status and balances from an unlocked node. It does not move funds.

```bash
uv run pytest tests/test_skill_channel_status_balance.py
```

`skills/payment-status-tracking/SKILL.md` reads Lightning payment status and recent payments from an unlocked node. It does not move funds.

```bash
uv run pytest tests/test_skill_payment_status_tracking.py
```

`skills/peer-status-connectivity/SKILL.md` reads Lightning peer connectivity from an unlocked node. It does not change peer connections or channel state.

```bash
uv run pytest tests/test_skill_peer_status_connectivity.py
```

`skills/wallet-balance-status/SKILL.md` reads on-chain and channel balances and node status from an unlocked node. It does not move funds.

```bash
uv run pytest tests/test_skill_wallet_balance_status.py
```

`skills/fee-estimation-routing/SKILL.md` reads on-chain and Lightning fee estimates from an unlocked node. It does not move funds.

```bash
uv run pytest tests/test_skill_fee_estimation_routing.py
```

`skills/pending-channel-status/SKILL.md` reads pending Lightning channels from an unlocked node. It does not change channel state.

```bash
uv run pytest tests/test_skill_pending_channel_status.py
```

`skills/invoice-list-status/SKILL.md` reads recent Lightning invoices from an unlocked node. It does not change invoice state.

```bash
uv run pytest tests/test_skill_invoice_list_status.py
```

`skills/nostr-identity-status/SKILL.md` reads a local Nostr public identity from public files. It does not generate keys.

```bash
uv run pytest tests/test_skill_nostr_identity_status.py
```

`skills/l402-endpoint-health/SKILL.md` reads an L402 `/health` path and a 402 challenge. It does not complete the challenge.

```bash
uv run pytest tests/test_skill_l402_endpoint_health.py
```
