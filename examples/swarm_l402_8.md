# Eight-agent swarm: who pays one L402 tool

Eight Nostr identities (`a1`…`a8`), signed file-bus messages, **one** winner pays `GET /paid/finance/mempool-feerate` (100 sats). Same jobs as the [two-agent demo](./swarm_l402.md). Coded policy picks the payer. Optional Grok explains in one sentence each and **never** pays. **`--no-llm` is the required path.**

Agents are **processes**, not Lightning nodes. One Mac LND wallet, one existing private channel, **one** pay per successful live run. Do not start eight LNDs. Do not open channels. The wrapper passes `--expect-peers 8`.

**Two modes — do not mix them:**

| Mode | Where | Lightning |
|------|--------|-----------|
| **A. Mock** | Any one host (AWS or Mac) | None (`--offline-bus`) |
| **B. Live L402** | **All eight processes on the Mac**; Aperture + invoice LND on **AWS** | Mac `agent-bitcoin-lnd*` pays the AWS invoice |

Live pay is **Mac → AWS**, not eight processes on AWS using AWS LND (that is self-pay).

## 1. What you will see

Eight **npubs** (never nsec), eight scores, one `i_pay=True`. That winner runs L402 once. Losers wait for a signed `result` and print it.

- **Mock:** `paid=True` and fee bands **3/2/1** (fixture). No sats move.
- **Live:** `paid=True` and real `fast` / `medium` / `slow` bands — **not** 3/2/1 unless the origin really returned that.

## 2. Prerequisites

- L402 stack up on AWS: `./startup-l402-aws.sh <regtest|signet|mainnet>`
- **Live:** Mac clone on the 8081 `/32`; Mac LND unlocked; channel **Mac → AWS** with **local** (outbound) ≫ 100 sats + routing (~3200+ so one 100-sat pay plus routing still fits)
- `XAI_API_KEY` optional. Without it, `--no-llm`
- Python **3.12** + `.venv-nostr` + `.[nostr]` — [SDK.md](../SDK.md). Do **not** use `uv run python` on 3.13/3.14

## 3. Security

**Do not** world-open 8081 or 10009. Do not put nsec, NWC URIs, macaroons, or `XAI_API_KEY` in git. `.nostr-poc/` is gitignored.

Live HTTP is from the **Mac** to `http://3.90.159.146:8081`. On-box `http://127.0.0.1:8081` is for **mock** or for a client whose payer LND is **not** the Aperture invoice node (AWS LND).

Splitting agents across Mac and AWS breaks the file bus unless they rsync (**out of scope**).

## 4. Two demo modes

### A. Mock (any one host, including AWS)

```bash
./examples/swarm_l402_8.sh --role a1 --offline-bus --no-llm
# terminals a2 … a8, same flags
```

Or one launcher (still one bus dir):

```bash
./examples/swarm_l402_8_all.sh --offline-bus --no-llm
```

No LND pay. Fine for Nostr ids + negotiate. All eight processes must share the **same** `.nostr-poc/bus` on **one disk**.

### B. Live L402 (required topology)

| Piece | Where |
|-------|--------|
| Aperture + invoice LND | **AWS** |
| Payer LND | **Mac** `agent-bitcoin-lnd*` |
| Eight swarm processes | **Mac** (shared `.nostr-poc/bus`) |
| URL | `http://3.90.159.146:8081/paid/finance/mempool-feerate` |
| Flags | **No** `--offline-bus`; `--price 100` |
| Do **not** | Use `LND_CONTAINER=agent-payment-decision-lnd*` as the live payer |

The script refuses live pay from the AWS invoice node (self-pay).

## 5. Setup

Do **not** use `uv run python` for this demo on 3.13/3.14: it recreates `.venv`, skips `.[nostr]`, then `import pynostr` fails. Use `./examples/swarm_l402_8.sh` or `.venv-nostr/bin/python examples/swarm_l402_negotiate.py --expect-peers 8`.

If all eight processes run on the **Mac** (live), use the **Mac** container below. AWS invoice names are notes only — **not** live-pay exports.

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

Then copy **one** network block. First run can use `--force-new-keys` once. Keys are `a1.enc.json` … `a8.enc.json` (distinct from two-agent `alice` / `bob`). Created if missing.

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

```bash
export LND_NETWORK=regtest
export LND_CONTAINER=agent-bitcoin-lnd
export LND_TRANSPORT=docker
```

AWS invoice node (do **not** live-pay from it): `agent-payment-decision-lnd`. No mainnet latches. Mock may use `http://127.0.0.1:8081/...` on either host.

### Signet

```bash
export LND_NETWORK=signet
export LND_CONTAINER=agent-bitcoin-lnd-signet
export LND_TRANSPORT=docker
```

AWS invoice node (do **not** live-pay from it): `agent-payment-decision-lnd-signet`. Confirm L402 started with `./startup-l402-aws.sh signet`.

### Mainnet

```bash
export LND_NETWORK=mainnet
export LND_CONTAINER=agent-bitcoin-lnd-mainnet
export LND_TRANSPORT=docker
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
```

AWS invoice node (do **not** live-pay from it): `agent-payment-decision-lnd-mainnet`. Real sats. Autoloop stays off. Only if you intend a live 100-sat pay from the **Mac**.

