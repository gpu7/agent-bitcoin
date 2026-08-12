# Agent-Bitcoin Documentation

**Lightning Bitcoin payments for autonomous AI Agents.**

## Primary docs

| Doc | Audience |
|-----|----------|
| [README.md](../README.md) | Product overview (public hub) |
| [SDK.md](../SDK.md) | SDK / app / agent developers |
| [backend.md](./backend.md) | Operators: AWS + Mac regtest, LND, channels |
| [signet.md](./signet.md) | Operators: run agent-bitcoin on Bitcoin **signet** |
| [mainnet-pilot.md](./mainnet-pilot.md) | **Phases 0–8:** mainnet pilot scope + **ops complete** (≤50k dual-node; N=5 pays) |
| [mainnet-infra.md](./mainnet-infra.md) | Mainnet compose, ports, SG, volumes (infra for Phase 8) |
| [lnd-client.md](./lnd-client.md) | **Phase 1:** LND transports (`docker` vs `grpc`) |
| [lnd-backup-restore.md](./lnd-backup-restore.md) | **Phase 3:** SCB export, volume backup, restore drill |
| [daily-ops-signet.md](./daily-ops-signet.md) | **Phase 4:** daily start/stop + `check-signet-health.sh` |
| [liquidity-topology-b.md](./liquidity-topology-b.md) | **Phase 5:** dual-node channel open / rebalance / close SOP |
| [security-hardening.md](./security-hardening.md) | **Phase 6:** secrets, SG, backend bind, mainnet vs lab |
| [signet-dress-rehearsal.md](./signet-dress-rehearsal.md) | **Phase 7:** signet “as if mainnet” checklist |
| [liquidity-automation.md](./liquidity-automation.md) | **Simple story:** channel health + Autoloop Phases 1–3 |
| [loop-autoloop.md](./loop-autoloop.md) | Phase 2 deep dive: Loop Autoloop, agent-loopd, ops (regtest) |
| [loop-multi-network.md](./loop-multi-network.md) | Install loopd on regtest / signet / mainnet (Autoloop off on mainnet until go) |
| [public-routing-loop.md](./public-routing-loop.md) | **Topology A′:** public channels + first Loop Out **SUCCESS**; capital **HOLD**; Autoloop off |
| [nostr-agent-identity.md](./nostr-agent-identity.md) | ADR: Nostr A–C; **mainnet M2 Dual 2k SUCCESS** |
| [nwc-automatic-wallets.md](./nwc-automatic-wallets.md) | **NWC / NIP-47:** automatic wallets (client+service+decision flow); mainnet invoice smoke closed |
| [m3-production-swarm.md](./m3-production-swarm.md) | **M3 v1:** relays, NIP-46, NIP-17, swarm registry (autopay still off) |
| [nip44-nwc-relays.md](./nip44-nwc-relays.md) | **NIP-44** + public-relay NWC (Mac listener / AWS service) |
| [setup.md](./setup.md) | Short setup pointers |

## Also

- [CHANGELOG.md](../CHANGELOG.md)
- [SECURITY.md](../SECURITY.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [examples/](../examples/) — runnable scripts (see SDK.md)

## Getting started

1. Install and use the library → [SDK.md](../SDK.md)
2. Run the regtest stack → [backend.md](./backend.md)
3. Channel health and Autoloop (operators) → [liquidity-automation.md](./liquidity-automation.md)
4. Signet (after regtest) → [signet.md](./signet.md)
5. Mainnet pilot (ops complete; limits still tight) → [mainnet-pilot.md](./mainnet-pilot.md)
6. Public routing + Loop (A′ executed; capital HOLD) → [public-routing-loop.md](./public-routing-loop.md)
7. Automatic wallets (NWC design) → [nwc-automatic-wallets.md](./nwc-automatic-wallets.md)

## Repository

- GitHub: https://github.com/gpu7/agent-bitcoin
- TestPyPI: https://test.pypi.org/project/agent-bitcoin/
- License: MIT
