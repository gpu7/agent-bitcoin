# Two-agent swarm: who pays one L402 tool

Engineer demo on the **existing** AWS box (or any host already allowed to `:8081`). Two Nostr identities, signed file-bus messages, one winner pays `GET /paid/finance/mempool-feerate` (100 sats). Coded policy picks the payer. Optional Grok explains in one sentence each and **never** pays.

Identity is Phase A/B encrypted keys (same as `examples/nostr_phase_b_payment.py`). Not a second stack. Phase C signer daemons are optional later; this demo is **two processes**, not four.

## 1. What you will see

Each agent prints its **npub** (never nsec), a deterministic score, then who pays. The winner runs the L402 handshake (402 → pay → retry) or a mock if `--offline-bus`. Both log `paid=True`, `amount_sats=100`, and fee bands `{fast, medium, slow}` only. The loser reads that from a signed `result` event on the bus.

## 2. Prerequisites

- Existing **AWS** `agent-bitcoin` checkout (or Mac already on the 8081 `/32`)
- L402 stack up: `./startup-l402-aws.sh <regtest|signet|mainnet>`
- Unlocked LND on the **payer** host
- Channel **local** liquidity ≥ price + routing (100 sats + fee cap)
- `XAI_API_KEY` optional (Grok one-liners). Without it, use `--no-llm`
- Python **3.12** + nostr extra — [SDK.md](../SDK.md) (`uv venv -p 3.12 .venv-nostr` / `uv pip install -e '.[nostr]'`). Do **not** use `uv run python` on 3.13/3.14.

## 3. Security

Run on the instance (`http://127.0.0.1:8081`) **or** any host already allowed to TCP **8081**. **Do not** world-open 8081 or 10009. Do not put nsec, NWC URIs, macaroons, or `XAI_API_KEY` in git. `.nostr-poc/` is gitignored.

Aperture invoices are created on **AWS LND**. `examples/l402_pay.py` pays them from the **Mac** node. Two processes on AWS talking to `127.0.0.1:8081` may hit **self-pay / no route** on that same LND. If live pay fails that way, run the two terminals on the Mac (already `/32`) with `--url http://<EIP>:8081/paid/finance/mempool-feerate`. Do not open the SG.

## 4. Setup

Do **not** use `uv run python` for this demo on 3.13/3.14: it recreates `.venv`, skips `.[nostr]`, then `import pynostr` fails. Use `./examples/swarm_l402.sh` or `.venv-nostr/bin/python examples/swarm_l402_negotiate.py`.

Typical live payer is **Mac LND** (outbound to the AWS Aperture invoice). Copy **one** network block below. On-box agents on AWS may use `http://127.0.0.1:8081/...` for HTTP; paying that invoice with AWS LND can self-pay (see §3).

### First time (no `.venv-nostr` yet)

```bash
cd ~/agent-bitcoin   # or the Mac clone
git pull
uv venv -p 3.12 .venv-nostr
uv pip install --python .venv-nostr/bin/python -e '.[nostr]'

export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
```

Then copy **one** of Regtest / Signet / Mainnet. First run can use `--force-new-keys` once. Reuse the same dir so alice/bob keep their npubs.

Start agents with `./examples/swarm_l402.sh` (see §5) or `.venv-nostr/bin/python examples/swarm_l402_negotiate.py`.

### Every later run

```bash
cd ~/agent-bitcoin   # or the Mac clone
# git pull   # optional
# skip uv venv if .venv-nostr exists
# uv pip install --python .venv-nostr/bin/python -e '.[nostr]'
#   only after dependency changes (pyproject extras / pull)

export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
```

Same network block as last time. Same wrapper / `.venv-nostr` python (§5). Do not recreate the venv.

### Regtest

```bash
export LND_NETWORK=regtest
export LND_CONTAINER=agent-bitcoin-lnd
export LND_TRANSPORT=docker
```

No mainnet latches. On-box L402 URL `http://127.0.0.1:8081/...` if agents run on AWS.

### Signet

```bash
export LND_NETWORK=signet
export LND_CONTAINER=agent-bitcoin-lnd-signet
export LND_TRANSPORT=docker
```

No mainnet latches. Confirm L402 started with `./startup-l402-aws.sh signet`.

### Mainnet

```bash
export LND_NETWORK=mainnet
export LND_CONTAINER=agent-bitcoin-lnd-mainnet
export LND_TRANSPORT=docker
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
```

Real sats. Autoloop stays off. Only if you intend a live 100-sat pay.

## 5. Run

Same commands for first time and later runs.

Engineer path — **two terminals**, shared bus directory:

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

Live L402 (after offline works). Typical: Mac, URL is the AWS EIP, price 100:

```bash
./examples/swarm_l402.sh --role alice \
  --url http://<AWS_EIP>:8081/paid/finance/mempool-feerate --price 100 --no-llm
# other terminal: --role bob, same --url --price
```

`--relay` is accepted and ignored; public relays often filter new keys. Happy path is `.nostr-poc/bus/`.

Expected log lines (npubs will differ):

```text
[alice] npub=npub1… invoice_id=… score=…
[bob]   npub=npub1… invoice_id=… score=…
[alice] winner_npub=npub1… i_pay=True reason=lower_score
[alice] l402 status=200 paid=True amount_sats=100 summary={'fast': 3, 'medium': 2, 'slow': 1}
[bob]   result payer_npub=npub1… paid=True summary={'fast': 3, 'medium': 2, 'slow': 1}
```

With `XAI_API_KEY` and without `--no-llm`, each agent may print `[alice] grok: …` / `[bob] grok: …`.

## 6. How to check the Lightning pay

- Client: `status=200` and `paid=True` on the winner line
- Origin JSON: integers `fast` / `medium` / `slow` only in the summary (not the full envelope)
- LND (payer container; redacted):

```bash
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd \
  --network="$LND_NETWORK" listpayments --max_payments 3
# Look at value_sat ≈ 100 and a payment_hash (hex). Do not paste preimages.
```

`--offline-bus` does **not** move sats; skip `listpayments`.

## 7. How IDs show up

Printed: `npub=npub1…`. Encrypted nsec stays in `.nostr-poc/alice.enc.json` and `bob.enc.json` (mode 0600). Never print or commit nsec.

## 8. Troubleshooting

| Symptom | What to do |
|---------|------------|
| 402 loop / `paid=False` | Price mismatch: pass `--price 100` for feerate. Client default elsewhere is 1000. |
| Connection refused :8081 | L402 not up, or you are not on the instance / not on the `/32`. **Do not open SG.** `./startup-l402-aws.sh <network>` |
| LND locked / macaroon errors | Unlock the **payer** wallet; `LND_CONTAINER` / `LND_NETWORK` match compose |
| Amount below floor | Min invoice is **100 sats** (`MIN_PAYMENT_SATS`) |
| `self payment` / `no route` | Paying AWS Aperture with AWS LND. Run the two agents on the Mac with `--url http://<EIP>:8081/…` |
| Timeout waiting for peer | Same `--dir`, same `--url`, both processes running; bus is `$NOSTR_POC_DIR/bus/` |
| Missing pynostr | Do not use `uv run python`. `uv venv -p 3.12 .venv-nostr` then `uv pip install --python .venv-nostr/bin/python -e '.[nostr]'`. Run `./examples/swarm_l402.sh` |

Sequence of a paid GET: [docs/architecture.md — L402 request sequence](../docs/architecture.md#l402-request-sequence). Operator gateway: [docs/l402-aperture.md](../docs/l402-aperture.md).
