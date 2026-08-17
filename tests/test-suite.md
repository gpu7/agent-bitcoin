# Agent-Bitcoin Test Suite

Automated tests live under `tests/` and run with **pytest**.

```bash
# Offline unit tests (default CI / no Docker)
uv run pytest tests/ -q --ignore=tests/test_aws_integration.py \
  --ignore=tests/test_lnd_sdk_integration.py

# Policy + amount + fee unit tests only
uv run pytest tests/test_payment_amounts.py tests/test_payment_decision_policy.py \
  tests/test_fee_collection.py -q

# Live LND SDK integration — regtest or signet (Docker LND on this host)
LND_NETWORK=signet uv run pytest tests/test_lnd_sdk_integration.py -m integration -v
LND_NETWORK=regtest uv run pytest tests/test_lnd_sdk_integration.py -m integration -v

# Live HTTP backend script (optional; needs API key + running backend)
export AGENT_BITCOIN_API_KEY=...
uv run python tests/test_aws_integration.py --network signet \
  --backend-url http://127.0.0.1:8000
uv run python tests/test_aws_integration.py --network regtest \
  --backend-url http://<AWS_EIP>:8000
```

## Networks

| `LND_NETWORK` | Agent container | Peer container | Dual-node roles (SDK product path) |
|---------------|-----------------|----------------|-------------------------------------|
| `regtest` | `agent-payment-decision-lnd` | `agent-bitcoin-lnd` | receiver=agent, payer=peer (Mac pays AWS) |
| `signet` | `agent-payment-decision-lnd-signet` | `agent-bitcoin-lnd-signet` | receiver=peer (Mac), payer=agent (AWS) |

Dual-node **pay** tests require **both** containers on the same Docker host. Typical lab split (Mac peer + AWS agent) runs single-node SDK tests on each host; dual pay runs only when both are local (or pay manually on the payer host).

## Case IDs

| ID | Case | Unit coverage | Integration |
|----|------|---------------|-------------|
| **ABT-001** | Normal payment (min &lt; amt ≤ max) | Client + API + agent allow mid-range | SDK create/pay when dual local |
| **ABT-002** | Below minimum | Client/API/agent reject | — |
| **ABT-003** | Above maximum (1,000,000 sats) | Client/API/agent reject | — |
| **ABT-004** | No platform fee | Invoice quote `total_cost_sats = amount_sats`; BOLT11 == requested | — |
| **ABT-L402-001** | L402 402 challenge parse | `parse_www_authenticate` + origin `/health` | curl `/paid/hello` → 402 |
| **ABT-L402-002** | L402 pay + retry | Mock 402 → pay → 200 | Mac `l402_pay.py` → origin JSON |
| **ABT-L402-003** | L402 PDF body | Origin `/paid/report.pdf` is `%PDF` | Mac `l402_pay.py --out report.pdf` |
| **ABT-L402-004** | L402 PNG body | Origin `/paid/badge.png` is a PNG | Mac `l402_pay.py --out badge.png` |

## Shared limits

Defined in `agent_bitcoin/constants.py`:

| Constant | Default (sats) |
|----------|----------------|
| `DEFAULT_MIN_PAYMENT_SATS` | 1,000 |
| `DEFAULT_MAX_PAYMENT_SATS` | **1,000,000** |

## Markers

- `@pytest.mark.integration` — live Docker/LND (not offline CI)

## Files

| File | Role |
|------|------|
| `test_payment_amounts.py` | ABT-001–003 client + API |
| `test_payment_decision_policy.py` | ABT agent policy |
| `test_fee_collection.py` | ABT-004 no platform fee |
| `test_l402.py` | ABT-L402-001 / 002 header + mock pay |
| `test_client.py` | Factory / basic client |
| `test_lnd_sdk_integration.py` | Live SDK regtest/signet |
| `test_aws_integration.py` | Live HTTP backend script (network-aware) |
| `network_config.py` | Container names / dual roles |
| `conftest.py` | Shared fixtures |
