"""Offline SG planner: add Mac /32, keep client pack. No live AWS."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.sg_ingress_plan import plan

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "update-aws-sg-my-ip.sh"


def _sg(*ranges: tuple[int, str, str]) -> dict:
    perms = []
    for port, cidr, desc in ranges:
        perms.append(
            {
                "IpProtocol": "tcp",
                "FromPort": port,
                "ToPort": port,
                "IpRanges": [{"CidrIp": cidr, "Description": desc}],
            }
        )
    return {"SecurityGroups": [{"IpPermissions": perms}]}


def test_keeps_client_pack_revokes_old_mac() -> None:
    doc = _sg(
        (8081, "1.2.3.4/32", "agent-bitcoin admin/Mac"),
        (8081, "73.14.70.17/32", "l402 client pack 8081"),
        (9735, "1.2.3.4/32", "LND P2P regtest Mac"),
        (9735, "73.14.70.17/32", "l402 client pack 9735"),
        (10009, "9.9.9.9/32", "should never appear"),
    )
    out = plan(
        doc,
        ports={8081, 9735},
        my_cidr="5.6.7.8/32",
    )
    assert out["add"] == [8081, 9735]
    rev = {(r["port"], r["cidr"]) for r in out["revoke"]}
    assert rev == {(8081, "1.2.3.4/32"), (9735, "1.2.3.4/32")}
    rem_8081 = {r["cidr"] for r in out["remaining"]["8081"]}
    rem_9735 = {r["cidr"] for r in out["remaining"]["9735"]}
    assert "73.14.70.17/32" in rem_8081
    assert "73.14.70.17/32" in rem_9735
    assert "5.6.7.8/32" in rem_8081
    assert "1.2.3.4/32" not in rem_8081
    assert all(r["port"] != 10009 for r in out["revoke"])
    assert 10009 not in out["add"]


def test_refuse_10009() -> None:
    with pytest.raises(ValueError, match="10009"):
        plan(_sg(), ports={8081, 10009}, my_cidr="1.1.1.1/32")


def test_refuse_world_open_add() -> None:
    with pytest.raises(ValueError, match="0.0.0.0/0"):
        plan(_sg(), ports={8081}, my_cidr="0.0.0.0/0")


def test_unnamed_cidr_kept() -> None:
    doc = _sg((8081, "8.8.8.8/32", ""))
    out = plan(doc, ports={8081}, my_cidr="1.1.1.1/32")
    assert out["add"] == [8081]
    assert out["revoke"] == []
    assert {r["cidr"] for r in out["remaining"]["8081"]} == {
        "8.8.8.8/32",
        "1.1.1.1/32",
    }


def test_dry_run_help_exits_zero() -> None:
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--dry-run" in proc.stdout
    assert "additive" in proc.stdout.lower() or "client pack" in proc.stdout.lower()
