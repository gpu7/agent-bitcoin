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

NIP-17 gift wrap (kind 1059), not a public kind-1 note. Relays are **transport**, not a marketplace. Default `NOSTR_RELAYS=wss://relay.damus.io,wss://nos.lol`.

Keys: same Phase A encrypted files as other examples (`NOSTR_PASSPHRASE`, `NOSTR_POC_DIR=.nostr-poc`). Defaults `a2a_payee` (AWS) and `a2a_payer` (Mac). Exchange **npubs** once (not nsec).

```bash
export NOSTR_PASSPHRASE='choose-a-local-passphrase'
export NOSTR_POC_DIR=.nostr-poc
```

AWS (prints `sent` only — no BOLT11):

```bash
export LND_CONTAINER=agent-payment-decision-lnd-mainnet
export AGENT_BITCOIN_ALLOW_MAINNET=1
export LND_NETWORK=mainnet
export LND_TRANSPORT=docker
uv run python examples/a2a_ln_pay.py invoice-dm --to-npub npub1mxhtkr0658tksmj7usred7jep0am0aqnhvmck2dgs472q90dxd5stdl7xg74c5a12a2767789e6e85c9f1e36a728d0a3c979cc13b25a7a5b1e58e83a413aa --sats 100
```

Mac:

```bash
export LND_CONTAINER=agent-bitcoin-lnd-mainnet
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
export LND_NETWORK=mainnet
export LND_TRANSPORT=docker
uv run python examples/a2a_ln_pay.py pay-dm --from-npub npub1a5valg8raheywc7vhmzewsewaag0rafgwt4cevtdrrjw7cmy36csh3e8jp37e2ddb3625fb6c13c98bc65b33f6ea07a87eb6691a417db4de32f1e58b5fc0a --sats 100 --wait 60
```

Payer decrypts, checks amount/expiry, pays once. Timeout / no DM → exit 1, no pay.

The script prints `payment_hash` and `preimage` on pay, then an `lncli listpayments --max_payments 3` hint. Do not paste preimages or nsec into git.

Offline: `invoice --offline` / `pay --bolt11 lnbc1offline --offline` / `invoice-dm --offline` (no relay).

Swarm (merchant L402, one wallet): [swarm_l402.md](./swarm_l402.md).
