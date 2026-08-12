## Ops/docs — Nostr mainnet Stage 2 Phase C (2026-08-12)

### Done

- Phase C local policy signer **PASS** for alice + bob against `.nostr-poc-mainnet` keys (client never loaded nsec; policy deny verified)
- CLI: `nostr_phase_c_signer.py` accepts `--agent` / `--dir` before **or** after the subcommand
- M2 pay still deferred; Dual path reserved

---

## Ops/docs — Nostr mainnet M1 identity (2026-08-12)

### Done

- **Stage 0 go:** M1 only; Dual path reserved for later M2; capital HOLD unchanged
- **M1:** dedicated alice/bob keys under gitignored `.nostr-poc-mainnet/`; Phase A offline crypto **PASS**
- `.gitignore` covers `.nostr-poc-mainnet/`; no nsec/passphrase in git
- ADR + pilot post-pilot table record M1 complete; M2/M3 still deferred

---

## Docs — Nostr mainnet process (not yet executed) (2026-08-11)

### Documented

- Confirmed Nostr Phase A/B live on **regtest + signet only**; mainnet identity/pay and NWC remain **frozen** without a new go
- Step-by-step mainnet process (M1 identity → M2 2k smoke → M3 roadmap) in [docs/nostr-agent-identity.md](docs/nostr-agent-identity.md)
- Cross-links in [docs/mainnet-pilot.md](docs/mainnet-pilot.md) and [docs/index.md](docs/index.md)
- Phase B example prints `LND_NETWORK` and mainnet warning; live mainnet still gated by `AGENT_BITCOIN_ALLOW_MAINNET=1` in `LNDClient`

---

## Docs — topology A′ Loop Out complete + capital HOLD (2026-08-11)

### Documented

- First mainnet **Loop Out SUCCESS** (250k; ~841 sats total cost) and dual **public** channels (ACINQ + LNBiG, 500k each)
- **Capital intent: HOLD as-is** — no further opens, deposits, or swaps without a new go; Autoloop remains **off**
- Updated [docs/public-routing-loop.md](docs/public-routing-loop.md): execution log, P0–P3 checkmarks, steady-state HOLD ops
- Updated [docs/mainnet-pilot.md](docs/mainnet-pilot.md): post-pilot decision table + cross-links
- [docs/index.md](docs/index.md) index line for A′ status

### Ops note (not automated)

- L402 `timeout_seconds` fix remains in [docker/loop-timeout-fix/](docker/loop-timeout-fix/) (merged PR #56)

---

## Docs — public routing + Loop design (2026-08-10)

### Added

- [docs/public-routing-loop.md](docs/public-routing-loop.md): post-pilot **topology A′** — single AWS LND opens **public** channels to external peers; **loopd** manages liquidity; Mac not permanent partner; no second AWS agent required
- P0–P4 operator checklist (policy, harden, open, Loop, product integration)

### Changed

- [docs/mainnet-pilot.md](docs/mainnet-pilot.md): cooperative close in pilot log; post-pilot table points at public-routing design
- Cross-links in index, liquidity-automation, loop-multi-network, loop-autoloop

---

## Docs — mainnet Phase 8 ops pilot (2026-08-10)

### Documented

- **Phase 8 ops complete:** dual-node mainnet private channel (43k sats), fund ≤50k, **N=5** human-attended Lightning pays via `lncli`
- Updated [docs/mainnet-pilot.md](docs/mainnet-pilot.md): pilot log, BIP-110 freeze historical, **pilot-complete checklist**, post-pilot non-goals
- Aligned [docs/mainnet-infra.md](docs/mainnet-infra.md), [docs/loop-multi-network.md](docs/loop-multi-network.md), [docs/liquidity-topology-b.md](docs/liquidity-topology-b.md), [docs/index.md](docs/index.md), README

### Still out of scope (unchanged policy)

- Mainnet Autoloop / raising loss budget / autonomous autopay without a new go decision
- SDK mainnet pay path remains optional post-pilot validation

---

## [23.1.0] - 2026-07-14

### Major Changes
- **Split architecture support**: AWS backend (`agent-payment-decision-lnd` + `bitcoind`) + Mac counterparty node
- **Persistent chain mode**: New `startup-aws.sh` (no aggressive reset) and `startup-aws-reset.sh` for full reset when needed
- **Improved startup scripts**: `startup-mac.sh` and `shutdown-mac.sh` for local testing
- **Better Docker Compose separation**: `docker-compose.regtest.aws.yml` and `docker-compose.regtest.mac.yml`

### Added
- Channel opening and Lightning payments between Mac and AWS nodes
- Automatic wallet detection (create vs unlock)
- Pre-warming and mining logic for faster startup
- TestPyPI publishing workflow

### Fixed
- Port binding and firewall issues on AWS (18443/9735)
- LND sync and "block height out of range" errors
- Wallet unlock reliability across restarts
- Docker service name and volume management

### Dependencies
- Updated to support latest Lightning Labs LND (v0.17.5-beta / v0.18.5-beta)

[Compare with previous version](https://github.com/gpu7/agent-bitcoin/compare/23.0.0...23.1.0)
