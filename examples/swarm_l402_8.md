# Eight-agent swarm: who pays one L402 tool

Eight Nostr identities (`a1`…`a8`), signed file-bus messages, **one** winner pays `GET /paid/finance/mempool-feerate` (100 sats). Same jobs as the [two-agent demo](./swarm_l402.md). Coded policy picks the payer. Optional Grok explains; **`--no-llm` is the required path**.

Agents are **processes**, not Lightning nodes. One Mac LND wallet, one existing private channel, **one** pay per successful live run. Do not start eight LNDs. Do not open channels.

## 1. What you will see

Eight **npubs** (never nsec), eight scores, one `i_pay=True`. That winner runs L402 once. Losers wait for a signed `result` and print it.

- **Mock:** `paid=True` and bands **3/2/1** (fixture). No sats.
- **Live:** `paid=True` and real fee bands. Mac `lncli listpayments` shows ~100 sat SUCCEEDED.

## 2. Topology (reuse two-agent)

| Piece | Where |
|-------|--------|
| Eight swarm processes | **Mac** (shared `.nostr-poc/bus`) |
| Payer LND | **Mac** `agent-bitcoin-lnd*` |
| Aperture + invoice LND | **AWS** |
| URL | `http://3.90.159.146:8081/paid/finance/mempool-feerate` |

Live pay is **Mac → AWS**. Splitting agents across Mac and AWS breaks the file bus unless they rsync (**out of scope**). Details: [swarm_l402.md](./swarm_l402.md).

## 3. First time vs repeat `.venv-nostr`

Do **not** use `uv run python` on 3.13/3.14.

**First time**

```bash
cd ~/agent-bitcoin   # Mac clone for live
git pull
uv venv -p 3.12 .venv-nostr
uv pip install --python .venv-nostr/bin/python -e '.[nostr]'
export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
```

**Later:** skip `uv venv` if `.venv-nostr` exists. Re-run `uv pip install … -e '.[nostr]'` only after dependency changes. Same exports.

Use `./examples/swarm_l402_8.sh` (not `uv run python`).

## 4. Mock vs live

| Mode | Flags | Host |
|------|--------|------|
| **A. Mock** | `--offline-bus --no-llm` | Any one machine |
| **B. Live** | **No** `--offline-bus`; `--url http://3.90.159.146:8081/… --price 100` | All eight on the **Mac** |

Do **not** live-pay with `LND_CONTAINER=agent-payment-decision-lnd*` (Aperture invoices that node → self-pay). The script refuses it.

## 5. `LND_CONTAINER` (live = Mac column)

**Mac payer (live swarm)**

```bash
# mainnet
export LND_NETWORK=mainnet
export LND_CONTAINER=agent-bitcoin-lnd-mainnet
export LND_TRANSPORT=docker
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
```

Regtest: `agent-bitcoin-lnd`. Signet: `agent-bitcoin-lnd-signet` (no mainnet latches).

**AWS LND** (`agent-payment-decision-lnd*`) is invoice/debug only — not the live swarm payer.

## 6. Setup keys

Eight files under `.nostr-poc/`: `a1.enc.json` … `a8.enc.json`. Created on first `--role aN` (or `--role all`) if missing. Distinct from two-agent `alice.enc.json` / `bob.enc.json`.

```bash
export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
# first run may pass --force-new-keys once
```

Never commit nsec.

## 7. Preflight (live, Mac)

```bash
# Mac + AWS LND unlocked; Mac listchannels: active, local_balance >> 100
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet getinfo
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet listchannels

curl -sS -o /dev/null -w '%{http_code}\n' http://3.90.159.146:8081/health
# 200
curl -sS -o /dev/null -w '%{http_code}\n' \
  http://3.90.159.146:8081/paid/finance/mempool-feerate
# 402

rm -f .nostr-poc/bus/*.json
# if health times out: ./update-aws-sg-my-ip.sh  — do not world-open 8081
```

## 8. Run

Engineer path — **eight terminals**, one bus dir:

```bash
./examples/swarm_l402_8.sh --role a1 --offline-bus --no-llm
# … a2 … a8 in the other terminals, same flags
```

Launcher (eight background jobs, still one bus):

```bash
./examples/swarm_l402_8_all.sh --offline-bus --no-llm
tail -f .nostr-poc/logs/a*.log
```

One process, eight threads:

```bash
./examples/swarm_l402_8.sh --role all --offline-bus --no-llm
```

Live (Mac, empty bus, **no** `--offline-bus`):

```bash
./examples/swarm_l402_8_all.sh --no-llm \
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100
```

`--relay` is ignored. Happy path is `.nostr-poc/bus/`.

## 9. Check

Winner: `i_pay=True reason=higher_score`, `status=200 paid=True`. Mock bands 3/2/1; live bands from origin.

```bash
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet listpayments --max_payments 3
# ~100 sat SUCCEEDED. Do not paste preimages.
```

Mock: skip `listpayments`.

## 10. Stop

Agent processes exit when the run finishes (`wait` in `swarm_l402_8_all.sh`). **LND stays up.** Ctrl-C a hung terminal if needed; do not shut down compose unless you intend to.

## 11. Liquidity

Eight agents share **one** Mac outbound balance. Budget ~3200+ local sats so one 100-sat pay plus routing still fits. Only **one** L402 pay per successful run.

Bus files: `{invoice_id}_aN_negotiate.json`, `{invoice_id}_aN_concede.json` (losers), `{invoice_id}_result.json` (winner). Same `--url` reuses `invoice_id` — clear the bus before a rerun.
