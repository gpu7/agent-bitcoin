"""Plan additive Mac /32 SG updates. Never 0.0.0.0/0; never 10009."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

ADMIN_MARKERS = (
    "admin/mac",
    "ssh admin",
    "agent bitcoin api",
    "bitcoind rpc mac",
    "zmq blocks mac",
    "zmq txs mac",
)


def is_client_pack(description: str) -> bool:
    return "client pack" in (description or "").lower()


def is_mac_admin(description: str) -> bool:
    d = (description or "").lower()
    if is_client_pack(d):
        return False
    if any(m in d for m in ADMIN_MARKERS):
        return True
    return "lnd p2p" in d and "mac" in d


def _ranges_for_port(sg_doc: dict[str, Any], port: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for g in sg_doc.get("SecurityGroups") or []:
        for perm in g.get("IpPermissions") or []:
            if perm.get("IpProtocol") != "tcp":
                continue
            fp, tp = perm.get("FromPort"), perm.get("ToPort")
            if fp is None or tp is None:
                continue
            if not (int(fp) <= port <= int(tp)):
                continue
            for r in perm.get("IpRanges") or []:
                cidr = r.get("CidrIp")
                if not cidr:
                    continue
                out.append((cidr, r.get("Description") or ""))
    return out


def plan(
    sg_doc: dict[str, Any],
    *,
    ports: set[int],
    my_cidr: str,
    keep_world_p2p: bool = False,
) -> dict[str, Any]:
    if 10009 in ports:
        raise ValueError("refuse port 10009")
    if my_cidr.strip() == "0.0.0.0/0":
        raise ValueError("refuse authorizing 0.0.0.0/0")

    to_add: list[int] = []
    to_revoke: list[dict[str, Any]] = []
    remaining: dict[int, list[dict[str, str]]] = defaultdict(list)

    for port in sorted(ports):
        rows = _ranges_for_port(sg_doc, port)
        cidrs = {c for c, _d in rows}
        if my_cidr not in cidrs:
            to_add.append(port)
        keep: list[tuple[str, str]] = []
        for cidr, desc in rows:
            if cidr == my_cidr:
                keep.append((cidr, desc))
                continue
            if keep_world_p2p and port in (9735, 19735) and cidr == "0.0.0.0/0":
                keep.append((cidr, desc))
                continue
            if is_client_pack(desc):
                keep.append((cidr, desc))
                continue
            if is_mac_admin(desc) and cidr != my_cidr:
                to_revoke.append({"port": port, "cidr": cidr, "description": desc})
                continue
            keep.append((cidr, desc))
        if my_cidr not in {c for c, _ in keep}:
            keep.append((my_cidr, "agent-bitcoin admin/Mac"))
        remaining[port] = [{"cidr": c, "description": d} for c, d in sorted(keep)]

    return {
        "add": to_add,
        "revoke": to_revoke,
        "remaining": {
            "8081": remaining.get(8081, []),
            "9735": remaining.get(9735, []),
        },
    }
