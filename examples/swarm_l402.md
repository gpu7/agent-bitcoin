# Two-agent swarm: who pays one L402 tool

Two Nostr identities, signed file-bus messages, one winner pays `GET /paid/finance/mempool-feerate` (100 sats). Coded policy picks the payer. Optional Grok explains in one sentence each and **never** pays.

**Two modes — do not mix them:**

| Mode | Where | Lightning |
|------|--------|-----------|
| **A. Mock** | Any one host (AWS or Mac) | None (`--offline-bus`) |
| **B. Live L402** | **Both swarm processes on the Mac**; Aperture + invoice LND on **AWS** | Mac `agent-bitcoin-lnd*` pays the AWS invoice |

Live pay is **Mac → AWS**, not two processes on AWS using AWS LND (that is self-pay).

Identity is Phase A/B encrypted keys (same as `examples/nostr_phase_b_payment.py`). This demo is **two processes** sharing one disk bus, not four (no Phase C daemons). Eight-agent variant: [swarm_l402_8.md](./swarm_l402_8.md).

## 1. What you will see

Each agent prints its **npub** (never nsec), a deterministic score, then who pays.

- **Mock:** `paid=True` and fee bands **3/2/1** (fixture). No sats move.
- **Live:** `paid=True` and real `fast` / `medium` / `slow` bands — **not** 3/2/1 unless the origin really returned that.

The loser reads the signed `result` on the bus.

## How the winner is chosen

Not Grok and not Lightning. `--no-llm` only skips an optional one-sentence explanation. Coded policy picks the payer.

Each agent’s score is SHA-256 of this UTF-8 string, with **no separators**: lowercase hex pubkey + `invoice_id` + decimal `round`. `invoice_id` is the first 16 hex characters of SHA-256 of the paid URL. The score is the first **8 hex characters** of that digest, read as an integer. **Highest score pays.** If scores tie, the lexicographically larger npub pays.

Same keys, same URL (`invoice_id`), and same `--round` → the same winner. One L402 pay per successful run.

Default is **`--resolve hash`**. `./examples/swarm_l402.sh --role alice --no-llm` still uses hash.

### Puzzle (fee-sats)

`--resolve puzzle --puzzle-type fee-sats`: both agents get the same problem (`ceil(vsize * sat_vb)` integer sats). Default `vsize=141`, `sat_vb=4` → **564**. First **correct** signed `solved` on the bus pays L402. Wrong answers are ignored. The win check is coded — Grok may suggest a number when `XAI_API_KEY` is set; `--no-llm` still solves locally so the race works offline.

```bash
# mock
./examples/swarm_l402.sh --role alice --resolve puzzle --puzzle-type fee-sats --offline-bus --no-llm
./examples/swarm_l402.sh --role bob --resolve puzzle --puzzle-type fee-sats --offline-bus --no-llm

# live (Mac)
./examples/swarm_l402.sh --role alice --resolve puzzle --puzzle-type fee-sats --no-llm \
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100
./examples/swarm_l402.sh --role bob --resolve puzzle --puzzle-type fee-sats --no-llm \
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100
```

## 2. Prerequisites

- L402 stack up on AWS: `./startup-l402-aws.sh <regtest|signet|mainnet>`
- **Live:** Mac clone on the 8081 `/32`; Mac LND unlocked; channel **Mac → AWS** with **local** (outbound) ≫ 100 sats + routing
- `XAI_API_KEY` optional. Without it, `--no-llm`
- Python **3.12** + `.venv-nostr` + `.[nostr]` — [SDK.md](../SDK.md). Do **not** use `uv run python` on 3.13/3.14

## 3. Security

**Do not** world-open 8081 or 10009. Do not put nsec, NWC URIs, macaroons, or `XAI_API_KEY` in git. `.nostr-poc/` is gitignored.

Live HTTP is from the **Mac** to `http://3.90.159.146:8081`. On-box `http://127.0.0.1:8081` is for **mock** or for a client whose payer LND is **not** the Aperture invoice node (AWS LND).

## 4. Two demo modes

### A. Mock (any one host, including AWS)

