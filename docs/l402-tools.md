# L402 tool suites (for agents)

Paid JSON tools behind Aperture L402. This page is for an **external autonomous agent** (or its developer): what each tool is for, how to call it, one example. Operators who run the gateway: [l402-aperture.md](./l402-aperture.md). SDK client: [SDK.md — L402](../SDK.md#l402-aperture).

## What this is

Aperture sits in front of a dummy HTTP origin on **`:8081`**. Unpaid `GET`/`POST` to a paid path returns **HTTP 402** plus a Lightning invoice. Pay at least **`MIN_PAYMENT_SATS`** (default **100**), then retry with L402 auth (`Authorization: L402 <macaroon>:<preimage>`). Prefer [`L402Client`](../SDK.md#l402-aperture) or [`examples/l402_pay.py`](../examples/l402_pay.py) so that handshake is automatic.

Every paid path is **100 sats**, including hello, PDF, PNG, finance, Nostr, and security. `/health` and `/.well-known/l402-services` are free. There is **no platform fee**; the L402 price **is** the Lightning amount.

The public base URL is `https://agent-bitcoin.net` (port **443**). Aperture still listens on plain HTTP **8081**, which stays restricted to the operator. See [l402-public-endpoint.md](./l402-public-endpoint.md).

## Agent discovery via 402index

Agents do not need the human directory page. They use machine-readable channels.

**HTTP API (primary)**

- Search: `GET https://402index.io/api/v1/services?protocol=L402&health=healthy&q=btc-usd`
- Direct: `GET https://402index.io/api/v1/services/b16b5e05-8e6e-476f-b2fa-a996a8fd4f17`

The response supplies the live URL (`https://agent-bitcoin.net/paid/finance/btc-usd`), the price in sats, and health. The agent then calls that URL, receives the 402, pays, and retries.

**MCP.** Agents inside an MCP host can use `@402index/mcp-server` (tools `search_services`, `get_service_detail`).

**RSS:** `https://402index.io/feed.xml?protocol=L402&health=healthy`

Webhooks, [llms.txt](https://402index.io/llms.txt), and the [OpenAPI spec](https://402index.io/api/v1/openapi.json) exist for additional automation.

Once the agent has the URL from the directory, it treats the endpoint exactly like any other L402 resource. No prior relationship is required.

![Agent payment via 402index](images/agent-402index.jpeg)

*Real example: an agent searched 402index for the btc-usd endpoint, paid 100 sats over L402, and received the current BTC-USD price. The same four steps work for any healthy L402 listing.*

The listing name is `btc-usd` and the description says “Bitcoin price”, so both `btc-usd` and `bitcoin price` queries match. The unit of account remains sats.

The origin also serves `GET https://agent-bitcoin.net/.well-known/l402-services` (`Content-Type: application/json`, HTTP 200, no payment). The document is [`l402/well-known/l402-services.json`](../l402/well-known/l402-services.json). It lists every public paid tool. Add each new public endpoint to that file.

The existing Caddy reverse proxy forwards the path to Aperture, which leaves it free alongside `/health`, and the origin returns the JSON. This repo does not call 402index. A new row shows up in search only after an operator registers it, or after a later crawl reads this file.

## How an external agent uses any tool

![L402: pay then JSON](images/l402-pay-flow.png)

*Unpaid request → Lightning pay → JSON. Typical tool price 100 sats.*

1. Call `https://agent-bitcoin.net` (this lab).
2. Call with `L402Client(..., expected_price_sats=100)` or `l402_pay.py --price 100`. The SDK default expected price is **100**.
3. **GET** for Bitcoin-suite query tools and the channel summary. **POST** JSON for the address check, the challenge inspect, Lightning invoices, and Nostr tools (GET → **405**).
4. Do **not** put BOLT11 in query strings. POST it in JSON (`--json`).
5. Read `ttl_s` and cache. Do not poll every second. Local inspect tools (`ttl_s` 0) are still not a hot loop.
6. Wiring, SG, and restart: [l402-aperture.md](./l402-aperture.md). Mainnet pays still need the usual latches on the payer.

Sequence (402 → pay → retry): [architecture.md — L402 request sequence](./architecture.md#l402-request-sequence).
Two agents negotiate who pays one GET: [examples/agent-swarm-merchant-2.md](../examples/agent-swarm-merchant-2.md) (live demo pays from the Mac). Coordination is signed kind 8139 on `NOSTR_RELAYS` (verify before trust). `--offline-bus` is a localhost mock relay. The L402 GET/POST itself stays unsigned HTTP.
Connect a **client** agent (their node, public HTTPS): [l402-external-agent.md](./l402-external-agent.md).
Client pack (compose + setup + smoke): [l402-client-pack.md](./l402-client-pack.md).

Lab host below is `https://agent-bitcoin.net`. Use a **test** invoice for decode/preflight examples, not a live mainnet pay request.

## Bitcoin suite

**Function:** on-chain fee / fullness / FX digest for an agent about to touch **L1**. Lightning-only pays do **not** need feerate.

### GET `/paid/finance/mempool-feerate`

Job: sat/vB bands (`fast` / `medium` / `slow`) from a public fee API cache. Use this when you will broadcast or size an on-chain tx. Not a mempool.space UI.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/finance/mempool-feerate --price 100
```

### GET `/paid/finance/mempool-backlog`

Job: how full the mempool is (`tx_count`, `vsize`, `total_fee_sats`) — not fee bands. Pair with feerate when you care whether the chain is congested.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/finance/mempool-backlog --price 100
```

### GET `/paid/finance/fee-for-vsize?vsize=`

Job: `ceil(vsize × sat/vB)` for a tx size in **virtual bytes** (not weight). Range **110–100000**. Same cache as feerate.

```bash
uv run python examples/l402_pay.py \
  --url 'https://agent-bitcoin.net/paid/finance/fee-for-vsize?vsize=250' --price 100
```

### GET `/paid/finance/confirm-target`

Job: map a wait window (`minutes` 1–60) or named band (`fast`|`medium`|`slow`) onto `sat_vb`. Optional `vsize` adds `fee_sats`. Snap: 1–20 fast, 21–45 medium, 46–60 slow.

```bash
uv run python examples/l402_pay.py \
  --url 'https://agent-bitcoin.net/paid/finance/confirm-target?minutes=30' --price 100
```

### GET `/paid/finance/btc-usd`

Job: USD per 1 BTC from one public JSON URL, plus `sats_per_usd`. Pass-through mark, **not** our index and **not** an FX oracle.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/finance/btc-usd --price 100
```

## Verification

### POST `/paid/finance/btc-address-validate`

Job: check a Bitcoin address locally (Base58Check or bech32/bech32m). No LND and no bitcoind. **100 sats**. 402index category: `verification`.

Returns `valid`, `network` (`mainnet`, `testnet`, or `regtest`), `address_type` (`p2pkh`, `p2sh`, `p2wpkh`, `p2wsh`, or `p2tr`), and a short `reason` when invalid. An invalid address is still HTTP 200. Missing or non-string `address` is HTTP 400. GET is HTTP 405.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/finance/btc-address-validate \
  --price 100 --method POST \
  --json '{"address":"bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"}'
```

## Lightning suite

**Function:** inspect / gate / hint **before** `pay_invoice`. Suggested order: **decode → preflight → path-hint → pay**. Decode and preflight are in-process (no LND). **path-hint** is what **AWS agent LND** sees via readonly QueryRoutes; operators using their own `lnd` may skip paying that path.

### POST `/paid/finance/ln-invoice-decode`

Job: parse a BOLT11 for network, `amount_sats`, dest, payment hash, expiry. No LND. Does not echo the full invoice.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/finance/ln-invoice-decode \
  --price 100 --method POST \
  --json '{"bolt11":"<test invoice>"}'
```

### POST `/paid/finance/ln-invoice-preflight`

Job: reuse that parse and return `allow` plus reason codes (`expired`, `zero_amount`, `below_floor`, `above_max_sats`, `network_mismatch`, `duplicate_payment_hash`). More than one payment-hash (`p`) field is `allow: false` / `duplicate_payment_hash`. Floor is **100** sats. Not a route check.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/finance/ln-invoice-preflight \
  --price 100 --method POST \
  --json '{"bolt11":"<test invoice>","max_sats":50000,"network":"bitcoin"}'
```

### POST `/paid/finance/ln-path-fee-hint`

Job: first-path fee hint (`fee_sats`, `hop_count`) from AWS agent LND QueryRoutes. POST JSON XOR: `{ "dest_pubkey": "<66 hex>", "amount_sats": 1000 }` **or** `{ "bolt11": "<test invoice>" }`. Not Terminal/RTL; no route dump.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/finance/ln-path-fee-hint \
  --price 100 --method POST \
  --json '{"dest_pubkey":"<66 hex>","amount_sats":1000}'
```

### GET `/paid/lightning/ln-channel-stats`

Job: read-only counts and balances from the operator LND `ListChannels`. Returns `num_active`, `num_inactive`, `total_capacity_sats`, `total_local_balance_sats`, `total_remote_balance_sats`, and up to eight active rows with `channel_point` and `peer_alias` only. Does **not** unlock, open, close, or pay. **100 sats**. 402index category: `lightning`.

The origin macaroon must include `uri:/lnrpc.Lightning/ListChannels` in addition to QueryRoutes and DecodePayReq. Until that permission is baked, this route returns HTTP 503.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/lightning/ln-channel-stats --price 100
```

## Nostr suite

**Function:** **local** identity checks. These two do **not** talk to a relay (no 503 from relays). They are not Damus and not **NWC (Nostr Wallet Connect)**. NWC is a way for an agent to talk to a Lightning wallet over Nostr using a URI, instead of holding an LND admin macaroon.

Agent identity, NWC, and NIP-46 live elsewhere: [README — Nostr](../README.md#nostr-agent-identity), [nostr-agent-identity.md](./nostr-agent-identity.md), [nwc-automatic-wallets.md](./nwc-automatic-wallets.md).

### POST `/paid/nostr/event-verify`

Job: NIP-01 id hash + Schnorr check on a **bare** event JSON. Response omits `content`, `tags`, and `sig`.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/nostr/event-verify \
  --price 100 --method POST \
  --json '{"id":"<64 hex>","pubkey":"<64 hex>","created_at":1,"kind":1,"tags":[],"content":"","sig":"<128 hex>"}'
```

### POST `/paid/nostr/npub-decode`

Job: NIP-19 bech32 → `type` + hex (`npub` / `note` / `nprofile` / `nevent`). **`nsec` is rejected** (no secret hex). Do not echo `entity`.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/nostr/npub-decode \
  --price 100 --method POST \
  --json '{"entity":"npub1..."}'
```

## Security

### POST `/paid/security/l402-challenge-inspect`

Job: fetch one `https` URL and read its L402 or LSAT challenge. Returns `valid_challenge`, `price_sats`, `expiry` (unix seconds), `payee_pubkey` when the invoice has one, `network` (`mainnet`, `testnet`, `signet`, or `regtest`), and a short `reason` when the challenge is missing or bad. Does **not** pay. Does **not** return the macaroon or the raw invoice. **100 sats**. 402index category: `security`.

Non-HTTPS URLs are rejected. At most one redirect. Private, loopback, and link-local addresses are not contacted.

```bash
uv run python examples/l402_pay.py \
  --url https://agent-bitcoin.net/paid/security/l402-challenge-inspect \
  --price 100 --method POST \
  --json '{"url":"https://agent-bitcoin.net/paid/finance/btc-usd"}'
```

## What this is not

- Not a **mempool.space** replacement or explorer
- Not an **FX oracle** or CoinGecko substitute (`btc-usd` is one public pass-through)
- Not **Terminal / RTL** (path-hint is one QueryRoutes scalar, not a route UI)
- Not **Damus** or a Nostr client (no relay on these two tools)
- Not a world-open **8081** (public HTTPS is port **443**)
- Do not put Aperture in front of `/pay`, `/invoices`, or `/balance`
