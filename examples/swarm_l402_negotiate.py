#!/usr/bin/env python3
"""Two Nostr agents negotiate who pays one Aperture L402 GET.

Identity: Phase A/B encrypted keys under .nostr-poc/ (same as nostr_phase_b_payment.py).
Transport: file bus (.nostr-poc/bus/). --relay is documented but unused.
Pay: L402Client (same 402 → pay → retry as l402_pay.py). Coded policy picks
the payer; optional Grok only explains.

Mock (any one host): --offline-bus (no sats; fixture bands 3/2/1).
Live: both processes on the Mac; Mac LND agent-bitcoin-lnd* pays AWS Aperture.
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100
Do not live-pay with LND_CONTAINER=agent-payment-decision-lnd* (self-pay).

Engineer path (two terminals):

  export NOSTR_PASSPHRASE='...'
  ./examples/swarm_l402.sh --role alice --offline-bus --no-llm
  ./examples/swarm_l402.sh --role bob --offline-bus --no-llm

See examples/swarm_l402.md
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

_EXAMPLES = Path(__file__).resolve().parent
if str(_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES))

try:
    from pynostr.event import EventKind
except ImportError as e:  # pragma: no cover
    print(
        "Missing pynostr. Use Python 3.12:\n"
        "  uv venv -p 3.12 .venv-nostr\n"
        "  uv pip install --python .venv-nostr/bin/python -e '.[nostr]'\n"
        "  ./examples/swarm_l402.sh --role alice --offline-bus --no-llm\n"
        "Do not use: uv run python  (3.13/3.14 skips .[nostr])\n"
        f"{e}",
        file=sys.stderr,
    )
    sys.exit(1)

from nostr_common import (  # noqa: E402
    load_or_create_agent,
    parse_payload,
    read_bus_event,
    sign_json_event,
    write_bus_event,
)

from agent_bitcoin.nostr.negotiate import (  # noqa: E402
    COORD_TAG,
    DEFAULT_L402_URL,
    DEFAULT_PRICE_SATS,
    choose_payer_n,
    fee_band_summary,
    invoice_id_for_url,
    negotiate_score_hex,
)

DEFAULT_DIR = Path(os.environ.get("NOSTR_POC_DIR", ".nostr-poc")).resolve()
DEFAULT_PASSPHRASE = os.environ.get("NOSTR_PASSPHRASE", "")
ROLES_2 = ("alice", "bob")
ROLES_8 = tuple(f"a{i}" for i in range(1, 9))


def _roles_for(expect_peers: int) -> tuple[str, ...]:
    if expect_peers == 2:
        return ROLES_2
    if expect_peers == 8:
        return ROLES_8
    raise SystemExit(f"--expect-peers must be 2 or 8, not {expect_peers}")


class _OfflineL402:
    """Stand-in for L402Client.fetch — no HTTP, no LND."""

    def fetch(self, url: str, **_kwargs: Any) -> Any:
        class _Resp:
            status_code = 200
            paid = True

            def json(self) -> dict[str, Any]:
                return {
                    "ok": True,
                    "service": "mempool-feerate",
                    "fast": 3,
                    "medium": 2,
                    "slow": 1,
                }

        print(f"[l402] --offline-bus mock GET {url}")
        return _Resp()


def _require_passphrase(p: str) -> str:
    if not p:
        raise SystemExit(
            "Set NOSTR_PASSPHRASE or --passphrase (encrypts Nostr nsec at rest)."
        )
    return p


def _bus_dir(root: Path) -> Path:
    return root / "bus"


def _wait_bus_file(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            return
        time.sleep(0.25)
    raise SystemExit(f"timeout waiting for {path}")


def _sign(sk: Any, payload: dict[str, Any], extra_tags: list[list[str]] | None = None):
    tags = [["t", COORD_TAG], ["client", "agent-bitcoin-swarm-l402"]]
    if extra_tags:
        tags.extend(extra_tags)
    event = sign_json_event(sk, payload, kind=EventKind.TEXT_NOTE, tags=tags)
    if not event.verify():
        raise SystemExit("Failed to verify own event signature")
    return event


def _explain(
    *,
    role: str,
    npub: str,
    score: int,
    peer_score: int,
    winner_npub: str,
    i_pay: bool,
) -> str | None:
    if not (os.environ.get("XAI_API_KEY") or "").strip():
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_xai import ChatXAI
    except ImportError:
        return None
    llm = ChatXAI(model="grok-4-1-fast-reasoning", temperature=0.2)
    who = "I pay" if i_pay else "peer pays"
    human = (
        f"Agent {role} npub={npub[:12]}… score={score} peer_score={peer_score} "
        f"winner_npub={winner_npub[:12]}… ({who}). One sentence. Do not pay."
    )
    msg = llm.invoke(
        [
            SystemMessage(
                content=(
                    "You explain a finished Lightning L402 negotiation. "
                    "One sentence. Never instruct or execute a payment."
                )
            ),
            HumanMessage(content=human),
        ]
    )
    text = str(getattr(msg, "content", "") or "").strip().split("\n")[0]
    return text or None


def _pay_l402(url: str, price: int, offline: bool) -> tuple[int, bool, dict[str, int]]:
    if offline:
        resp = _OfflineL402().fetch(url)
    else:
        from agent_bitcoin import L402Client, create_client

        client = L402Client(create_client(), expected_price_sats=price)
        resp = client.fetch(url, method="GET")
    status = int(getattr(resp, "status_code", 0) or 0)
    paid = bool(getattr(resp, "paid", False))
    body: Any = {}
    try:
        body = resp.json()
    except Exception:
        body = {}
    return status, paid, fee_band_summary(body)


def run_role(args: argparse.Namespace, role: str) -> int:
    role = role.lower()
    roles = _roles_for(int(args.expect_peers))
    if role not in roles:
        raise SystemExit(
            f"unknown role {role!r} for --expect-peers {args.expect_peers}; "
            f"expected one of {', '.join(roles)}"
        )
    passphrase = _require_passphrase(args.passphrase)
    root = Path(args.dir)
    bus = _bus_dir(root)
    url = args.url
    price = int(args.price)
    round_n = int(args.round)
    iid = invoice_id_for_url(url)

    sk = load_or_create_agent(root, role, passphrase, force_new=args.force_new_keys)
    npub = sk.public_key.bech32()
    pubkey_hex = sk.public_key.hex()
    score, score_hx = negotiate_score_hex(pubkey_hex, iid, round_n)
    print(
        f"[{role}] npub={npub} invoice_id={iid} round={round_n} "
        f"score={score} score_hex={score_hx}"
    )

    neg = {
        "type": "negotiate",
        "v": 1,
        "invoice_id": iid,
        "round": round_n,
        "url": url,
        "price_sats": price,
        "npub": npub,
        "score": score,
        "score_hex": score_hx,
    }
    write_bus_event(bus, f"{iid}_{role}_negotiate.json", _sign(sk, neg))

    others = [r for r in roles if r != role]
    print(f"[{role}] waiting for {len(others)} peer negotiate file(s) …")
    for peer in others:
        _wait_bus_file(bus / f"{iid}_{peer}_negotiate.json", args.timeout)

    candidates: list[tuple[str, int]] = []
    peer_scores: list[int] = []
    for r in roles:
        path = bus / f"{iid}_{r}_negotiate.json"
        ev = read_bus_event(path)
        if not ev.verify():
            raise SystemExit(f"[{role}] {r} negotiate signature invalid")
        payload = parse_payload(ev)
        if payload.get("type") != "negotiate":
            raise SystemExit(f"[{role}] unexpected type {payload.get('type')!r}")
        if payload.get("invoice_id") != iid:
            raise SystemExit(f"[{role}] invoice_id mismatch from {r}")
        sc, _ = negotiate_score_hex(ev.pubkey, iid, round_n)
        n = str(payload.get("npub") or "")
        candidates.append((n, sc))
        if r != role:
            peer_scores.append(sc)

    winner_npub, reason = choose_payer_n(candidates)
    i_pay = winner_npub == npub
    log_reason = "higher_score" if i_pay and reason == "lower_score" else reason
    print(
        f"[{role}] winner_npub={winner_npub} i_pay={i_pay} reason={log_reason} "
        f"peers={len(others)} peer_scores={peer_scores}"
    )

    if not args.no_llm:
        try:
            line = _explain(
                role=role,
                npub=npub,
                score=score,
                peer_score=max(peer_scores) if peer_scores else 0,
                winner_npub=winner_npub,
                i_pay=i_pay,
            )
            if line:
                print(f"[{role}] grok: {line}")
        except Exception as exc:
            print(f"[{role}] grok skipped: {exc}", file=sys.stderr)

    if not i_pay:
        concede = {
            "type": "concede",
            "v": 1,
            "invoice_id": iid,
            "round": round_n,
            "winner_npub": winner_npub,
            "loser_npub": npub,
            "reason": reason,
        }
        concede_name = (
            f"{iid}_concede.json" if len(roles) == 2 else f"{iid}_{role}_concede.json"
        )
        write_bus_event(bus, concede_name, _sign(sk, concede))
        result_path = bus / f"{iid}_result.json"
        print(f"[{role}] waiting for signed result …")
        _wait_bus_file(result_path, args.timeout)
        result_event = read_bus_event(result_path)
        if not result_event.verify():
            raise SystemExit(f"[{role}] result signature invalid")
        result = parse_payload(result_event)
        print(
            f"[{role}] result payer_npub={result.get('payer_npub')} "
            f"amount_sats={result.get('amount_sats')} "
            f"http_status={result.get('http_status')} paid={result.get('paid')} "
            f"summary={result.get('summary')}"
        )
        return 0 if result.get("paid") else 1

    status, paid, summary = _pay_l402(url, price, args.offline_bus)
    print(
        f"[{role}] l402 status={status} paid={paid} amount_sats={price} "
        f"summary={summary}"
    )
    result_payload = {
        "type": "result",
        "v": 1,
        "invoice_id": iid,
        "payer_npub": npub,
        "amount_sats": price,
        "http_status": status,
        "paid": paid,
        "summary": summary,
    }
    write_bus_event(bus, f"{iid}_result.json", _sign(sk, result_payload))
    return 0 if paid and status == 200 else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Nostr swarm: who pays one L402 GET (2 or 8 agents). "
            "Mock: --offline-bus. Live: all processes on the Mac, "
            "payer agent-bitcoin-lnd* + "
            "--url http://3.90.159.146:8081/paid/finance/mempool-feerate "
            "(not 127.0.0.1 on AWS; that is self-pay)."
        )
    )
    parser.add_argument(
        "--role",
        default="",
        help=(
            "alice|bob|both (two-agent) or a1…a8|all (eight-agent). "
            "Engineer path: one role per terminal"
        ),
    )
    parser.add_argument(
        "--expect-peers",
        type=int,
        default=0,
        help="2 or 8. Inferred from --role if omitted",
    )
    parser.add_argument(
        "--alice",
        action="store_true",
        help="Alias for --role alice",
    )
    parser.add_argument(
        "--bob",
        action="store_true",
        help="Alias for --role bob",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("L402_URL", DEFAULT_L402_URL),
        help=(
            "Paid L402 URL (default mock/on-box: %(default)s). "
            "Live from the Mac: http://3.90.159.146:8081/paid/finance/mempool-feerate"
        ),
    )
    parser.add_argument(
        "--price",
        type=int,
        default=int(os.getenv("L402_PRICE_SATS", str(DEFAULT_PRICE_SATS))),
        help="Expected invoice sats (default: %(default)s)",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=1,
        help="Negotiation round mixed into the score (default: 1)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help="Key + bus root (default: .nostr-poc or NOSTR_POC_DIR)",
    )
    parser.add_argument(
        "--passphrase",
        default=DEFAULT_PASSPHRASE,
        help="Encrypts nsec at rest (or NOSTR_PASSPHRASE)",
    )
    parser.add_argument(
        "--offline-bus",
        action="store_true",
        help="Mock L402 (fixture bands 3/2/1; no sats). Omit for live Mac→AWS pay",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip Grok explanation (also skipped if XAI_API_KEY is unset)",
    )
    parser.add_argument(
        "--relay",
        default="",
        help="Optional public relay (documented only; happy path is the file bus)",
    )
    parser.add_argument(
        "--force-new-keys",
        action="store_true",
        help="Rotate encrypted key files for this role",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Seconds to wait for peer bus files (default: 60)",
    )
    args = parser.parse_args(argv)
    role = (args.role or "").strip().lower()
    if args.alice and args.bob:
        raise SystemExit("Use --role both, not both --alice and --bob")
    if args.alice:
        role = "alice"
    elif args.bob:
        role = "bob"
    if not role:
        raise SystemExit("Pass --role alice|bob|both or a1…a8|all (or --alice / --bob)")
    expect = int(args.expect_peers or 0)
    if role in ROLES_8 or role == "all":
        expect = expect or 8
    elif role in ("alice", "bob", "both"):
        expect = expect or 2
    else:
        raise SystemExit(f"unknown --role {role!r}")
    if expect not in (2, 8):
        raise SystemExit("--expect-peers must be 2 or 8")
    if role in ROLES_8 and expect != 8:
        raise SystemExit("roles a1…a8 require --expect-peers 8")
    if role in ("alice", "bob") and expect != 2:
        raise SystemExit("alice/bob require --expect-peers 2")
    args.role = role
    args.expect_peers = expect
    if args.relay:
        print(
            "[relay] --relay is documented but not used; "
            "happy path is the file bus (.nostr-poc/bus/)",
            file=sys.stderr,
        )
    return args


def _assert_live_payer_not_invoice_node(offline: bool) -> None:
    """Aperture always invoices AWS LND; paying with that node is self-pay."""
    if offline:
        return
    container = (os.environ.get("LND_CONTAINER") or "").strip()
    if "agent-payment-decision-lnd" in container:
        raise SystemExit(
            "Live L402 pay with LND_CONTAINER="
            f"{container} is self-pay: Aperture invoices AWS LND. "
            "Use Mac agent-bitcoin-lnd* and "
            "--url http://3.90.159.146:8081/… or --offline-bus. "
            "See examples/swarm_l402.md."
        )


def _assert_no_stale_result(bus: Path, iid: str) -> None:
    path = bus / f"{iid}_result.json"
    if path.is_file():
        raise SystemExit(
            f"Stale bus result {path}. Clear before a new run:\n"
            "  rm -f .nostr-poc/bus/*.json"
        )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _assert_live_payer_not_invoice_node(args.offline_bus)
    iid = invoice_id_for_url(args.url)
    _assert_no_stale_result(_bus_dir(Path(args.dir)), iid)
    if args.role in ("both", "all"):
        batch = _roles_for(int(args.expect_peers))
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            futs = [pool.submit(run_role, args, r) for r in batch]
            codes = [f.result() for f in futs]
        print(f"[{args.role}] exits={codes}")
        return 0 if all(c == 0 for c in codes) else 1
    return run_role(args, args.role)


if __name__ == "__main__":
    raise SystemExit(main())
