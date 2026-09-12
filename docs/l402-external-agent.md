# Connect an external agent to L402

Operator + their engineer. Known client, ~100 sats, **8081 stays allowlisted**. HTTP as deployed today (`http://3.90.159.146:8081`). No TLS terminator in this lab.

## What this is

An external agent pays **our AWS Aperture** for existing JSON tools. Aperture is the **cash register** (HTTP 402 + BOLT11). Origin returns JSON after pay. This is not a public marketplace. We do **not** run their node (not an A-kit).

## Requirements

- Their process can reach `http://3.90.159.146:8081` (after we add their **egress /32**).
- Lightning payer **≠** our AWS invoice LND. They pay with **their** LND (or SDK + their node). Paying our invoice with our AWS node is self-pay and fails.
- A path that can send **100 sats**. Prefer a **direct private channel** to our AWS node. Public multi-hop is unreliable at 100 sats.
- An L402 client: unpaid GET/POST → **402** + BOLT11 → pay → retry `Authorization: L402 <macaroon>:<preimage>`. Use [`examples/l402_pay.py`](../examples/l402_pay.py) or [`L402Client`](../SDK.md#l402-aperture).

## Step-by-step

1. **Agree a trial.** One path, e.g. `GET http://3.90.159.146:8081/paid/finance/mempool-feerate` at **100 sats**. Other routes: [l402-tools.md](./l402-tools.md). Finance/Nostr tools are typically 100 sats; hello/PDF/PNG are 1,000.

2. **Client gives egress /32** of the **agent host**. A VPS is more stable than a home ISP (home IPv4 often changes).

3. **We add that /32 on TCP 8081** (same idea as [`update-aws-sg-my-ip.sh`](../update-aws-sg-my-ip.sh), with **their** IP — not ours). **10009 stays closed** (LND gRPC is not public). Optionally allow **9735** if they will open a channel.

4. **They probe** from that host:

   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' http://3.90.159.146:8081/health
   # 200
   curl -sS -D - -o /dev/null http://3.90.159.146:8081/paid/finance/mempool-feerate
   # 402 and a BOLT11 starting lnbc1u
   ```

   Timeout / hang = SG or wrong IP. `500` challenge failure = our AWS LND is **locked**.

5. **Lightning.** They connect to AWS LND and open a **private** channel with **outbound** (their side can send 100 sats):

   ```text
   0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967@3.90.159.146:9735
   ```

   We do **not** pay from AWS for them (self-pay / we are not their wallet). Not our Mac wallet either.

6. **Paid call** from their machine, using **their** LND env (and mainnet latches if mainnet):

   ```bash
   uv run python examples/l402_pay.py \
     --url http://3.90.159.146:8081/paid/finance/mempool-feerate \
     --price 100
   ```

7. **Their agent** loops the same L402 client. We only **add or remove** the SG rule.

8. **We operate:** AWS LND unlocked, channel active, `listinvoices` / origin logs. **Revoke** = delete their `/32` on 8081 (and 9735 if we opened it).

## What this is not

- A public URL for anyone
- `0.0.0.0/0` on 8081
- Card checkout (no Lightning ⇒ no path)
- Required: Nostr, swarm, or Grok

## Pointers

- Routes: [l402-tools.md](./l402-tools.md)
- Diagrams: [architecture.md](./architecture.md)
- Client: [examples/l402_pay.py](../examples/l402_pay.py)
- [examples/swarm_l402.md](../examples/swarm_l402.md) is **our** lab (Mac payer). It is not the client’s setup.
