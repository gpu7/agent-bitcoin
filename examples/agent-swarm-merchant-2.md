# 2-agent merchant swarm

Two-agent swarm: who pays one L402 tool.

Two Nostr identities, signed relay events, one winner pays `GET /paid/finance/mempool-feerate` (100 sats). Coded policy picks the payer. Optional Grok explains in one sentence each and **never** pays.

**Two modes — do not mix them:**

| Mode | Where | Lightning |
|------|--------|-----------|
| **A. Mock** | Any one host (AWS or Mac) | None (`--offline-bus`) |
| **B. Live L402** | **Both swarm processes on the Mac**; Aperture + invoice LND on **AWS** | Mac `agent-bitcoin-lnd*` pays the AWS invoice |

Live pay is **Mac → AWS**, not two processes on AWS using AWS LND (that is self-pay).

Identity is Phase A/B encrypted keys (same as `examples/nostr_phase_b_payment.py`). This demo is **two processes** that share a key directory, not a message bus and not four Phase C daemons. Eight-agent variant: [agent-swarm-merchant-8.md](./agent-swarm-merchant-8.md). Swarm picks who pays the **merchant**; A2A LN (two LND nodes) is [a2a_ln_pay.md](./a2a_ln_pay.md).

## 1. What you will see

Each agent prints its **npub** (never nsec), a deterministic score, then who pays.

- **Mock:** `paid=True` and fee bands **3/2/1** (fixture). No sats move.
- **Live:** `paid=True` and real `fast` / `medium` / `slow` bands — **not** 3/2/1 unless the origin really returned that.

The loser reads the signed `result` on the relay.

## How the winner is chosen

Not Grok and not Lightning. `--no-llm` only skips an optional one-sentence explanation. Coded policy picks the payer.

Each agent’s score is SHA-256 of this UTF-8 string, with **no separators**: lowercase hex pubkey + `invoice_id` + decimal `round`. `invoice_id` is the first 16 hex characters of SHA-256 of the paid URL. The score is the first **8 hex characters** of that digest, read as an integer. **Highest score pays.** If scores tie, the lexicographically larger npub pays.

Same keys, same URL (`invoice_id`), and same `--round` → the same winner. One L402 pay per successful run.

Default is **`--resolve hash`**. `./examples/agent-to-merchant-pay.sh --role alice --no-llm` still uses hash (no `XAI_API_KEY` required).

### Puzzle (fee-sats)

`--resolve puzzle --puzzle-type fee-sats`: both agents get the same problem (`ceil(vsize * sat_vb)` integer sats). Default `vsize=141`, `sat_vb=4` → **564**. First **correct** signed `solved` on the relay pays L402. Wrong answers are ignored. The win check is coded — Grok may suggest a number when `XAI_API_KEY` is set; `--no-llm` still solves locally so the race works offline.

```bash
# mock
./examples/agent-to-merchant-pay.sh --role alice --resolve puzzle --puzzle-type fee-sats --offline-bus --no-llm
./examples/agent-to-merchant-pay.sh --role bob --resolve puzzle --puzzle-type fee-sats --offline-bus --no-llm

# live (Mac)
./examples/agent-to-merchant-pay.sh --role alice --resolve puzzle --puzzle-type fee-sats --no-llm \
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100
./examples/agent-to-merchant-pay.sh --role bob --resolve puzzle --puzzle-type fee-sats --no-llm \
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100
```

### LLM gate (opt-in)

`--resolve llm-gate`: each agent votes YES/NO whether to pay **100 sats** for `POST /paid/finance/ln-path-fee-hint`. YES voters then use the **hash** tie-break. 0 YES → no L402. `--model grok` (default) uses `XAI_API_KEY`. `--model ollama` uses local Ollama (`http://127.0.0.1:11434`, `OLLAMA_MODEL` or `llama3.2`) and does not need xAI. `--no-llm` cannot be combined with `--model` or llm-gate. Two-agent only. Vote `reason` is logged locally, not sent to AWS. Hash / puzzle still need no model (`--no-llm`).

```bash
export XAI_API_KEY=       # local only; never commit
export NOSTR_PASSPHRASE=  # local only; never commit; create any passphrase you like
```

Alice in **one Mac terminal**, Bob in **another**. Same exports in both. Start Alice, then Bob. The script POSTs path-hint (no `--method POST` flag).

Mock Grok (no Lightning):

```bash
# Terminal A
./examples/agent-to-merchant-pay.sh --role alice --resolve llm-gate --model grok --offline-bus
# Terminal B
./examples/agent-to-merchant-pay.sh --role bob --resolve llm-gate --model grok --offline-bus
```

Mock Ollama (local HTTP; `ollama pull llama3.2`; no `XAI_API_KEY`):

```bash
# Terminal A
./examples/agent-to-merchant-pay.sh --role alice --resolve llm-gate --model ollama --offline-bus
# Terminal B
./examples/agent-to-merchant-pay.sh --role bob --resolve llm-gate --model ollama --offline-bus
```