```bash
./examples/swarm_l402.sh --role alice --offline-bus --no-llm
./examples/swarm_l402.sh --role bob --offline-bus --no-llm
```

No LND pay. Fine for Nostr ids + negotiate. Both processes must share the **same** `.nostr-poc/bus` on **one disk**.

### B. Live L402 (required topology)

| Piece | Where |
|-------|--------|
| Aperture + invoice LND | **AWS** |
| Payer LND | **Mac** `agent-bitcoin-lnd*` |
| Both swarm processes | **Mac** (shared `.nostr-poc/bus`) |
| URL | `http://3.90.159.146:8081/paid/finance/mempool-feerate` |
| Flags | **No** `--offline-bus`; `--price 100` |
| Do **not** | Use `LND_CONTAINER=agent-payment-decision-lnd*` as the live payer |

Splitting Alice on AWS and Bob on Mac breaks the file bus unless they rsync (**out of scope**).

## 5. Setup

Do **not** use `uv run python` for this demo on 3.13/3.14: it recreates `.venv`, skips `.[nostr]`, then `import pynostr` fails. Use `./examples/swarm_l402.sh` or `.venv-nostr/bin/python examples/swarm_l402_negotiate.py`.

If both swarm processes run on the **Mac** (live), use the **Mac** container. The AWS column is for invoicing or debugging on the instance, **not** paying the local Aperture invoice.

Before a **new live** run (or any rerun of the same `--url`), clear the bus — `invoice_id` is derived from the URL; leftover `*_result.json` reuses the old pay:

```bash
rm -f .nostr-poc/bus/*.json
```

### First time (no `.venv-nostr` yet)

```bash
cd ~/agent-bitcoin   # Mac clone for live; AWS clone is fine for mock
git pull
uv venv -p 3.12 .venv-nostr
uv pip install --python .venv-nostr/bin/python -e '.[nostr]'

export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
```

Then copy **one** network block. First run can use `--force-new-keys` once. Reuse the same dir so alice/bob keep their npubs.

### Every later run

```bash
cd ~/agent-bitcoin
# git pull   # optional
# skip uv venv if .venv-nostr exists
# uv pip install --python .venv-nostr/bin/python -e '.[nostr]'
#   only after dependency changes (pyproject extras / pull)

export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
```

Same network block as last time. Same wrapper. Do not recreate the venv.

### Regtest

**Mac payer (live swarm)**

```bash
export LND_NETWORK=regtest
export LND_CONTAINER=agent-bitcoin-lnd
export LND_TRANSPORT=docker
```

**AWS LND (invoice / debug — not live swarm payer)**

```bash
export LND_NETWORK=regtest
export LND_CONTAINER=agent-payment-decision-lnd
export LND_TRANSPORT=docker
```

No mainnet latches. Mock may use `http://127.0.0.1:8081/...` on either host.

### Signet

**Mac payer (live swarm)**

```bash
export LND_NETWORK=signet
export LND_CONTAINER=agent-bitcoin-lnd-signet
export LND_TRANSPORT=docker
```

**AWS LND (invoice / debug — not live swarm payer)**

```bash
export LND_NETWORK=signet
export LND_CONTAINER=agent-payment-decision-lnd-signet
export LND_TRANSPORT=docker
```

No mainnet latches. Confirm L402 started with `./startup-l402-aws.sh signet`.

### Mainnet

**Mac payer (live swarm)** — latches only here:

```bash
export LND_NETWORK=mainnet
export LND_CONTAINER=agent-bitcoin-lnd-mainnet
export LND_TRANSPORT=docker
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
```

**AWS LND (invoice / debug — not live swarm payer)**

```bash
export LND_NETWORK=mainnet
export LND_CONTAINER=agent-payment-decision-lnd-mainnet
export LND_TRANSPORT=docker
```

Real sats. Autoloop stays off. Only if you intend a live 100-sat pay from the **Mac**.

## 6. Live preflight (Mac)

Mainnet names shown. Regtest/signet: `agent-bitcoin-lnd` / `agent-bitcoin-lnd-signet` and `--network=regtest|signet`. No secrets.

