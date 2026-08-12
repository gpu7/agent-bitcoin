# NIP-44 + public-relay NWC (Mac ↔ AWS)

**Status:** Implementation in progress — NIP-44 v2 required for new NWC connections; public relays only; payments via NWC with existing latches.
**Date:** 2026-08-12
**Related:** [nwc-automatic-wallets.md](./nwc-automatic-wallets.md) · [m3-production-swarm.md](./m3-production-swarm.md) · [NIP-44](https://github.com/nostr-protocol/nips/blob/master/44.md) · [NIP-47](https://nips.nostr.com/47)

---

## Goal

Production-grade payload encryption and **dual-host** NWC over **public** Nostr relays:

```text
Mac NWCClient ──nip44_v2──► kind 23194 ──►  wss://relay.damus.io
        ▲                                    wss://nos.lol
        └──────── kind 23195 ◄───────────────┤
                                             │
AWS NWCService (long-lived SUB 23194) ◄──────┘
        │  AGENT_BITCOIN_NWC_* + 2k mainnet budget
        ▼
   LND (docker) agent-payment-decision-lnd-mainnet
```

## Policy

| Item | Rule |
|------|------|
| Relays | **Public only** (defaults: nos.lol, primal, damus); no private relay required |
| New NWC payloads | **`nip44_v2`** |
| NIP-04 | Lab fallback only if `AGENT_BITCOIN_NWC_ALLOW_NIP04=1` |
| Payments | NWC methods; mainnet max **2k**; multi-latch |
| Autopay / Autoloop | **Off** |
| Mainnet `--pay` | Operator + `--yes-mainnet` only |

## Operators

**AWS** (long-lived listener):

```bash
export AGENT_BITCOIN_NWC_ENABLE=1
# mainnet also: LND_NETWORK=mainnet + ALLOW_MAINNET + NWC_ALLOW_MAINNET
export LND_TRANSPORT=docker
export LND_CONTAINER=agent-payment-decision-lnd-mainnet
uv run --python 3.12 python examples/nwc_relay_service.py
# copy printed NWC URI to Mac — never commit
# wait until you see: [aws] subscribed, polling ['wss://…']
```

Per-relay connect is ~2s (hard skip after ~3.5s). Do **not** wait minutes on `connecting …`. Mac `get_info` waits **30s** then exits.

Expected AWS logs:

```text
[aws] connecting wss://nos.lol …
[aws] ok wss://nos.lol
[aws] connecting wss://relay.primal.net …
[aws] skip wss://relay.primal.net: connect timeout or error   # optional
[aws] registered wss://nos.lol (close_on_eose=False)
[aws] subscribed, polling ['wss://nos.lol']
[aws] request from abcd1234…     # after each Mac call (get_info, get_balance, …)
[aws] queued 23195 on live relays
```

**Mac** (client):

```bash
export NWC_URL='nostr+walletconnect://…'
uv run --python 3.12 python examples/nwc_relay_client.py --method get_info
# pay only with a go:
# uv run --python 3.12 python examples/nwc_relay_client.py --method pay --amount 2000 --yes-mainnet
```

## Limitations (NIP-44)

No forward secrecy; relay metadata leaks (`created_at`, IPs). Stolen URI still bounded by NWC budgets.