Live (Mac pays AWS, 100 sats):

```bash
export LND_NETWORK=mainnet
export LND_CONTAINER=agent-bitcoin-lnd-mainnet
export LND_TRANSPORT=docker
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
# Terminal A
./examples/agent-to-merchant-pay.sh --role alice --resolve llm-gate --price 100 \
  --url http://3.90.159.146:8081/paid/finance/ln-path-fee-hint
# Terminal B
./examples/agent-to-merchant-pay.sh --role bob --resolve llm-gate --price 100 \
  --url http://3.90.159.146:8081/paid/finance/ln-path-fee-hint
```

Forced YES (test only — skip Grok; do not default). Same alice/bob commands as mock (`--offline-bus`) or live (URL + LND exports):

```bash
export SWARM_LLM_FORCE_VOTE=YES
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
./examples/agent-to-merchant-pay.sh --role alice --offline-bus --no-llm
./examples/agent-to-merchant-pay.sh --role bob --offline-bus --no-llm
```

No LND pay. Fine for Nostr ids + negotiate. `--offline-bus` uses a **localhost mock relay** on `127.0.0.1:8765` (`MERCHANT_MOCK_PORT` to move it). Not shared files. Not Damus or nos.lol. Live uses `NOSTR_RELAYS` (default `wss://relay.damus.io,wss://nos.lol`). Every accepted event is kind **8139** (regular, not kind 1, not replaceable). The process checks **id, signature, and pubkey** and rejects a signer that is not the pubkey stored for that role. Coordination JSON is npub, score, and invoice id only — not a NIP-17 gift wrap, and never a BOLT11 or preimage. The L402 GET/POST to Aperture stays unsigned HTTP plus the invoice. No npub on that hop.

### B. Live L402 (required topology)

| Piece | Where |
|-------|--------|
| Aperture + invoice LND | **AWS** |
| Payer LND | **Mac** `agent-bitcoin-lnd*` |
| Both swarm processes | **Mac** (Nostr relays; no shared message directory) |
| URL | `http://3.90.159.146:8081/paid/finance/mempool-feerate` |
| Flags | **No** `--offline-bus`; `--price 100` |
| Do **not** | Use `LND_CONTAINER=agent-payment-decision-lnd*` as the live payer |

Alice and Bob do not share a message directory. Live coordination is signed events on `NOSTR_RELAYS`. Start Alice and wait until she prints `waiting for`, then start Bob within `--timeout` (default 60 seconds). Verify before trust. Same order for the mock relay: the first process starts `127.0.0.1:8765`.

## 5. Setup

Do **not** use `uv run python` for this demo on 3.13/3.14: it recreates `.venv`, skips `.[nostr]`, then `import pynostr` fails. Use `./examples/agent-to-merchant-pay.sh` or `.venv-nostr/bin/python examples/agent-to-merchant-pay.py`.

If both swarm processes run on the **Mac** (live), use the **Mac** container. The AWS column is for invoicing or debugging on the instance, **not** paying the local Aperture invoice.

Before a **new live** run of the same `--url`, bump `--round` if a result for this invoice is already on the relay.

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
# if health times out: ./update-aws-sg-my-ip.sh   # do not world-open 8081
```

## 7. Run

Same wrapper for first time and later runs. `--relay` is ignored; set `NOSTR_RELAYS` for the live path. There is no message directory to clear. If a result for this invoice and `--round` is already on the relay, bump `--round`. The mock relay forgets events about 60 seconds after the last client disconnects.

### Mock (any one host)

```bash
# Terminal A
./examples/agent-to-merchant-pay.sh --role alice --offline-bus --no-llm

# Terminal B
./examples/agent-to-merchant-pay.sh --role bob --offline-bus --no-llm
```

One process (two threads):

```bash
./examples/agent-to-merchant-pay.sh --role both --offline-bus --no-llm
```

### Live (Mac, two terminals)

**No** `--offline-bus`. Start Alice, wait for `waiting for`, then start Bob within `--timeout`.

```bash
# Terminal A
./examples/agent-to-merchant-pay.sh --role alice --no-llm \
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100

# Terminal B
./examples/agent-to-merchant-pay.sh --role bob --no-llm \
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
| `Stale result already on the relay` | Bump `--round`. Do not delete key files. The mock relay also drops events ~60s after both processes exit. |
| Timeout waiting for peer | Same `--dir`, same `--url`, both processes on **one** host. Start Alice first. Mock: both use `127.0.0.1` (not two machines). Live: both use the same `NOSTR_RELAYS`. |
| Missing pynostr / uv 3.14 | Do not use `uv run python`. `uv venv -p 3.12 .venv-nostr` then `uv pip install --python .venv-nostr/bin/python -e '.[nostr]'`. Run `./examples/agent-to-merchant-pay.sh` |

Sequence of a paid GET: [docs/architecture.md — L402 request sequence](../docs/architecture.md#l402-request-sequence). Operator gateway: [docs/l402-aperture.md](../docs/l402-aperture.md).
