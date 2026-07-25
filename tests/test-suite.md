# Agent-Bitcoin Test Suite

Automated tests live under `tests/` and run with **pytest**.

```bash
# Offline unit tests (default)
uv run pytest tests/ -q --ignore=tests/test_aws_integration.py

# Policy + amount + fee unit tests only
uv run pytest tests/test_payment_amounts.py tests/test_payment_decision_policy.py tests/test_fee_collection.py -q

# Live regtest integration (AWS + Mac stack, API key required)
export AGENT_BITCOIN_API_KEY=...
uv run python tests/test_aws_integration.py --backend-url http://<AWS_EIP>:8000
```

## Case IDs

| ID | Case | Unit coverage | Integration |
|----|------|---------------|-------------|
| **ABT-001** | Normal payment (min &lt; amt ≤ max) | Client + API + agent allow mid-range | `test_aws_integration.py` nominal pay |
| **ABT-002** | Below minimum | Client/API/agent reject | — |
| **ABT-003** | Above maximum (1,000,000 sats) | Client/API/agent reject | — |
| **ABT-004** | Fee deposit amount | Client `collect_transaction_fee` + API `/send-fee` mock | Live `/send-fee` in integration test |

## Shared limits

Defined in `agent_bitcoin/constants.py`:

| Constant | Default (sats) |
|----------|----------------|
| `DEFAULT_MIN_PAYMENT_SATS` | 2,000 |
| `DEFAULT_MAX_PAYMENT_SATS` | **1,000,000** |
| `DEFAULT_FEE_AMOUNT_SATS` | 1,000 |

Invoice max and agent max both default to `DEFAULT_MAX_PAYMENT_SATS`.

## Markers

- `@pytest.mark.integration` — reserved for live Docker/LND tests (skip offline)

## Files

| File | Role |
|------|------|
| `test_payment_amounts.py` | ABT-001–003 client + API |
| `test_payment_decision_policy.py` | ABT agent policy |
| `test_fee_collection.py` | ABT-004 fee unit |
| `test_client.py` | Factory / basic client |
| `test_aws_integration.py` | Live regtest script |
| `conftest.py` | Shared fixtures |
