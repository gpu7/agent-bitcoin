# Aperture L402 paid gateway

**Status:** Regtest, signet, and mainnet Mac→AWS paid GET **PASS** (2026-08-15). One mainnet pay was 1,000 sats.
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
              GET /health           free
              GET /paid/hello       1,000 sats (JSON)
              GET /paid/report.pdf  1,000 sats (PDF file)
              GET /paid/script.pdf  1,000 sats (PDF from generate_script_pdf.py)
              GET /paid/badge.png   1,000 sats (PNG image)
              GET /paid/finance/mempool-feerate  100 sats (JSON fee bands)
              GET /paid/finance/mempool-backlog  100 sats (JSON mempool fullness)
              GET /paid/finance/fee-for-vsize?vsize=  100 sats (JSON total fee sats)
              GET /paid/finance/confirm-target?       100 sats (JSON wait → sat/vB)
              GET /paid/finance/btc-usd               100 sats (JSON BTC/USD pass-through)
```

There is **no platform fee**. The L402 price **is** the Lightning amount (must be ≥ `MIN_PAYMENT_SATS`, default 100). Demo files are **1,000 sats**; finance paths (feerate, backlog, fee-for-vsize, confirm-target, btc-usd) are **100 sats**.

This is **not** a mempool.space replacement, FX oracle, or CoinGecko substitute. **mempool-feerate** is fee bands (sat/vB). **mempool-backlog** is fullness. **fee-for-vsize** multiplies those bands by a **vbyte** size. **confirm-target** maps a wait window (minutes) or named band onto `sat_vb` from the feerate cache. **btc-usd** is a **pass-through mark, not our index** — USD per 1 BTC from one public JSON URL. Useful before an **on-chain** send or a USD↔sats sanity check; not needed for Lightning-only invoice pays.

Do **not** put Aperture in front of `/pay`, `/invoices`, or `/balance`.

## Prerequisites

- AWS + Mac LND up and **unlocked** on the same network
- Channel Mac → AWS with **≥ 1,000 local sats** on the Mac
- Only **one** L402 stack at a time (`:8081`)

| Network | AWS LND | Mac LND | Docker network | LND volume |
|---------|---------|---------|----------------|------------|
| regtest | `agent-payment-decision-lnd` | `agent-bitcoin-lnd` | `regtest_regtest` | `agent-bitcoin_lnd-data` |
| signet | `agent-payment-decision-lnd-signet` | `agent-bitcoin-lnd-signet` | `agent-bitcoin-signet` | `agent-bitcoin_lnd-signet-data` |
| mainnet | `agent-payment-decision-lnd-mainnet` | `agent-bitcoin-lnd-mainnet` | `agent-bitcoin-mainnet` | `agent-bitcoin_lnd-mainnet-data` |

## Start on AWS

```bash
cd ~/agent-bitcoin
git pull
# Stop the other network's L402 first if :8081 is in use
./shutdown-l402-aws.sh regtest   # if switching to signet
./startup-l402-aws.sh signet     # or: regtest | mainnet

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
# Mainnet (also AGENT_BITCOIN_ALLOW_MAINNET=1 AGENT_BITCOIN_ALLOW_AUTOPAY=1)

uv run python examples/l402_pay.py --url http://<AWS_EIP>:8081/paid/hello
```

Expect `status=200 paid=True` and JSON `{"ok": true, "service": "l402-demo", "network": "<regtest|signet|mainnet>", "msg": "hello"}`.

Paid PDF (same price; origin writes a one-page Helvetica demo):

```bash
uv run python examples/l402_pay.py --url http://<AWS_EIP>:8081/paid/report.pdf --out report.pdf
# open report.pdf — text: "agent-bitcoin L402 demo report"

uv run python examples/l402_pay.py --url http://<AWS_EIP>:8081/paid/badge.png --out badge.png
# open badge.png — gold "L402 PAID" on a dark badge

uv run python examples/l402_pay.py --url http://<AWS_EIP>:8081/paid/script.pdf --out script.pdf
# open script.pdf — text from l402/generate_script_pdf.py

# On-chain fee bands (100 sats). L402Client default expected price is 1000 — pass --price 100.
uv run python examples/l402_pay.py \
  --url http://<AWS_EIP>:8081/paid/finance/mempool-feerate --price 100

# Mempool fullness (100 sats) — tx count / vbytes, not fee bands
uv run python examples/l402_pay.py \
  --url http://<AWS_EIP>:8081/paid/finance/mempool-backlog --price 100

# Total fee for a tx size in **vbytes** (not weight). Range 110–100000.
uv run python examples/l402_pay.py \
  --url 'http://<AWS_EIP>:8081/paid/finance/fee-for-vsize?vsize=250' --price 100

# Wait window → sat/vB (Helix: 1–20 fast, 21–45 medium, 46–60 slow)
uv run python examples/l402_pay.py \
  --url 'http://<AWS_EIP>:8081/paid/finance/confirm-target?minutes=30' --price 100
uv run python examples/l402_pay.py \
  --url 'http://<AWS_EIP>:8081/paid/finance/confirm-target?target=fast&vsize=250' --price 100

# BTC/USD pass-through (100 sats). Not an FX index — one public JSON URL.
uv run python examples/l402_pay.py \
  --url http://<AWS_EIP>:8081/paid/finance/btc-usd --price 100
