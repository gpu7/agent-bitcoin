# Connect an external agent to L402

Operator + their engineer. Paid HTTP is `https://agent-bitcoin.net` (TLS on **443**). **8081** stays restricted to the operator. Aperture is still plain HTTP behind Caddy. Details: [l402-public-endpoint.md](./l402-public-endpoint.md).

## What this is

An external agent pays **our AWS Aperture** for existing JSON tools. Aperture is the **cash register** (HTTP 402 + BOLT11). Origin returns JSON after pay. We do **not** run their node (not an A-kit).

## Requirements

- Their process can reach `https://agent-bitcoin.net` on port **443**. They do **not** need an **8081** `/32`.
- Lightning payer **≠** our AWS invoice LND. They pay with **their** LND (or SDK + their node). Paying our invoice with our AWS node is self-pay and fails.
- A path that can send **100 sats**. Prefer a **direct private channel** to our AWS node. Public multi-hop is unreliable at 100 sats.
- An L402 client: unpaid GET/POST → **402** + BOLT11 → pay → retry `Authorization: L402 <macaroon>:<preimage>`. Use [`examples/l402_pay.py`](../examples/l402_pay.py) or [`L402Client`](../SDK.md#l402-aperture).

## Step-by-step

1. **Agree a trial.** One path, e.g. `GET https://agent-bitcoin.net/paid/finance/mempool-feerate` at **100 sats**. Other routes: [l402-tools.md](./l402-tools.md). Finance/Nostr tools are typically 100 sats; hello/PDF/PNG are 1,000.

2. **They probe** from their host:

   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' https://agent-bitcoin.net/health
   # 200
   curl -sS -D - -o /dev/null https://agent-bitcoin.net/paid/finance/mempool-feerate
   # 402 and a BOLT11 starting lnbc1u
   ```

   Timeout / hang = DNS or port 443. `500` challenge failure = our AWS LND is **locked**.

3. **Lightning.** They connect to AWS LND and open a **private** channel with **outbound** (their side can send 100 sats). Peer port **9735** may still be an operator-added `/32`. **10009 stays closed**. Do not pass `MY_IP=<client>` to `./update-aws-sg-my-ip.sh` — that script is additive for the Mac.

   ```text
   0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967@3.90.159.146:9735
   ```

   We do **not** pay from AWS for them (self-pay / we are not their wallet). Not our Mac wallet either.

4. **Paid call** from their machine, using **their** LND env (and mainnet latches if mainnet):

   ```bash
   uv run python examples/l402_pay.py \
     --url https://agent-bitcoin.net/paid/finance/mempool-feerate \
     --price 100
   ```

5. **Their agent** loops the same L402 client.

6. **We operate:** AWS LND unlocked, channel active, `listinvoices` / origin logs. **Revoke** a Lightning peer by deleting their `/32` on **9735** if one was opened. Do **not** open **8081** to the client or to `0.0.0.0/0`.

## What this is not

- A reason to world-open **8081** (public HTTPS is **443**)
- Card checkout (no Lightning ⇒ no path)
- Required: Nostr, swarm, or Grok

Installer sketch (Neutrino LND on their box): [l402-client-pack.md](./l402-client-pack.md).

## Pointers

- Routes: [l402-tools.md](./l402-tools.md)
- Diagrams: [architecture.md](./architecture.md)
- Client: [examples/l402_pay.py](../examples/l402_pay.py)
- [examples/agent-swarm-merchant-2.md](../examples/agent-swarm-merchant-2.md) is **our** lab (Mac payer). It is not the client’s setup.
