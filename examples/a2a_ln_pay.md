# Agent-to-agent Lightning (two LND nodes)

Two **Lightning nodes**, one 100-sat invoice, one pay. This is **not** the swarm: Alice/Bob (or a1…a8) share **one** Mac wallet and pick who pays **our Aperture merchant**. Here the payee and payer are different `LND_CONTAINER`s.

| Role | Node |
|------|------|
| **Payee** (creates invoice) | AWS `agent-payment-decision-lnd-mainnet` |
| **Payer** | Mac `agent-bitcoin-lnd-mainnet` **or** Ubuntu `l402-client-lnd` |

Need a channel with outbound on the **payer** (private is fine). Not Aperture. Not self-pay (do not invoice and pay the same container).

## Latches (same as live L402)

Set these environment variables on the payer and payee machines:

```bash
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
export LND_NETWORK=mainnet
export LND_TRANSPORT=docker
```

## Payee (AWS)

Run these commands on AWS:

```bash
export LND_CONTAINER=agent-payment-decision-lnd-mainnet
uv run python examples/a2a_ln_pay.py invoice --sats 100
# copy the printed BOLT11 to the payer
```

## Payer (Mac)

Run these commands on Mac:

```bash
export LND_CONTAINER=agent-bitcoin-lnd-mainnet
uv run python examples/a2a_ln_pay.py pay --bolt11 'lnbc1…'
```

Ubuntu client pack as payer: `LND_CONTAINER=l402-client-lnd` ([l402-client-pack.md](../docs/l402-client-pack.md)).

The script prints `payment_hash` and `preimage`, then an `lncli listpayments --max_payments 3` hint. Do not paste preimages into git.

Offline (no LND): `… invoice --offline` / `… pay --bolt11 lnbc1offline --offline`.

Swarm (merchant L402, one wallet): [swarm_l402.md](./swarm_l402.md).