```

`GET /paid/finance/mempool-feerate` JSON (after pay): `ok`, `service` (`mempool-feerate`), `version` (`v1`), `as_of`, `ttl_s`, `unit` (`sat_per_vbyte`), `fast` / `medium` / `slow` (integers ≥ 1), `source`, `source_as_of`, `stale`.

Upstream default: `https://mempool.space/api/v1/fees/recommended`. Mapping: `fastestFee` → `fast`, `halfHourFee` → `medium`, `hourFee` → `slow`. Override URL with `MEMPOOL_FEERATE_URL`; cache TTL with `MEMPOOL_FEERATE_TTL_S` (default 30, clamp 15–60). If the fetch fails and a cache exists, the origin returns it with `stale: true`. No cache → HTTP 503 `{ "ok": false, "error": "upstream_unavailable" }`.

`GET /paid/finance/mempool-backlog` JSON (after pay): `ok`, `service` (`mempool-backlog`), `version` (`v1`), `as_of`, `ttl_s`, `tx_count`, `vsize` (virtual bytes), `total_fee_sats` (from upstream `total_fee`, same payload), `vsize_per_block_equiv` (`vsize / 1e6`; ~one full block), `source`, `source_as_of`, `stale`. **No** `fast` / `medium` / `slow`.

Upstream default: `https://mempool.space/api/mempool` (`count`, `vsize`, `total_fee`). Override `MEMPOOL_BACKLOG_URL`; TTL `MEMPOOL_BACKLOG_TTL_S` (same clamp). Same 503 / `stale` rules as feerate. After `./startup-l402-aws.sh`, **`docker restart agent-l402-aperture`** so YAML prices load.

`GET /paid/finance/fee-for-vsize?vsize=<int>` JSON (after pay): envelope from the **feerate cache** (`as_of`, `ttl_s`, `source`, `source_as_of`, `stale`) plus `vsize` and `fee_sats_fast` / `fee_sats_medium` / `fee_sats_slow` (`ceil(vsize * sat_vb)`). Query `vsize` is **virtual bytes**, not weight; range **110–100000**. Missing/non-integer/out of range or a `weight` param → origin **400** `{ "ok": false, "error": "bad_vsize" }`. No second upstream; uses feerate rates (including stale). Empty feerate cache → **503**.

`GET /paid/finance/confirm-target` JSON (after pay): envelope from the **feerate cache** plus `target`, `sat_vb`. Echo `minutes` only if the client sent it. Optional `vsize` (110–100000 vbytes) adds `vsize` and `fee_sats = ceil(vsize * sat_vb)`. At least one of `minutes` (1–60) or `target` (`fast`|`medium`|`slow`). If both, snapped minutes must match `target` or **400** `bad_confirm_target`. `weight=` or bad `vsize` → **400** `bad_vsize`. Snap: 1–20 fast, 21–45 medium, 46–60 slow (no 61–180). No second upstream.

`GET /paid/finance/btc-usd` JSON (after pay): `ok`, `service` (`btc-usd`), `version` (`v1`), `as_of`, `ttl_s`, `source` (`public_price_api` — this is **not** mempool fee data), `source_as_of`, `stale`, `btc_usd` (JSON number, USD per 1 BTC), `sats_per_usd` (integer, `floor(100_000_000 / btc_usd)`). No query params. Constant `btc_sats` is omitted. Raw vendor JSON is not attached.

```json
{
  "ok": true,
  "service": "btc-usd",
  "version": "v1",
  "as_of": "2026-09-07T17:50:00Z",
  "ttl_s": 30,
  "source": "public_price_api",
  "source_as_of": "2026-09-07T17:49:50Z",
  "stale": false,
  "btc_usd": 97450.12,
  "sats_per_usd": 1026
}
```

Upstream default: `https://mempool.space/api/v1/prices`. Accepted schema: JSON object with **`USD`** a positive number (int or float). Optional unix **`time`** becomes `source_as_of`. Other fields (EUR, …) are ignored. Override URL with `BTC_USD_URL`; cache TTL with `BTC_USD_TTL_S` (default **30**, clamp **30–60**). Separate in-memory cache from feerate/backlog. Lazy refresh on GET; one in-flight fetch. Fail + cache → `stale: true`. Fail / missing / `USD` ≤ 0 + no cache → HTTP **503** `{ "ok": false, "error": "upstream_unavailable" }`. Pass-through mark, not our index.

Rebuild origin + Aperture after pull: `./startup-l402-aws.sh mainnet` (do **not** `--remove-orphans`). Do **not** world-open 8081. Mainnet payer still needs `AGENT_BITCOIN_ALLOW_MAINNET=1` and `AGENT_BITCOIN_ALLOW_AUTOPAY=1`. Autoloop stays off. Payer needs enough local channel sats for a **100 sat** invoice plus routing.

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
| `docker-compose.l402.mainnet.yml` | Origin + Aperture on `agent-bitcoin-mainnet` |
| `l402/aperture.*.yaml` | `price: 1000`, `insecure: true` |
| `l402/origin.py` | Dummy origin |
| `agent_bitcoin/l402/` | Client + header parser |
| `examples/l402_pay.py` | Mac CLI |
| `startup-l402-aws.sh` / `shutdown-l402-aws.sh` | Ops |

## Mainnet notes

- Same `:8081` + SG `/32`. Do **not** world-open 8081.
- Aperture uses **`invoice.macaroon`** from the mainnet macaroon dir (not admin).
- One paid GET is **1,000 real sats**. Needs `AGENT_BITCOIN_ALLOW_MAINNET=1` and `AGENT_BITCOIN_ALLOW_AUTOPAY=1` on the Mac payer. Autoloop stays **off**.
