# Agent-to-agent Lightning pay (two LND nodes)

Two **different LND wallets**. One 100-sat invoice, one pay, optional Grok/Ollama **gate on the payer only**.

This is **not** [agent-swarm-merchant-2.md](./agent-swarm-merchant-2.md) (Alice/Bob share **one** Mac LND and pay **Aperture**).

| Role | Node | LLM |
|------|------|-----|
| **payee** | AWS `agent-payment-decision-lnd-mainnet` | never |
| **payer** | Mac `agent-bitcoin-lnd-mainnet` or Ubuntu `l402-client-lnd` | `--no-llm` or `--model grok\|ollama` |

Raw BOLT11 paste (no DM): [a2a_ln_pay.md](./a2a_ln_pay.md).

Use `.venv-nostr/bin/python` after `uv pip install --python .venv-nostr/bin/python -e '.[nostr]'` — not `uv run python`.

**Start the payer first**, then the payee (payer is listening for the encrypted DM).

## Payee (AWS)

```bash
export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
export LND_NETWORK=mainnet
export LND_TRANSPORT=docker
export LND_CONTAINER=agent-payment-decision-lnd-mainnet
export AGENT_BITCOIN_ALLOW_MAINNET=1
# no AUTOPAY on payee
./examples/agent-to-agent-pay.sh --role payee --to-npub npub1…payer --sats 100
# prints: sent
```

## Payer (Mac) — no LLM

```bash
export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
export LND_NETWORK=mainnet
export LND_TRANSPORT=docker
export LND_CONTAINER=agent-bitcoin-lnd-mainnet
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
./examples/agent-to-agent-pay.sh --role payer --from-npub npub1…payee --sats 100 --wait 60 --no-llm
```

## Payer — Grok gate

```bash
export XAI_API_KEY=   # local only; never commit
./examples/agent-to-agent-pay.sh --role payer --from-npub npub1…payee --sats 100 --model grok
```

## Payer — Ollama gate

```bash
# ollama pull llama3.2
./examples/agent-to-agent-pay.sh --role payer --from-npub npub1…payee --sats 100 --model ollama
```

`--no-llm` cannot combine with `--model`. Ollama down → vote NO, no pay. Test hook: `A2A_LLM_FORCE_VOTE=YES` or `NO` (do not default).

Offline: `--offline` (no LND, no relays).
