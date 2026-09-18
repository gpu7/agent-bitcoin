# Agent-to-agent Lightning (two LND nodes)

Two **Lightning nodes**, one 100-sat invoice, one pay. This is **not** the swarm: Alice/Bob (or a1…a8) share **one** Mac wallet and pick who pays **our Aperture merchant**. Here the payee and payer are different `LND_CONTAINER`s.

| Role | Node |
|------|------|
| **Payee** (creates invoice) | AWS `agent-payment-decision-lnd-mainnet` |
| **Payer** | Mac `agent-bitcoin-lnd-mainnet` **or** Ubuntu `l402-client-lnd` |

Need a channel with outbound on the **payer** (private is fine). Not Aperture. Not self-pay (do not invoice and pay the same container).

## SSH paste (still valid)

Payee prints a BOLT11; you copy it to the payer.

### Payee (AWS)

```bash
export AGENT_BITCOIN_ALLOW_MAINNET=1
export LND_NETWORK=mainnet
export LND_TRANSPORT=docker
export LND_CONTAINER=agent-payment-decision-lnd-mainnet
uv run python examples/a2a_ln_pay.py invoice --sats 100
# copy the printed BOLT11 to the payer
```

Payee does **not** need `ALLOW_AUTOPAY`.

### Payer (Mac)

```bash
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
export LND_NETWORK=mainnet
export LND_TRANSPORT=docker
export LND_CONTAINER=agent-bitcoin-lnd-mainnet
uv run python examples/a2a_ln_pay.py pay --bolt11 'lnbc1…'
```

Ubuntu client pack as payer: `LND_CONTAINER=l402-client-lnd` ([l402-client-pack.md](../docs/l402-client-pack.md)).

## Encrypted Nostr DM (no SSH)

NIP-17 gift wrap (kind 1059), not a public kind-1 note. Relays are **transport**, not a marketplace. Use `.venv-nostr/bin/python` after `uv pip install --python .venv-nostr/bin/python -e '.[nostr]'` — not `uv run python` (that venv lacks `bech32` / pynostr).
Default `NOSTR_RELAYS=wss://relay.damus.io,wss://nos.lol`.
Defaults `a2a_payee` (AWS) and `a2a_payer` (Mac). Exchange **npubs** once (not nsec).

AWS:

Run commands on AWS:

```bash
export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
export LND_CONTAINER=agent-payment-decision-lnd-mainnet
export AGENT_BITCOIN_ALLOW_MAINNET=1
export LND_NETWORK=mainnet
export LND_TRANSPORT=docker

.venv-nostr/bin/python examples/a2a_ln_pay.py invoice-dm \
  --to-npub npub1mxhtkr0658tksmj7usred7jep0am0aqnhvmck2dgs472q90dxd5stdl7xg \
  --sats 100
```

Mac:

Run commands on Mac:

```bash
export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
export LND_CONTAINER=agent-bitcoin-lnd-mainnet
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
export LND_NETWORK=mainnet
export LND_TRANSPORT=docker

.venv-nostr/bin/python examples/a2a_ln_pay.py pay-dm \
  --from-npub 'npub1a5valg8raheywc7vhmzewsewaag0rafgwt4cevtdrrjw7cmy36csh3e8jp' \
  --sats 100 \
  --wait 60
```

Payer decrypts, checks amount/expiry, pays once. Timeout / no DM → exit 1, no pay.

The script prints `payment_hash` and `preimage` on pay, then an `lncli listpayments --max_payments 3` hint. Do not paste preimages or nsec into git.

Offline: `invoice --offline` / `pay --bolt11 lnbc1offline --offline` / `invoice-dm --offline` (no relay).

Role wrapper (payer gate optional): [agent-to-agent-pay.md](./agent-to-agent-pay.md).

Swarm (merchant L402, one wallet): [agent-to-merchant-pay.md](./agent-to-merchant-pay.md).
