# Aperture L402 paid gateway

**Status:** Regtest Mac→AWS paid GET **PASS** (2026-08-15). Signet overlay is in this PR (live paid GET is the merge gate). Mainnet is a later PR.
**Not** Lightning Loop’s container named `aperture` (`aperture:11018`). That is Loop L402 auth. This gateway is **`agent-l402-aperture`** on **`:8081`**.

## What it is

Aperture sits in front of a dummy HTTP origin on AWS. A client that has not paid gets **HTTP 402** plus a macaroon and a 1,000 sat BOLT11. After the Mac LND node pays, the client retries with `Authorization: L402 <macaroon>:<preimage>` and Aperture proxies to the origin.

```text
Mac  examples/l402_pay.py
        │  HTTP :8081  (SG: Mac IP /32 only)
        ▼
AWS  agent-l402-aperture :8081
        ├─ LND gRPC  <aws-lnd>:10009  (invoice.macaroon)
        └─ origin    agent-l402-origin:8090
              GET /health      free
              GET /paid/hello  1,000 sats
```

There is **no platform fee**. The L402 price **is** the Lightning amount (1,000 sats = `MIN_PAYMENT_SATS`).

Do **not** put Aperture in front of `/pay`, `/invoices`, or `/balance`.

## Prerequisites

- AWS + Mac LND up and **unlocked** on the same network
- Channel Mac → AWS with **≥ 1,000 local sats** on the Mac
- Only **one** L402 stack at a time (`:8081`)

| Network | AWS LND | Mac LND | Docker network | LND volume |
|---------|---------|---------|----------------|------------|
| regtest | `agent-payment-decision-lnd` | `agent-bitcoin-lnd` | `regtest_regtest` | `agent-bitcoin_lnd-data` |
| signet | `agent-payment-decision-lnd-signet` | `agent-bitcoin-lnd-signet` | `agent-bitcoin-signet` | `agent-bitcoin_lnd-signet-data` |

## Start on AWS

```bash
cd ~/agent-bitcoin
git pull
# Stop the other network's L402 first if :8081 is in use
./shutdown-l402-aws.sh regtest   # if switching to signet
./startup-l402-aws.sh signet     # or: ./startup-l402-aws.sh regtest

curl -sS http://127.0.0.1:8081/health          # 200, no payment
curl -sSi http://127.0.0.1:8081/paid/hello     # 402 + WWW-Authenticate
```

Stop (preserves Aperture sqlite + LND volumes):

```bash
./shutdown-l402-aws.sh signet    # or regtest
```

This does **not** change `startup-aws.sh` / Loop / `startup-signet-aws.sh`.

## Security group

`update-aws-sg-my-ip.sh` includes **8081** (operator `/32` only). From the Mac:

```bash
./update-aws-sg-my-ip.sh
```

Do **not** open LND gRPC `10009`. Do **not** world-open 8081.

## Pay from the Mac

```bash
# Regtest
export LND_NETWORK=regtest LND_CONTAINER=agent-bitcoin-lnd
# Signet
# export LND_NETWORK=signet LND_CONTAINER=agent-bitcoin-lnd-signet

uv run python examples/l402_pay.py --url http://<AWS_EIP>:8081/paid/hello
```

Expect `status=200 paid=True` and JSON `{"ok": true, "service": "l402-demo", "network": "<regtest|signet>", "msg": "hello"}`.

## SDK

```python
from agent_bitcoin import L402Client, create_client

client = L402Client(create_client(), expected_price_sats=1000)
resp = client.fetch("http://<AWS_EIP>:8081/paid/hello")
```

`PaymentResult.preimage` is filled from `lncli sendpayment` / gRPC so the L402 retry can succeed.

## Files

| Path | Role |
|------|------|
| `docker-compose.l402.regtest.yml` | Origin + Aperture on `regtest_regtest` |
| `docker-compose.l402.signet.yml` | Origin + Aperture on `agent-bitcoin-signet` |
| `l402/aperture.regtest.yaml` / `aperture.signet.yaml` | `price: 1000`, `insecure: true` |
| `l402/origin.py` | Dummy origin |
| `agent_bitcoin/l402/` | Client + header parser |
| `examples/l402_pay.py` | Mac CLI |
| `startup-l402-aws.sh` / `shutdown-l402-aws.sh` | Ops |

## Later networks

Mainnet gets its own compose overlay and PR. Same `:8081` + SG `/32`. Mainnet pay still needs a written go. Invoice-only macaroon is required on mainnet (Aperture already requests `invoice.macaroon` from `macdir`).
