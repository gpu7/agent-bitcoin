# ADR: Nostr identity for agent swarms (Phase A)

**Status:** Accepted — Phase A/B complete (regtest + **signet** live); Phase C hardening PoC available
**Date:** 2026-07-29 (signet Phase B exercised 2026-08-02)
**Audience:** Operators and developers.
**Agents / SDK payment path:** unchanged. Nostr is **additive** identity/transport, not a replacement for LND, Autoloop, or the FastAPI backend.

**Related:** [liquidity-automation.md](./liquidity-automation.md) · [SECURITY.md](../SECURITY.md)
**Examples:**
- [nostr_agent_poc.py](../examples/nostr_agent_poc.py) (Phase A)
- [nostr_phase_b_payment.py](../examples/nostr_phase_b_payment.py) (Phase B)
- [nostr_phase_c_signer.py](../examples/nostr_phase_c_signer.py) (Phase C local policy signer)

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
   - **Phase A:** keys, encrypted local storage, signed notes. **No LND.**
   - **Phase B:** coordinate invoice/pay between dual LND nodes using **signed Nostr-style events** as the request channel; payments still via existing `LNDClient` / `lncli`.
   - **Phase C:** harden key custody — local **policy signer** (NIP-46-inspired); roadmap for full NIP-46 bunker, NIP-17 DMs, NIP-47 NWC, MPC.

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

## Phase B scope (in / out)

| In | Out |
|----|-----|
| Signed `pay_request` / `invoice_offer` / `payment_result` messages | Replacing FastAPI or Autoloop |
| **File bus** of signed events (reliable lab path) | Depending only on public relays |
| `addinvoice` / `payinvoice` via existing Docker LND | Merging pay into `PaymentDecisionAgent` |
| Dual-host: Mac payer LND pays → AWS invoice LND receives (regtest or signet) | NWC / zaps |
| Optional `--decide` before pay | Mainnet |

Default container names differ by network (override via env):

| Network | Payer container (Mac) | Invoice container (AWS) |
|---------|----------------------|-------------------------|
| regtest | `agent-bitcoin-lnd` | `agent-payment-decision-lnd` |
| signet | `agent-bitcoin-lnd-signet` | `agent-payment-decision-lnd-signet` |

Set `LND_NETWORK=signet` (or `regtest`) so `LNDClient` / `lncli` use the right chain. See [signet.md](./signet.md) for the full signet dual-host runbook.

### Phase B message flow

```text
Alice (payer agent, Nostr key)          Bob (invoice agent, Nostr key)
        |                                         |
        | 1. signed pay_request                   |
        |---------------------------------------->|
        |                                         | 2. LND addinvoice
        | 3. signed invoice_offer (bolt11)        |
        |<----------------------------------------|
        | 4. optional PaymentDecisionAgent        |
        | 5. LND payinvoice                       |
        | 6. signed payment_result                |
        |---------------------------------------->|
```

Default lab mapping (receive-heavy AWS agent; **regtest** names shown — use `*-signet` + `LND_NETWORK=signet` on signet):

| Role | Nostr agent | LND container (regtest) | Typical host |
|------|-------------|-------------------------|--------------|
| Payer | `alice` | `agent-bitcoin-lnd` | Mac |
| Invoice | `bob` | `agent-payment-decision-lnd` | AWS |

Coordination is a **bus directory** of signed event JSON files (`.nostr-poc/bus/`). Copy that directory between hosts (scp, USB, shared folder). Public relays remain optional and often filter new keys.

---

## Key management (roadmap)

| Stage | Approach | Use when |
|-------|----------|----------|
| **Phase A/B** | Encrypted local file; agent process may load nsec to sign | Lab / low value |
| **Phase C PoC** | **Local policy signer** — only signer process loads nsec; agent uses Unix socket | Hardening step |
| **Next** | Full NIP-46 bunker (possibly remote host / TEE) | Long-lived / higher trust |
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
- Phase B binds Nostr coordination to existing dual-LND (AWS + Mac) on **regtest or signet** without redesigning LND topology.
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

## How to run Phase B PoC

Prerequisites: AWS + Mac stack up, wallets unlocked, **channel active**, Python 3.12 + `.[nostr]` on **both** hosts that run a role. Use the **same** `NOSTR_PASSPHRASE` and share the `.nostr-poc` tree (or at least `bus/` + both encrypted keys if each host signs).

