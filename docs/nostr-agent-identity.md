# ADR: Nostr identity for agent swarms (Phase A)

**Status:** Accepted for PoC (Phase A)
**Date:** 2026-07-28
**Audience:** Operators and developers.
**Agents / SDK payment path:** unchanged. Nostr is **additive** identity/transport, not a replacement for LND, Autoloop, or the FastAPI backend.

**Related:** [liquidity-automation.md](./liquidity-automation.md) (separate track: channel health / Loop) · [SECURITY.md](../SECURITY.md) · example [examples/nostr_agent_poc.py](../examples/nostr_agent_poc.py)

---

## Context

We plan an **open, multi-operator, long-lived, economically active** autonomous agent swarm. Each agent needs:

- A **sovereign, persistent identity** (not a shared platform account)
- **Permissionless discovery** and signed coordination
- A path to **Lightning-native value** under that identity (later)
- **Censorship-resistant** publication (multi-relay)

**Nostr** provides secp256k1 keypair identity, signed events, independent relays, and Lightning-oriented NIPs (zaps, NWC). That matches swarm goals better than UUID labels alone.

**agent-bitcoin today** already provides:

- LND-backed invoice/pay (`agent-payment-decision-lnd`, optional Mac counterparty)
- `PaymentDecisionAgent` (PAY / REJECT / CONFIRM — **never executes** payments)
- HTTP backend with API key
- Phase 1–2 liquidity monitoring and Autoloop (operator infrastructure)

Gaps: no per-agent public identity, no decentralized discovery/messaging, multi-agent coordination is out-of-band.

---

## Decision

1. **Keep current infrastructure fully intact.** Nostr is layered **on top**.
2. **Per-agent Nostr accounts** (one secp256k1 keypair per agent) for open swarm work.
3. **Do not** fold Nostr into `PaymentDecisionAgent` execution. Decision remains a gatekeeper; payment stays on LND / future NWC after PAY.
4. **Do not** replace operator LND peer scripts or Autoloop with Nostr.
5. **Phase delivery:**
   - **Phase A (this ADR + PoC):** keys, encrypted local storage, relay pub/sub, signed notes (and optional NIP-04 DMs). **No LND.**
   - **Phase B (later):** coordinate invoice/pay between `agent-payment-decision-lnd` and `agent-bitcoin-lnd` using Nostr as the request channel; still use existing payment APIs.
   - **Phase C (later):** harden key management (NIP-46 remote signer, then MPC if needed); prefer NIP-17 DMs over NIP-04; optional NIP-47 NWC.

---

## Phase A scope (in / out)

| In | Out |
|----|-----|
| Generate agent keypairs with CSPRNG | LND, invoices, Autoloop |
| Encrypt `nsec` at rest (passphrase / Fernet) | NIP-46 / MPC |
| Connect to public or self-hosted relays | Changing FastAPI auth model |
| Kind 0 profile + kind 1 coordination notes | Mainnet requirements |
| Optional experimental NIP-04 DM | Production key custody |

---

## Key management (roadmap)

| Stage | Approach | Use when |
|-------|----------|----------|
| **PoC (now)** | Encrypted local file or secrets manager; load only for signing | Experiments, low value |
| **Next** | NIP-46 remote signer (“bunker”); agent never holds raw `nsec` | Long-lived / higher trust |
| **High value** | Threshold / MPC shares | Real economic agents |
| **Swarms** | HD master seed offline; derive per-agent keys | Many agents under one operator |

**Rules:** never commit `nsec` / encrypted blobs with weak passwords; use CSPRNG (`secrets`); zero keys from memory where practical; treat Lightning keys with equal or greater care (prefer NWC so agents do not hold full LND admin credentials).

---

## UUID vs Nostr

| Need | Prefer |
|------|--------|
| Uniqueness inside a closed, trusted bus | UUID is enough |
| Prove ownership, public reputation, multi-operator discovery, autonomous value | **Nostr (or other pubkey identity)** |

This project’s stated swarm goals imply **Nostr (or equivalent crypto identity)**, not UUID alone. UUID may still be used for internal bookkeeping.

---

## Alternatives considered

| Option | Role vs Nostr |
|--------|----------------|
| **libp2p** | Stronger pure P2P; more engineering; no native Lightning/zaps |
| **DIDs + DIDComm / Aries** | Rich credentials; heavier |
| **Google A2A** | Agent interop focus; weaker as a censorship-resistant network layer alone |
| **SSB** | Censorship-resistant gossip; smaller ecosystem |

**Choice for PoC:** Nostr — simple, Lightning-adjacent, multi-relay, fits open economic swarms.

---

## Consequences

- New optional dependency / example path (`pynostr`); core SDK remains LND-focused.
- Operators may run or choose relays; reliability and spam resistance are operational concerns.
- Phase B will bind Nostr coordination to existing dual-LND regtest (AWS + Mac) without redesigning LND topology.
- Public relays see kind 1 content; do not put secrets or full production BOLT11s in public notes during experiments.

---

## How to run Phase A PoC

`pynostr` pulls in `coincurve`, which currently needs a **Python 3.10–3.12** environment with binary wheels (3.14 may fail to build).

```bash
# From repo root — recommended isolated venv
uv venv -p 3.12 .venv-nostr
uv pip install --python .venv-nostr/bin/python -e '.[nostr]'
# or: uv pip install --python .venv-nostr/bin/python 'pynostr[websocket-client]' cryptography

export NOSTR_PASSPHRASE='use-a-strong-passphrase'

# Minimum Phase A: keygen + encrypt + sign + verify (no network)
.venv-nostr/bin/python examples/nostr_agent_poc.py --offline

# Full: also publish/subscribe via a public relay
.venv-nostr/bin/python examples/nostr_agent_poc.py --relay wss://nos.lol --timeout 15
```

See `examples/nostr_agent_poc.py --help`. Encrypted keys default to `.nostr-poc/` (gitignored).

---

## Success criteria (Phase A)

- [x] ADR documented (this file)
- [x] Example: two agent identities, encrypted `nsec` at rest
- [x] Example: offline sign + verify of a coordination note (no LND)
- [ ] Optional: Agent B retrieves Alice's note from a public relay (network-dependent)
- [x] No LND or payment code required for the PoC to pass

---

## Non-goals (explicit)

- Replacing `AGENT_BITCOIN_API_KEY` HTTP auth in Phase A
- Merging Nostr into `PaymentDecisionAgent.pay`
- Mainnet Nostr + Lightning agent economies
- Claiming NIP-04 DMs as production-grade privacy (prefer NIP-17 later)
