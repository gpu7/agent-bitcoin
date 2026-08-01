# Agent-Bitcoin Documentation

**Lightning Bitcoin payments for autonomous AI Agents.**

## Primary docs

| Doc | Audience |
|-----|----------|
| [README.md](../README.md) | Product overview (public hub) |
| [SDK.md](../SDK.md) | SDK / app / agent developers |
| [backend.md](./backend.md) | Operators: AWS + Mac regtest, LND, channels |
| [signet.md](./signet.md) | Operators: run agent-bitcoin on Bitcoin **signet** |
| [mainnet-pilot.md](./mainnet-pilot.md) | **Phase 0:** mainnet pilot scope (topology B) — not go-live |
| [lnd-client.md](./lnd-client.md) | **Phase 1:** LND transports (`docker` vs `grpc`) |
| [liquidity-automation.md](./liquidity-automation.md) | **Simple story:** channel health + Autoloop Phases 1–3 |
| [loop-autoloop.md](./loop-autoloop.md) | Phase 2 deep dive: Loop Autoloop, agent-loopd, ops |
| [nostr-agent-identity.md](./nostr-agent-identity.md) | ADR: Nostr agent identity Phases A–C (keys, pay coord, policy signer) |
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
5. Mainnet readiness scope (later) → [mainnet-pilot.md](./mainnet-pilot.md)

## Repository

- GitHub: https://github.com/gpu7/agent-bitcoin
- TestPyPI: https://test.pypi.org/project/agent-bitcoin/
- License: MIT