## 6. Live preflight (Mac)

Mainnet names shown. Regtest/signet: `agent-bitcoin-lnd` / `agent-bitcoin-lnd-signet` and `--network=regtest|signet`. Unlock **Mac and AWS** LND. No secrets.

```bash
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet getinfo
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet listchannels
# want: unlocked, synced; a channel active with local_balance >> 100
# eight agents share one outbound; ~3200+ local sats is comfortable

curl -sS -o /dev/null -w '%{http_code}\n' http://3.90.159.146:8081/health
# 200
curl -sS -o /dev/null -w '%{http_code}\n' \
  http://3.90.159.146:8081/paid/finance/mempool-feerate
# 402

rm -f .nostr-poc/bus/*.json
# if health times out: ./update-aws-sg-my-ip.sh   # do not world-open 8081
```

## 7. Run

Same wrapper for first time and later runs. `--relay` is accepted and ignored; happy path is `.nostr-poc/bus/`. `swarm_l402_8.sh` adds `--expect-peers 8`.

### Mock (any one host)

Engineer path — **eight terminals**, one bus dir:

```bash
./examples/swarm_l402_8.sh --role a1 --offline-bus --no-llm
./examples/swarm_l402_8.sh --role a2 --offline-bus --no-llm
# … a3 … a8
```

Launcher (eight background jobs; `tail -f .nostr-poc/logs/a*.log`):

```bash
./examples/swarm_l402_8_all.sh --offline-bus --no-llm
```

One process (eight threads):

```bash
./examples/swarm_l402_8.sh --role all --offline-bus --no-llm
```

### Live (Mac, empty bus)

**No** `--offline-bus`. After `rm -f .nostr-poc/bus/*.json`:

```bash
./examples/swarm_l402_8_all.sh --no-llm \
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100
```

Or eight terminals with `./examples/swarm_l402_8.sh --role aN --no-llm --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100`.

Expected log (npubs will differ). Mock bands are **3/2/1**; live bands come from the origin:

```text
[a1] npub=npub1… invoice_id=… score=…
[a2] npub=npub1… invoice_id=… score=…
…
[a3] winner_npub=npub1… i_pay=True reason=higher_score
[a3] l402 status=200 paid=True amount_sats=100 summary={'fast': …, 'medium': …, 'slow': …}
[a1] result payer_npub=npub1… paid=True summary={'fast': …, 'medium': …, 'slow': …}
```

Agent processes exit when the run finishes (`wait` in `swarm_l402_8_all.sh`). **LND stays up.**

## 8. How to check the Lightning pay

- Client: `status=200` and `paid=True` on the **one** winner line
- Origin JSON: integers `fast` / `medium` / `slow` only in the summary
- **Mock:** skip `listpayments` (no sats)
- **Live:** on the **Mac** node (redacted):

```bash
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet listpayments --max_payments 3
# ~100 sat SUCCEEDED. Do not paste preimages.
```

Only **one** L402 pay per successful run.

## 9. How IDs show up

Printed: `npub=npub1…`. Encrypted nsec stays in `.nostr-poc/a1.enc.json` … `a8.enc.json` (mode 0600). Never print or commit nsec.

Bus: `{invoice_id}_aN_negotiate.json`, `{invoice_id}_aN_concede.json` (losers), `{invoice_id}_result.json` (winner).

## 10. Troubleshooting

| Symptom | What to do |
|---------|------------|
| 402 loop / `paid=False` | Price mismatch: pass `--price 100` for feerate. Client default elsewhere is 1000. |
| Connection refused / health timeout :8081 | Not on the `/32`. `./update-aws-sg-my-ip.sh`. **Do not open SG.** L402: `./startup-l402-aws.sh <network>` |
| LND locked / macaroon errors | Unlock the **Mac payer** wallet; `LND_CONTAINER` is `agent-bitcoin-lnd*` |
| Amount below floor | Min invoice is **100 sats** (`MIN_PAYMENT_SATS`) |
| `No such container: agent-bitcoin-lnd-mainnet` on AWS | Wrong host. Live payer is the **Mac** |
| `self-payments not allowed` | Payer == invoice node. Use Mac `agent-bitcoin-lnd*` + `--url http://3.90.159.146:8081/…`. Do not enable LND self-pay |
| Agent exits instantly with bands 3/2/1 | Stale bus and/or `--offline-bus`. `rm -f .nostr-poc/bus/*.json` |
| Timeout waiting for peer | Same `--dir`, same `--url`, all eight on **one** Mac; bus is `$NOSTR_POC_DIR/bus/` |
| Missing pynostr / uv 3.14 | Do not use `uv run python`. `uv venv -p 3.12 .venv-nostr` then `uv pip install --python .venv-nostr/bin/python -e '.[nostr]'`. Run `./examples/swarm_l402_8.sh` |

Sequence of a paid GET: [docs/architecture.md — L402 request sequence](../docs/architecture.md#l402-request-sequence). Operator gateway: [docs/l402-aperture.md](../docs/l402-aperture.md). Two-agent: [swarm_l402.md](./swarm_l402.md).
