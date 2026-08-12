#!/usr/bin/env python3
"""M3: local swarm registry (no secrets)."""

from __future__ import annotations

from pathlib import Path

from agent_bitcoin.nostr.swarm import SwarmAgent, SwarmRegistry


def main() -> int:
    reg = SwarmRegistry(
        [
            SwarmAgent(
                name="alice",
                npub="npub1u9z2exv9udv2hkhnq5fl8pvlsqvuphmuuxejj2u6g0lf06r8tgsqxl68s8",
                role="payer",
                relays=["wss://relay.damus.io"],
                note="Mac Dual payer",
            ),
            SwarmAgent(
                name="bob",
                npub="npub1jy3ch65u5wvhx4x5s7239k63qtp65h4084fcaq8djgra0dh0erfslusp9f",
                role="invoice",
                note="AWS invoice / NWC service host",
            ),
        ]
    )
    out = Path(".swarm-registry.json")
    reg.save(out)
    print(f"[m3] wrote {out.resolve()} agents={len(reg.list())}")
    for a in reg.list():
        print(f"  {a.name:8} role={a.role:8} {a.npub[:20]}…")
    print("\nRESULT: PASS — swarm registry demo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