```bash
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet getinfo
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet listchannels
# want: unlocked, synced; a channel active with local_balance >> 100

curl -sS -o /dev/null -w '%{http_code}\n' http://3.90.159.146:8081/health
# 200
curl -sS -o /dev/null -w '%{http_code}\n' \
  http://3.90.159.146:8081/paid/finance/mempool-feerate
# 402

rm -f .nostr-poc/bus/*.json
# if health times out: ./update-aws-sg-my-ip.sh   # do not world-open 8081
```

## 7. Run

Same wrapper for first time and later runs. `--relay` is accepted and ignored; happy path is `.nostr-poc/bus/`.

### Mock (any one host)

```bash
# Terminal A
./examples/swarm_l402.sh --role alice --offline-bus --no-llm

# Terminal B
./examples/swarm_l402.sh --role bob --offline-bus --no-llm
```

One process (two threads):

```bash
./examples/swarm_l402.sh --role both --offline-bus --no-llm
```

### Live (Mac, two terminals, empty bus)

Alice or Bob first is fine after `rm -f .nostr-poc/bus/*.json`. **No** `--offline-bus`.

```bash
# Terminal A
./examples/swarm_l402.sh --role alice --no-llm \
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100

# Terminal B
./examples/swarm_l402.sh --role bob --no-llm \
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100
```

Expected log lines (npubs will differ). Mock bands are **3/2/1**; live bands come from the origin:

```text
[alice] npub=npub1… invoice_id=… score=…
[bob]   npub=npub1… invoice_id=… score=…
[alice] winner_npub=npub1… i_pay=True reason=higher_score
[alice] l402 status=200 paid=True amount_sats=100 summary={'fast': …, 'medium': …, 'slow': …}
[bob]   result payer_npub=npub1… paid=True summary={'fast': …, 'medium': …, 'slow': …}
```

With `XAI_API_KEY` and without `--no-llm`, each agent may print `[alice] grok: …` / `[bob] grok: …`.

## 8. How to check the Lightning pay

- Client: `status=200` and `paid=True` on the winner line
- Origin JSON: integers `fast` / `medium` / `slow` only in the summary
- **Mock:** skip `listpayments` (no sats)
- **Live:** on the **Mac** node (redacted):

```bash
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet listpayments --max_payments 3
# ~100 sat SUCCEEDED. Do not paste preimages.
```

## 9. How IDs show up

Printed: `npub=npub1…`. Encrypted nsec stays in `.nostr-poc/alice.enc.json` and `bob.enc.json` (mode 0600). Never print or commit nsec.

## 10. Troubleshooting

| Symptom | What to do |
|---------|------------|
| 402 loop / `paid=False` | Price mismatch: pass `--price 100` for feerate. Client default elsewhere is 1000. |
| Connection refused / health timeout :8081 | Not on the `/32`. `./update-aws-sg-my-ip.sh`. **Do not open SG.** L402: `./startup-l402-aws.sh <network>` |
| LND locked / macaroon errors | Unlock the **Mac payer** wallet; `LND_CONTAINER` is `agent-bitcoin-lnd*` |
| Amount below floor | Min invoice is **100 sats** (`MIN_PAYMENT_SATS`) |
| `No such container: agent-bitcoin-lnd-mainnet` on AWS | Wrong host. Live payer is the **Mac** |
| `self-payments not allowed` | Payer == invoice node. Use Mac `agent-bitcoin-lnd*` + `--url http://3.90.159.146:8081/…`. Do not enable LND self-pay |
| Alice exits instantly with bands 3/2/1 | Stale bus and/or `--offline-bus`. `rm -f .nostr-poc/bus/*.json` |
| Timeout waiting for peer | Same `--dir`, same `--url`, both processes on **one** Mac; bus is `$NOSTR_POC_DIR/bus/` |
| Missing pynostr / uv 3.14 | Do not use `uv run python`. `uv venv -p 3.12 .venv-nostr` then `uv pip install --python .venv-nostr/bin/python -e '.[nostr]'`. Run `./examples/swarm_l402.sh` |

Sequence of a paid GET: [docs/architecture.md — L402 request sequence](../docs/architecture.md#l402-request-sequence). Operator gateway: [docs/l402-aperture.md](../docs/l402-aperture.md).
