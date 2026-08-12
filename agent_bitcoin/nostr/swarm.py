"""Local multi-agent swarm registry (M3).

No global directory. Operators share a JSON registry (scp/rsync) or
publish kind-0 / kind-1 helpers for discovery notes.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class SwarmAgent:
    name: str
    npub: str
    role: str  # payer | invoice | wallet | signer | other
    relays: list[str] = field(default_factory=list)
    nwc_hint: str = ""  # never store full secret URI in shared files if avoidable
    note: str = ""

    def profile_content(self) -> str:
        """Kind-0 style profile JSON (no secrets)."""
        return json.dumps(
            {
                "name": self.name,
                "about": f"agent-bitcoin swarm role={self.role}",
                "nip05": "",
                "agent_bitcoin": {
                    "role": self.role,
                    "relays": self.relays,
                    "note": self.note,
                },
            },
            separators=(",", ":"),
        )

    def coord_note(self, message: str) -> dict[str, Any]:
        return {
            "kind": 1,
            "created_at": int(time.time()),
            "tags": [
                ["t", "agent-bitcoin-swarm"],
                ["client", "agent-bitcoin-m3"],
            ],
            "content": f"[{self.name}/{self.role}] {message}",
        }


class SwarmRegistry:
    def __init__(self, agents: Iterable[SwarmAgent] | None = None) -> None:
        self._by_name: dict[str, SwarmAgent] = {}
        for a in agents or []:
            self.register(a)

    def register(self, agent: SwarmAgent) -> None:
        self._by_name[agent.name] = agent

    def get(self, name: str) -> SwarmAgent | None:
        return self._by_name.get(name)

    def list(self, *, role: str | None = None) -> list[SwarmAgent]:
        vals = list(self._by_name.values())
        if role:
            return [a for a in vals if a.role == role]
        return vals

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "v": 1,
            "agents": [
                {k: v for k, v in asdict(a).items() if k != "nwc_hint" or not v}
                for a in self.list()
            ],
        }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.write_text(json.dumps(self.to_public_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> SwarmRegistry:
        data = json.loads(Path(path).read_text())
        agents = [SwarmAgent(**row) for row in data.get("agents") or []]
        return cls(agents)
