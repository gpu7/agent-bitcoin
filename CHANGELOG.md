## Ops — NWC mainnet invoice smoke PASS; session closed (2026-08-12)

### Documented

- AWS live N6 invoice path **PASS** (`nwc_mainnet_smoke.py --yes-mainnet --amount 2000`)
- Payment hash `7afc7a2b0c0098a61aaa64ed4b7d433424faa3996ccca70db4bafdb7f47c28e6`
- Operator closed at invoice-only (no `--pay`); latches unset
- Further mainnet NWC pays require a **new written go**

---

## Feat — NWC mainnet tight-budget go (N6) (2026-08-12)

### Added

- `AGENT_BITCOIN_NWC_ALLOW_MAINNET` + `assert_nwc_network_allowed()` (requires enable + LND mainnet latch)
- Mainnet NWC default max **2,000 sats** (`DEFAULT_NWC_MAINNET_MAX_SATS` / `NWC_MAX_PAYMENT_SATS`)
- `examples/nwc_mainnet_smoke.py` (`--yes-mainnet`, optional `--pay`)
- Tests: `tests/test_nwc_mainnet_policy.py`

### Policy

- Operator go for human-attended mainnet NWC smoke only; unset latches after session
- Autoloop remains off

---

## Feat — NWC decision → pay product path (N5) (2026-08-12)

### Added

- `agent_bitcoin/nwc/flow.py`: `decision_is_pay`, `nwc_pay_if_approved`, `rule_based_decision`
- `examples/nwc_decision_pay.py`: offline/mock (and optional LLM) gate then NWC settle
- SDK.md section for automatic wallets; tests in `tests/test_nwc_flow.py`
- PaymentDecisionAgent remains recommend-only; execution only via NWC after PAY

---

## Feat — NWC LND service (N4) (2026-08-12)

### Added

- `NWCService`: authorize clients, enforce budgets/enable latch, dispatch to LND
- `create_nwc_service()`, `issue_connection()` → `nostr+walletconnect://` URI
- Offline tests with FakeLND (`tests/test_nwc_service.py`)
- `examples/nwc_regtest_smoke.py` (`--mock` or live docker LND)
- Mainnet still off unless `AGENT_BITCOIN_NWC_ENABLE=1` + separate go

---

## Feat — NWC client + mock bus (N3) (2026-08-12)

### Added

- `NWCClient`: encrypted NIP-47 requests (`get_info`, `get_balance`, `make_invoice`, `pay_invoice`)
- `InMemoryNWCBus` + `attach_mock_wallet` for offline/lab tests (no WebSocket relays)
- NIP-04 payload crypto via pynostr; tests in `tests/test_nwc_client.py`
- No LND-backed service yet (N4)

---

## Feat — NWC scaffold URI + policy (N2) (2026-08-12)

### Added

- `agent_bitcoin/nwc/`: `parse_nwc_uri`, `build_nwc_uri`, v1 method allowlist, amount budgets, `AGENT_BITCOIN_NWC_ENABLE` kill switch
- Offline tests: `tests/test_nwc_uri.py`, `tests/test_nwc_policy.py`
- No client/service wire protocol yet (N3–N4)

---

## Docs — NWC automatic wallets design (2026-08-12)

### Added

- [docs/nwc-automatic-wallets.md](docs/nwc-automatic-wallets.md): NIP-47 automatic wallets ADR — architecture, allowlist, budgets, phases N0–N6
- Policy go: **design + regtest implementation**; mainnet NWC remains frozen
- Cross-links: index, mainnet-pilot, nostr-agent-identity

---

## Ops — Nostr mainnet M2 Dual 2k SUCCESS (2026-08-12)

### Done

- Private dual channel Mac↔AWS: 25k capacity, push 12k to Mac (`b76115f9…1002:0`)
- Phase B signed bus: request → AWS invoice → Mac pay **2000 sats SUCCEEDED** (fee 0)
- Payment hash `f87a39a3597a59859436d6d947e3788cc6e1dc5cea9dc092f0d715a70fa8ca71`
- Phase B defaults `LND_TRANSPORT=docker` to avoid stale signet gRPC `:30009` failures

### Hard stop

- No further Nostr mainnet pays without a new N budget; Autoloop/NWC/autopay remain off

---

## Ops/docs — Nostr mainnet M2 Dual go (2026-08-12)

### Policy

- **M2 go:** Dual path (Mac alice → AWS bob), **2,000 sats** max, human-attended, autopay off
- Capital HOLD still covers deposits / new channels / Loop / Autoloop
- Live pay pending Stage 3 (Mac wallet unlock + outbound path) and Stage 5 dry-run

### Documented

- Expanded dual-host runbook Stages 3–6 in [docs/nostr-agent-identity.md](docs/nostr-agent-identity.md)

---

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
