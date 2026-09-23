#!/usr/bin/env python3
"""Two Nostr agents negotiate who pays one Aperture L402 GET.

Identity: Phase A/B encrypted keys under .nostr-poc/ (same as nostr_phase_b_payment.py).
Transport: signed kind-8139 events on NOSTR_RELAYS (localhost mock if --offline-bus).
Pay: L402Client (same 402 → pay → retry as l402_pay.py). Coded policy picks
the payer; optional Grok only explains. L402 HTTP stays unsigned (no npub).

Mock (any one host): --offline-bus (no sats; fixture bands 3/2/1).
Live: both processes on the Mac; Mac LND agent-bitcoin-lnd* pays AWS Aperture.
  --url http://3.90.159.146:8081/paid/finance/mempool-feerate --price 100
Do not live-pay with LND_CONTAINER=agent-payment-decision-lnd* (self-pay).

Engineer path (two terminals):

  export NOSTR_PASSPHRASE='...'
  ./examples/agent-to-merchant-pay.sh --role alice --offline-bus --no-llm
  ./examples/agent-to-merchant-pay.sh --role bob --offline-bus --no-llm

See examples/agent-swarm-merchant-2.md
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

_EXAMPLES = Path(__file__).resolve().parent
if str(_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES))

try:
    import pynostr.event  # noqa: F401
except ImportError as e:  # pragma: no cover
    print(
        "Missing pynostr. Use Python 3.12:\n"
        "  uv venv -p 3.12 .venv-nostr\n"
        "  uv pip install --python .venv-nostr/bin/python -e '.[nostr]'\n"
        "  ./examples/agent-to-merchant-pay.sh --role alice --offline-bus --no-llm\n"
        "Do not use: uv run python  (3.13/3.14 skips .[nostr])\n"
        f"{e}",
        file=sys.stderr,
    )
    sys.exit(1)

from nostr_common import (  # noqa: E402
    load_or_create_agent,
    parse_payload,
    sign_json_event,
)

from agent_bitcoin.nostr.merchant_coord import (  # noqa: E402
    COORD_TAG,
    KIND_MERCHANT,
    collect_events,
    has_result,
    hold_mock,
    publish as coord_publish,
    wait_event,
)
from agent_bitcoin.nostr.negotiate import (  # noqa: E402
    DEFAULT_L402_URL,
    DEFAULT_PRICE_SATS,
    choose_payer_n,
    fee_band_summary,
    invoice_id_for_url,
    negotiate_score_hex,
)
from agent_bitcoin.nostr.resolve import (  # noqa: E402
    DEFAULT_SAT_VB,
    DEFAULT_VSIZE,
    PUZZLE_FEE_SATS,
    check_solved,
    fee_sats_expected,
    fee_sats_problem,
    parse_force_vote,
    parse_yes_no,
    parse_vote_reason,
    pick_first_correct,
    pick_llm_gate_winner,
)

DEFAULT_DIR = Path(os.environ.get("NOSTR_POC_DIR", ".nostr-poc")).resolve()
DEFAULT_PASSPHRASE = os.environ.get("NOSTR_PASSPHRASE", "")
AWS_LND_PUB = "0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967"
LLM_GATE_URL = "http://3.90.159.146:8081/paid/finance/ln-path-fee-hint"
LLM_GATE_TIMEOUT_S = 8.0
_LLM_CALLS = 0
_LLM_LOCK = threading.Lock()
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


def _sign(sk: Any, payload: dict[str, Any], role: str, invoice_id: str):
    tags = [
        ["t", COORD_TAG],
        ["role", role],
        ["client", "agent-bitcoin-merchant"],
    ]
    event = sign_json_event(sk, payload, kind=KIND_MERCHANT, tags=tags)
    if not event.verify():
        raise SystemExit("Failed to verify own event signature")
    return event


def _pub(args: argparse.Namespace, event: Any) -> None:
    coord_publish(event, offline=bool(args.offline_bus))


def _wait(
    args: argparse.Namespace,
    invoice_id: str,
    msg_type: str,
    role: str | None,
    timeout: float,
) -> Any:
    return wait_event(
        offline=bool(args.offline_bus),
        invoice_id=invoice_id,
        msg_type=msg_type,
        role=role,
        timeout=timeout,
        since=int(getattr(args, "since", 0) or 0),
        key_dir=Path(args.dir),
        round_n=int(args.round),
    )


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


def _pay_l402(
    url: str,
    price: int,
    offline: bool,
    *,
    method: str = "GET",
    json_body: Any | None = None,
) -> tuple[int, bool, dict[str, int]]:
    if offline:
        resp = _OfflineL402().fetch(url)
    else:
        from agent_bitcoin import L402Client, create_client

        client = L402Client(create_client(), expected_price_sats=price)
        resp = client.fetch(url, method=method, json_body=json_body)
    status = int(getattr(resp, "status_code", 0) or 0)
    paid = bool(getattr(resp, "paid", False))
    body: Any = {}
    try:
        body = resp.json()
    except Exception:
        body = {}
    return status, paid, fee_band_summary(body)


def _ensure_problem(
    args: argparse.Namespace, sk: Any, role: str, iid: str, problem: dict
) -> dict[str, Any]:
    payload = {
        **problem,
        "v": 1,
        "invoice_id": iid,
        "type": "problem",
        "round": int(args.round),
    }
    _pub(args, _sign(sk, payload, role, iid))
    ev = _wait(args, iid, "problem", None, min(5.0, float(args.timeout)))
    body = parse_payload(ev)
    if int(body.get("vsize", -1)) != int(problem["vsize"]) or int(
        body.get("sat_vb", -1)
    ) != int(problem["sat_vb"]):
        raise SystemExit("problem mismatch on relay")
    return body


def _puzzle_answer(args: argparse.Namespace, problem: dict[str, Any]) -> int:
    expected = fee_sats_expected(int(problem["vsize"]), int(problem["sat_vb"]))
    if args.no_llm or not (os.environ.get("XAI_API_KEY") or "").strip():
        return expected
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_xai import ChatXAI

        llm = ChatXAI(model="grok-4-1-fast-reasoning", temperature=0)
        msg = llm.invoke(
            [
                SystemMessage(
                    content="Reply with one integer only. The fee in sats is ceil(vsize * sat_vb)."
                ),
                HumanMessage(content=str(problem.get("text") or "")),
            ]
        )
        guess = str(getattr(msg, "content", "") or "").strip().split()[0]
        print(f"[puzzle] grok suggested {guess!r} (win check uses {expected})")
    except Exception as exc:
        print(f"[puzzle] grok skipped: {exc}", file=sys.stderr)
    return expected


def _wait_puzzle_winner(
    args: argparse.Namespace, iid: str, problem: dict[str, Any], timeout: float
) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows: list[tuple[float, str, dict[str, Any]]] = []
        for ev in collect_events(
            offline=bool(args.offline_bus),
            invoice_id=iid,
            msg_type="solved",
            timeout=0.4,
            since=int(getattr(args, "since", 0) or 0),
            key_dir=Path(args.dir),
            round_n=int(args.round),
        ):
            payload = parse_payload(ev)
            rows.append(
                (float(ev.created_at or 0), str(payload.get("npub") or ""), payload)
            )
        winner = pick_first_correct(rows, problem)
        if winner:
            return winner
        time.sleep(0.25)
    raise SystemExit("timeout waiting for a correct solved event")


def _finish_pay_or_wait(
    *,
    args: argparse.Namespace,
    role: str,
    sk: Any,
    npub: str,
    iid: str,
    round_n: int,
    url: str,
    price: int,
    roles: tuple[str, ...],
    i_pay: bool,
    winner_npub: str,
    reason: str,
) -> int:
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
        _pub(args, _sign(sk, concede, role, iid))
        print(f"[{role}] waiting for signed result …")
        result_event = _wait(args, iid, "result", None, args.timeout)
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

    status, paid, summary = _pay_l402(
        url,
        price,
        args.offline_bus,
        method=getattr(args, "http_method", "GET") or "GET",
        json_body=getattr(args, "json_body", None),
    )
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
        "round": round_n,
    }
    _pub(args, _sign(sk, result_payload, role, iid))
    return 0 if paid and status == 200 else 1


def run_puzzle_role(args: argparse.Namespace, role: str, roles: tuple[str, ...]) -> int:
    if args.puzzle_type != PUZZLE_FEE_SATS:
        raise SystemExit(
            f"unknown --puzzle-type {args.puzzle_type!r} (only {PUZZLE_FEE_SATS} in this release)"
        )
    passphrase = _require_passphrase(args.passphrase)
    root = Path(args.dir)
    url = args.url
    price = int(args.price)
    round_n = int(args.round)
    iid = invoice_id_for_url(url)
    sk = load_or_create_agent(root, role, passphrase, force_new=args.force_new_keys)
    problem = _ensure_problem(
        args, sk, role, iid, fee_sats_problem(int(args.vsize), int(args.sat_vb))
    )
    npub = sk.public_key.bech32()
    answer = _puzzle_answer(args, problem)
    print(
        f"[{role}] npub={npub} invoice_id={iid} resolve=puzzle "
        f"type={PUZZLE_FEE_SATS} vsize={problem['vsize']} sat_vb={problem['sat_vb']} "
        f"answer={answer}"
    )
    solved = {
        "type": "solved",
        "v": 1,
        "invoice_id": iid,
        "puzzle_type": PUZZLE_FEE_SATS,
        "vsize": int(problem["vsize"]),
        "sat_vb": int(problem["sat_vb"]),
        "answer": int(answer),
        "npub": npub,
        "round": round_n,
    }
    if not check_solved(solved, problem):
        raise SystemExit(f"[{role}] local answer failed the coded check")
    _pub(args, _sign(sk, solved, role, iid))
    winner_npub = _wait_puzzle_winner(args, iid, problem, args.timeout)
    i_pay = winner_npub == npub
    print(f"[{role}] winner_npub={winner_npub} i_pay={i_pay} reason=first_correct")
    return _finish_pay_or_wait(
        args=args,
        role=role,
        sk=sk,
        npub=npub,
        iid=iid,
        round_n=round_n,
        url=url,
        price=price,
        roles=roles,
        i_pay=i_pay,
        winner_npub=winner_npub,
        reason="first_correct",
    )


def _gate_prompt():
    from langchain_core.messages import SystemMessage

    return [
        SystemMessage(
            content=(
                "Line 1: YES or NO only. Line 2: one short reason. "
                "Do not pay. Do not ask for invoices or keys."
            )
        ),
    ]


def _take_llm_slot() -> bool:
    global _LLM_CALLS
    max_calls = int(os.environ.get("SWARM_LLM_MAX_CALLS") or "2")
    with _LLM_LOCK:
        if _LLM_CALLS >= max_calls:
            return False
        _LLM_CALLS += 1
        return True


def ask_gate(job: str, backend: str = "grok") -> tuple[str, str]:
    """YES/NO for llm-gate. backend grok|ollama. FORCE_VOTE overrides both."""
    try:
        forced = parse_force_vote(os.environ.get("SWARM_LLM_FORCE_VOTE"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if forced:
        return forced, "forced_test"
    backend = (backend or "grok").strip().lower()
    if backend == "ollama":
        return _ask_ollama(job)
    return _ask_grok(job)


def _ask_grok(job: str) -> tuple[str, str]:
    key = (os.environ.get("XAI_API_KEY") or "").strip()
    if not key:
        return "NO", "no_key"
    if not _take_llm_slot():
        return "NO", "unparsed"
    try:
        from langchain_core.messages import HumanMessage
        from langchain_xai import ChatXAI
    except ImportError:
        return "NO", "unparsed"
    llm = ChatXAI(
        model="grok-4-1-fast-reasoning",
        temperature=0,
        max_tokens=80,
        api_key=key,
        timeout=LLM_GATE_TIMEOUT_S,
    )

    def _invoke() -> str:
        msg = llm.invoke([*_gate_prompt(), HumanMessage(content=job)])
        return str(getattr(msg, "content", "") or "")

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_invoke)
            raw = fut.result(timeout=LLM_GATE_TIMEOUT_S)
    except Exception:
        return "NO", "timeout"
    return parse_vote_reason(raw)


def _ask_ollama(job: str) -> tuple[str, str]:
    if not _take_llm_slot():
        return "NO", "unparsed"
    host = (os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL") or "llama3.2"
    try:
        from langchain_core.messages import HumanMessage
        from langchain_ollama import ChatOllama

        llm = ChatOllama(model=model, base_url=host, temperature=0)

        def _invoke() -> str:
            msg = llm.invoke([*_gate_prompt(), HumanMessage(content=job)])
            return str(getattr(msg, "content", "") or "")

        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_invoke)
            raw = fut.result(timeout=LLM_GATE_TIMEOUT_S)
    except Exception:
        return "NO", "ollama_down"
    return parse_vote_reason(raw)


def run_llm_gate_role(
    args: argparse.Namespace, role: str, roles: tuple[str, ...]
) -> int:
    passphrase = _require_passphrase(args.passphrase)
    root = Path(args.dir)
    url = args.url
    price = int(args.price)
    round_n = int(args.round)
    iid = invoice_id_for_url(url)
    sk = load_or_create_agent(root, role, passphrase, force_new=args.force_new_keys)
    npub = sk.public_key.bech32()
    score, _hx = negotiate_score_hex(sk.public_key.hex(), iid, round_n)
    job = (
        f"Should this agent pay {price} sats for POST /paid/finance/ln-path-fee-hint "
        f"(Lightning first-path fee hint)? Reply YES or NO."
    )
    vote, grok_reason = ask_gate(job, getattr(args, "model", "grok") or "grok")
    print(
        f"[{role}] npub={npub} resolve=llm-gate vote={vote} "
        f"reason={grok_reason} score={score}"
    )
    payload = {
        "type": "vote",
        "v": 1,
        "invoice_id": iid,
        "vote": vote,
        "reason": grok_reason,
        "npub": npub,
        "score": score,
        "round": round_n,
    }
    _pub(args, _sign(sk, payload, role, iid))
    others = [r for r in roles if r != role]
    for peer in others:
        _wait(args, iid, "vote", peer, args.timeout)
    votes: list[tuple[str, str, int]] = []
    for r in roles:
        ev = _wait(args, iid, "vote", r, args.timeout)
        if not ev.verify():
            raise SystemExit(f"[{role}] {r} vote signature invalid")
        body = parse_payload(ev)
        votes.append(
            (
                str(body.get("npub") or ""),
                parse_yes_no(str(body.get("vote") or "NO")),
                negotiate_score_hex(ev.pubkey, iid, round_n)[0],
            )
        )
    winner_npub = pick_llm_gate_winner(votes)
    if winner_npub is None:
        print(f"[{role}] llm-gate: 0 YES — skip L402")
        if role == "alice":
            skipped = {
                "type": "result",
                "v": 1,
                "invoice_id": iid,
                "paid": False,
                "skipped": True,
                "http_status": 0,
                "amount_sats": 0,
                "summary": {},
                "round": round_n,
            }
            _pub(args, _sign(sk, skipped, role, iid))
        else:
            _wait(args, iid, "result", None, args.timeout)
        return 0
    i_pay = winner_npub == npub
    print(f"[{role}] winner_npub={winner_npub} i_pay={i_pay} reason=llm-gate")
    return _finish_pay_or_wait(
        args=args,
        role=role,
        sk=sk,
        npub=npub,
        iid=iid,
        round_n=round_n,
        url=url,
        price=price,
        roles=roles,
        i_pay=i_pay,
        winner_npub=winner_npub,
        reason="llm-gate",
    )


def run_role(args: argparse.Namespace, role: str) -> int:
    role = role.lower()
    roles = _roles_for(int(args.expect_peers))
    if getattr(args, "resolve", "hash") == "llm-gate":
        if role not in roles:
            raise SystemExit(f"unknown role {role!r}")
        return run_llm_gate_role(args, role, roles)
    if getattr(args, "resolve", "hash") == "puzzle":
        if role not in roles:
            raise SystemExit(
                f"unknown role {role!r} for --expect-peers {args.expect_peers}; "
                f"expected one of {', '.join(roles)}"
            )
        return run_puzzle_role(args, role, roles)
    if role not in roles:
        raise SystemExit(
            f"unknown role {role!r} for --expect-peers {args.expect_peers}; "
            f"expected one of {', '.join(roles)}"
        )
    passphrase = _require_passphrase(args.passphrase)
    root = Path(args.dir)
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
    _pub(args, _sign(sk, neg, role, iid))

    others = [r for r in roles if r != role]
    print(f"[{role}] waiting for {len(others)} peer negotiate event(s) …")
    for peer in others:
        _wait(args, iid, "negotiate", peer, args.timeout)

    candidates: list[tuple[str, int]] = []
    peer_scores: list[int] = []
    for r in roles:
        ev = _wait(args, iid, "negotiate", r, args.timeout)
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

    return _finish_pay_or_wait(
        args=args,
        role=role,
        sk=sk,
        npub=npub,
        iid=iid,
        round_n=round_n,
        url=url,
        price=price,
        roles=roles,
        i_pay=i_pay,
        winner_npub=winner_npub,
        reason=reason,
    )


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
        help="Encrypted key directory (default: .nostr-poc or NOSTR_POC_DIR)",
    )
    parser.add_argument(
        "--passphrase",
        default=DEFAULT_PASSPHRASE,
        help="Encrypts nsec at rest (or NOSTR_PASSPHRASE)",
    )
    parser.add_argument(
        "--offline-bus",
        action="store_true",
        help=(
            "Localhost mock relay (127.0.0.1:8765 or MERCHANT_MOCK_PORT). "
            "No shared JSON files and no public relays. "
            "Also skips L402 (fixture bands 3/2/1)"
        ),
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip Grok explanation (also skipped if XAI_API_KEY is unset)",
    )
    parser.add_argument(
        "--relay",
        default="",
        help="Deprecated alias; live path uses NOSTR_RELAYS",
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
        help="Seconds to wait for the peer's signed events (default: 60)",
    )
    parser.add_argument(
        "--resolve",
        choices=("hash", "puzzle", "llm-gate"),
        default="hash",
        help="Winner rule: hash (default), puzzle, or llm-gate (YES/NO then hash)",
    )
    parser.add_argument(
        "--model",
        choices=("grok", "ollama"),
        default="",
        help="llm-gate backend (default grok). Mutually exclusive; not with --no-llm",
    )
    parser.add_argument(
        "--dest-pubkey",
        default=AWS_LND_PUB,
        help="llm-gate path-hint dest (default: AWS LND pubkey)",
    )
    parser.add_argument(
        "--hint-sats",
        type=int,
        default=100,
        help="llm-gate path-hint amount_sats (default: 100)",
    )
    parser.add_argument(
        "--puzzle-type",
        default=PUZZLE_FEE_SATS,
        help=f"Puzzle kind when --resolve puzzle (default: {PUZZLE_FEE_SATS})",
    )
    parser.add_argument(
        "--vsize",
        type=int,
        default=DEFAULT_VSIZE,
        help="fee-sats vsize (default: %(default)s)",
    )
    parser.add_argument(
        "--sat-vb",
        type=int,
        default=DEFAULT_SAT_VB,
        help="fee-sats sat/vB (default: %(default)s)",
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
    args.resolve = (args.resolve or "hash").strip().lower()
    args.http_method = "GET"
    args.json_body = None
    if args.resolve == "puzzle" and args.puzzle_type != PUZZLE_FEE_SATS:
        raise SystemExit(
            f"unknown --puzzle-type {args.puzzle_type!r} (only {PUZZLE_FEE_SATS})"
        )
    if args.no_llm and (args.model or "").strip():
        raise SystemExit("--no-llm cannot be combined with --model")
    if args.resolve == "llm-gate":
        if expect != 2:
            raise SystemExit("llm-gate is two-agent only (--role alice|bob|both)")
        if args.no_llm:
            raise SystemExit("llm-gate cannot be used with --no-llm")
        args.model = (args.model or "grok").strip().lower()
        try:
            forced = parse_force_vote(os.environ.get("SWARM_LLM_FORCE_VOTE"))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if (
            not forced
            and args.model == "grok"
            and not (os.environ.get("XAI_API_KEY") or "").strip()
        ):
            raise SystemExit(
                "llm-gate --model grok requires XAI_API_KEY in the environment"
            )
        if args.url == DEFAULT_L402_URL:
            args.url = LLM_GATE_URL
        args.http_method = "POST"
        args.json_body = {
            "dest_pubkey": args.dest_pubkey,
            "amount_sats": int(args.hint_sats),
        }
    if args.relay:
        print(
            "[relay] --relay is ignored; set NOSTR_RELAYS "
            f"(kind {KIND_MERCHANT}, verified before trust)",
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
            "See examples/agent-swarm-merchant-2.md."
        )


def _assert_no_stale_result(args: argparse.Namespace, iid: str) -> None:
    if has_result(
        iid,
        int(args.round),
        offline=bool(args.offline_bus),
        key_dir=Path(args.dir),
    ):
        raise SystemExit(
            "Stale result already on the relay for this invoice_id and round. "
            "Bump --round and run again."
        )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    args.since = int(time.time()) - max(int(args.timeout), 30)
    _assert_live_payer_not_invoice_node(args.offline_bus)
    holder = hold_mock() if args.offline_bus else None
    try:
        iid = invoice_id_for_url(args.url)
        _assert_no_stale_result(args, iid)
        if args.role in ("both", "all"):
            batch = _roles_for(int(args.expect_peers))
            with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                futs = [pool.submit(run_role, args, r) for r in batch]
                codes = [f.result() for f in futs]
            print(f"[{args.role}] exits={codes}")
            return 0 if all(c == 0 for c in codes) else 1
        return run_role(args, args.role)
    finally:
        if holder is not None:
            holder.close()


if __name__ == "__main__":
    raise SystemExit(main())