```bash
uv venv -p 3.12 .venv-nostr
uv pip install --python .venv-nostr/bin/python -e '.[nostr]'
export NOSTR_PASSPHRASE='use-a-strong-passphrase'
export NOSTR_POC_DIR=./.nostr-poc

# --- Protocol dry-run (no LND; any single machine) ---
.venv-nostr/bin/python examples/nostr_phase_b_payment.py --force-new-keys request --amount 5000
.venv-nostr/bin/python examples/nostr_phase_b_payment.py --force-new-keys invoice --dry-run
.venv-nostr/bin/python examples/nostr_phase_b_payment.py pay --dry-run
.venv-nostr/bin/python examples/nostr_phase_b_payment.py status

# --- Live dual-host (example amounts must be >= MIN_PAYMENT_SATS, default 2000) ---
# Mac (payer has local outbound):
.venv-nostr/bin/python examples/nostr_phase_b_payment.py request --amount 5000 --memo 'nostr-b'
# scp -r .nostr-poc  ubuntu@AWS:~/agent-bitcoin/

# AWS (agent receives):
LND_INVOICE_CONTAINER=agent-payment-decision-lnd \
  .venv-nostr/bin/python examples/nostr_phase_b_payment.py invoice
# scp offer/result bus files back to Mac

# Mac (pay):
LND_PAYER_CONTAINER=agent-bitcoin-lnd \
  .venv-nostr/bin/python examples/nostr_phase_b_payment.py pay
# optional: add --decide
```

---

## Success criteria (Phase B)

- [x] Signed `pay_request` → `invoice_offer` → `payment_result` over file bus
- [x] Dry-run path without LND
- [x] Live: invoice on one LND, pay on the other, channel settles (**regtest**)
- [x] Live: same protocol on **signet** dual-node (Mac pay → AWS invoice; 2026-08-02, 2000 sats)
- [x] Decision agent remains optional gate only (`--decide`)

Signet operator steps: [signet.md — Nostr Phase B on signet](./signet.md#nostr-phase-b-on-signet-same-as-regtest).

---

## Phase C — hardening (key custody + policy)

**Question:** How do we keep agent identities safe when agents run long-term and may control real value?

### What Phase C delivers now (PoC)

| In | Out (roadmap / later) |
|----|------------------------|
| Local **policy signer** process holds nsec | Full wire-compatible **NIP-46** bunker over Nostr |
| Agent client signs via **Unix socket** only | **MPC** threshold signing |
| Policy: allowed kinds, rate limit, required tags, payload `type` allow-list | **NIP-17** private DMs |
| One-shot `demo` self-test | **NIP-47 NWC** wallet service next to LND |
| Localhost / same-host only | Remote signer over network / TEE |

Architecture:

```text
  Agent runtime (no nsec)
        |  JSON-lines over Unix socket
        v
  Policy signer process
        |  passphrase unlock once
        v
  Encrypted nsec on disk (.nostr-poc/*.enc.json)
```

### How to run Phase C PoC

```bash
uv venv -p 3.12 .venv-nostr
uv pip install --python .venv-nostr/bin/python -e '.[nostr]'
export NOSTR_PASSPHRASE='use-a-strong-passphrase'
export NOSTR_POC_DIR=./.nostr-poc

# One-shot: signer + client (client never loads nsec)
.venv-nostr/bin/python examples/nostr_phase_c_signer.py demo --agent alice

# Or two terminals:
# T1 — holds the key
.venv-nostr/bin/python examples/nostr_phase_c_signer.py serve --agent alice
# T2 — agent-like client
.venv-nostr/bin/python examples/nostr_phase_c_signer.py get-pubkey --agent alice
.venv-nostr/bin/python examples/nostr_phase_c_signer.py sign --agent alice --type phase_c_demo
.venv-nostr/bin/python examples/nostr_phase_c_signer.py deny-demo --agent alice
```

Policy file: [examples/nostr_phase_c_policy.json](../examples/nostr_phase_c_policy.json).

### Phase C roadmap (not in this PoC)

1. **NIP-46** — interoperable remote signer (“bunker”) instead of custom Unix protocol
2. **NIP-17** — modern private DMs for inter-agent secrets (not NIP-04)
3. **NIP-47 NWC** — limited Lightning permissions for agents (no full admin macaroon in agent process)
4. **MPC / TEE** — for high-value autonomous keys
5. Wire Phase B `pay`/`request` to call the signer instead of `load_or_create_agent` in the agent process

### Success criteria (Phase C PoC)

- [x] Signer process alone loads nsec
- [x] Client obtains pubkey + signed event without nsec
- [x] Policy can deny disallowed payload types
- [ ] Full NIP-46 / NIP-17 / NWC (roadmap)

---

## Non-goals (explicit)

- Replacing `AGENT_BITCOIN_API_KEY` HTTP auth
- Merging Nostr into `PaymentDecisionAgent` payment execution
- Mainnet Nostr + Lightning agent economies without further design
- Claiming NIP-04 DMs as production-grade privacy (prefer NIP-17 later)
- Public-relay reliability as a Phase B/C requirement (file bus + local signer are lab paths)
- Claiming the Phase C Unix signer is a complete NIP-46 implementation
