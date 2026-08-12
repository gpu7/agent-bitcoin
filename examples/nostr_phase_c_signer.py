#!/usr/bin/env python3
"""Phase C: local policy signer (NIP-46-inspired) — agent never holds nsec.

The signer process:
  - Loads encrypted Nostr nsec once (passphrase)
  - Listens on a local Unix socket
  - Signs events only if policy allows (kind, rate limit, tags, payload type)

Agent / client processes talk JSON-lines over the socket and never see the private key.

This is a lab hardening step toward NIP-46 remote signers. It is NOT a full
NIP-46 bunker implementation and is localhost-only by design.

Usage:
  export NOSTR_PASSPHRASE='...'
  # Terminal 1 — unlock key into signer only
  .venv-nostr/bin/python examples/nostr_phase_c_signer.py serve --agent alice

  # Terminal 2 — client never loads nsec
  .venv-nostr/bin/python examples/nostr_phase_c_signer.py get-pubkey --agent alice
  .venv-nostr/bin/python examples/nostr_phase_c_signer.py sign --agent alice \\
      --type phase_c_demo --content '{"hello":"world"}'

  # One-shot demo (spawns signer, signs, stops)
  .venv-nostr/bin/python examples/nostr_phase_c_signer.py demo --agent alice

See docs/nostr-agent-identity.md (Phase C).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import socketserver
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

_EXAMPLES = Path(__file__).resolve().parent
if str(_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES))

try:
    from pynostr.event import Event, EventKind
    from pynostr.key import PrivateKey
except ImportError as e:  # pragma: no cover
    print(
        "Missing pynostr. Use Python 3.12:\n"
        "  uv venv -p 3.12 .venv-nostr\n"
        "  uv pip install --python .venv-nostr/bin/python -e '.[nostr]'\n"
        f"{e}",
        file=sys.stderr,
    )
    sys.exit(1)

from nostr_common import (  # noqa: E402
    event_to_dict,
    load_or_create_agent,
)

DEFAULT_DIR = Path(os.environ.get("NOSTR_POC_DIR", ".nostr-poc")).resolve()
DEFAULT_PASSPHRASE = os.environ.get("NOSTR_PASSPHRASE", "")
DEFAULT_POLICY = _EXAMPLES / "nostr_phase_c_policy.json"


def _socket_path(root: Path, agent: str) -> Path:
    """Unix socket path (keep short — AF_UNIX has a low max path length)."""
    override = os.environ.get("NOSTR_SIGNER_SOCK")
    if override:
        return Path(override)
    # Prefer /tmp to avoid long worktree paths breaking bind()
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in agent)[:32]
    return Path(f"/tmp/agent-bitcoin-signer-{safe}.sock")


def _load_policy(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "allowed_kinds": [0, 1],
            "max_signs_per_minute": 30,
            "require_tag": ["client", "agent-bitcoin-phase-c"],
            "allowed_payload_types": [
                "pay_request",
                "invoice_offer",
                "payment_result",
                "coord_note",
                "phase_c_demo",
            ],
        }
    return json.loads(path.read_text(encoding="utf-8"))


class PolicyEngine:
    def __init__(self, policy: dict[str, Any]):
        self.policy = policy
        self._sign_times: deque[float] = deque()

    def _rate_ok(self) -> bool:
        limit = int(self.policy.get("max_signs_per_minute") or 30)
        now = time.time()
        while self._sign_times and now - self._sign_times[0] > 60.0:
            self._sign_times.popleft()
        return len(self._sign_times) < limit

    def check_sign(self, kind: int, tags: list[list[str]], content: str) -> str | None:
        """Return error string if denied, else None."""
        allowed_kinds = set(self.policy.get("allowed_kinds") or [0, 1])
        if kind not in allowed_kinds:
            return f"kind {kind} not in allowed_kinds {sorted(allowed_kinds)}"

        req = self.policy.get("require_tag")
        if req and len(req) >= 2:
            key, val = req[0], req[1]
            if not any(len(t) >= 2 and t[0] == key and t[1] == val for t in tags):
                return f"missing required tag [{key}, {val}]"

        allowed_types = self.policy.get("allowed_payload_types")
        if allowed_types:
            try:
                payload = json.loads(content)
                ptype = payload.get("type")
                if ptype not in allowed_types:
                    return (
                        f"payload type {ptype!r} not in allowed_payload_types "
                        f"{allowed_types}"
                    )
            except json.JSONDecodeError:
                return "content must be JSON when allowed_payload_types is set"

        if not self._rate_ok():
            return "rate limit: max_signs_per_minute exceeded"
        return None

    def record_sign(self) -> None:
        self._sign_times.append(time.time())


class SignerState:
    def __init__(self, sk: PrivateKey, policy: PolicyEngine, agent: str):
        self.sk = sk
        self.policy = policy
        self.agent = agent

    def handle(self, req: dict[str, Any]) -> dict[str, Any]:
        rid = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        if method == "ping":
            return {"id": rid, "result": {"ok": True, "agent": self.agent}}

        if method == "get_public_key":
            return {
                "id": rid,
                "result": {
                    "pubkey": self.sk.public_key.hex(),
                    "npub": self.sk.public_key.bech32(),
                    "agent": self.agent,
                },
            }

        if method == "sign_event":
            content = params.get("content")
            if content is None:
                return {"id": rid, "error": "params.content required"}
            if not isinstance(content, str):
                content = json.dumps(content, separators=(",", ":"), sort_keys=True)
            kind = int(params.get("kind", EventKind.TEXT_NOTE))
            tags = params.get("tags") or []
            # Ensure policy client tag present
            req_tag = self.policy.policy.get("require_tag")
            if req_tag and len(req_tag) >= 2:
                if not any(
                    len(t) >= 2 and t[0] == req_tag[0] and t[1] == req_tag[1]
                    for t in tags
                ):
                    tags = list(tags) + [list(req_tag)]

            err = self.policy.check_sign(kind, tags, content)
            if err:
                return {"id": rid, "error": f"policy denied: {err}"}

            event = Event(content=content, kind=kind, tags=tags)
            event.sign(self.sk.hex())
            if hasattr(event, "verify") and not event.verify():
                return {"id": rid, "error": "internal: signature verify failed"}
            self.policy.record_sign()
            return {"id": rid, "result": {"event": event_to_dict(event)}}

        if method == "get_policy":
            # Do not leak secrets; policy file is non-secret
            safe = {
                k: v
                for k, v in self.policy.policy.items()
                if k != "passphrase" and "secret" not in k.lower()
            }
            return {"id": rid, "result": safe}

        return {"id": rid, "error": f"unknown method: {method}"}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        state: SignerState = self.server.signer_state  # type: ignore[attr-defined]
        for raw in self.rfile:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                resp = {"id": None, "error": "invalid json"}
            else:
                resp = state.handle(req)
            self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))
            self.wfile.flush()


class ThreadedUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def rpc_call(
    sock_path: Path, method: str, params: dict | None = None, timeout: float = 10.0
) -> dict:
    if not sock_path.exists():
        raise SystemExit(
            f"Signer socket not found: {sock_path}\n"
            "Start: python examples/nostr_phase_c_signer.py serve --agent <name>"
        )
    req = {"id": str(time.time_ns()), "method": method, "params": params or {}}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock_path))
        s.sendall((json.dumps(req) + "\n").encode("utf-8"))
        data = b""
        while b"\n" not in data:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    if not data:
        raise SystemExit("Empty response from signer")
    return json.loads(data.decode("utf-8").splitlines()[0])


def cmd_serve(args: argparse.Namespace) -> int:
    passphrase = args.passphrase or DEFAULT_PASSPHRASE
    if not passphrase:
        raise SystemExit("Set NOSTR_PASSPHRASE or --passphrase")

    policy = PolicyEngine(_load_policy(args.policy))
    sk = load_or_create_agent(
        args.dir, args.agent, passphrase, force_new=args.force_new_keys
    )
    state = SignerState(sk, policy, args.agent)

    sock_path = _socket_path(args.dir, args.agent)
    args.dir.mkdir(parents=True, exist_ok=True)
    if sock_path.exists():
        sock_path.unlink()

    server = ThreadedUnixServer(str(sock_path), _Handler)
    server.signer_state = state  # type: ignore[attr-defined]
    os.chmod(sock_path, 0o600)

    print("=== Phase C policy signer (local) ===")
    print(f"agent:   {args.agent}")
    print(f"npub:    {sk.public_key.bech32()}")
    print(f"socket:  {sock_path}")
    print(f"policy:  {args.policy}")
    print("Private key loaded in THIS process only. Clients must not use nsec.")
    print("Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[signer] stopped")
    finally:
        server.server_close()
        if sock_path.exists():
            sock_path.unlink()
    return 0


def cmd_get_pubkey(args: argparse.Namespace) -> int:
    sock = _socket_path(args.dir, args.agent)
    resp = rpc_call(sock, "get_public_key")
    if resp.get("error"):
        print(f"ERROR: {resp['error']}", file=sys.stderr)
        return 1
    print(json.dumps(resp["result"], indent=2))
    return 0


def cmd_get_policy(args: argparse.Namespace) -> int:
    sock = _socket_path(args.dir, args.agent)
    resp = rpc_call(sock, "get_policy")
    if resp.get("error"):
        print(f"ERROR: {resp['error']}", file=sys.stderr)
        return 1
    print(json.dumps(resp["result"], indent=2))
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    sock = _socket_path(args.dir, args.agent)
    if args.content_file:
        content_obj = json.loads(Path(args.content_file).read_text(encoding="utf-8"))
    elif args.content:
        content_obj = json.loads(args.content)
    else:
        content_obj = {
            "type": args.type,
            "v": 1,
            "message": args.message or "phase-c demo",
            "ts": int(time.time()),
        }
    if "type" not in content_obj:
        content_obj["type"] = args.type

    content = json.dumps(content_obj, separators=(",", ":"), sort_keys=True)
    tags = [["t", "agent-bitcoin-phase-c"], ["client", "agent-bitcoin-phase-c"]]
    resp = rpc_call(
        sock,
        "sign_event",
        {"content": content, "kind": args.kind, "tags": tags},
    )
    if resp.get("error"):
        print(f"ERROR: {resp['error']}", file=sys.stderr)
        return 1
    event = resp["result"]["event"]
    print(json.dumps(event, indent=2))
    # Local verify without private key
    ev = Event(
        content=event["content"],
        kind=event["kind"],
        tags=event.get("tags") or [],
        pubkey=event.get("pubkey"),
        id=event.get("id"),
        sig=event.get("sig"),
        created_at=event.get("created_at"),
    )
    if hasattr(ev, "verify") and ev.verify():
        print("\n[client] signature VERIFY ok (client never loaded nsec)")
    return 0


def cmd_deny_demo(args: argparse.Namespace) -> int:
    """Show policy denial (wrong payload type)."""
    sock = _socket_path(args.dir, args.agent)
    resp = rpc_call(
        sock,
        "sign_event",
        {
            "content": json.dumps({"type": "not_allowed_type", "v": 1}),
            "kind": 1,
            "tags": [["client", "agent-bitcoin-phase-c"]],
        },
    )
    print(json.dumps(resp, indent=2))
    return 0 if resp.get("error") else 1


def cmd_demo(args: argparse.Namespace) -> int:
    """One process: start signer thread, exercise client, stop."""
    passphrase = args.passphrase or DEFAULT_PASSPHRASE
    if not passphrase:
        raise SystemExit("Set NOSTR_PASSPHRASE or --passphrase")

    # Ensure key exists before server starts
    load_or_create_agent(
        args.dir, args.agent, passphrase, force_new=args.force_new_keys
    )

    sock_path = _socket_path(args.dir, args.agent)
    if sock_path.exists():
        sock_path.unlink()

    # Run serve in background thread by importing logic
    stop = threading.Event()

    def _run_server() -> None:
        policy = PolicyEngine(_load_policy(args.policy))
        sk = load_or_create_agent(args.dir, args.agent, passphrase, force_new=False)
        state = SignerState(sk, policy, args.agent)
        server = ThreadedUnixServer(str(sock_path), _Handler)
        server.signer_state = state  # type: ignore[attr-defined]
        os.chmod(sock_path, 0o600)
        print(f"[demo] signer up on {sock_path} npub={sk.public_key.bech32()}")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        stop.wait()
        server.shutdown()
        server.server_close()
        if sock_path.exists():
            sock_path.unlink()

    t = threading.Thread(target=_run_server, daemon=True)
    t.start()
    time.sleep(0.3)

    print("\n--- client: get_public_key (no nsec) ---")
    pk = rpc_call(sock_path, "get_public_key")
    print(json.dumps(pk.get("result"), indent=2))

    print("\n--- client: sign_event allowed ---")
    args_ns = argparse.Namespace(
        dir=args.dir,
        agent=args.agent,
        content=None,
        content_file=None,
        type="phase_c_demo",
        message="phase-c local signer demo",
        kind=1,
    )
    rc = cmd_sign(args_ns)
    if rc != 0:
        stop.set()
        return rc

    print("\n--- client: sign_event denied (policy) ---")
    cmd_deny_demo(args_ns)

    print("\nRESULT: PASS — Phase C local policy signer demo")
    print("Agent client never loaded nsec; signer enforced policy.")
    stop.set()
    time.sleep(0.2)
    return 0


def main() -> int:
    # Shared flags as parents so either order works:
    #   prog --agent alice demo
    #   prog demo --agent alice
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--dir", type=Path, default=DEFAULT_DIR, help="Key + socket directory"
    )
    common.add_argument(
        "--agent", default="alice", help="Agent key name (default: alice)"
    )
    common.add_argument(
        "--passphrase", default=DEFAULT_PASSPHRASE, help="Or NOSTR_PASSPHRASE"
    )
    common.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY,
        help="Policy JSON path",
    )
    common.add_argument("--force-new-keys", action="store_true")

    parser = argparse.ArgumentParser(
        description="Phase C local policy signer (NIP-46-inspired, localhost)",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser(
        "serve", parents=[common], help="Run signer daemon (holds nsec)"
    )
    p_serve.set_defaults(func=cmd_serve)

    p_pk = sub.add_parser(
        "get-pubkey", parents=[common], help="Client: fetch pubkey from signer"
    )
    p_pk.set_defaults(func=cmd_get_pubkey)

    p_pol = sub.add_parser(
        "get-policy", parents=[common], help="Client: fetch active policy"
    )
    p_pol.set_defaults(func=cmd_get_policy)

    p_sign = sub.add_parser(
        "sign", parents=[common], help="Client: request a signed event"
    )
    p_sign.add_argument("--type", default="phase_c_demo")
    p_sign.add_argument("--message", default="")
    p_sign.add_argument("--content", default="", help="Raw JSON object string")
    p_sign.add_argument("--content-file", default="")
    p_sign.add_argument("--kind", type=int, default=1)
    p_sign.set_defaults(func=cmd_sign)

    p_deny = sub.add_parser(
        "deny-demo", parents=[common], help="Client: show a policy denial"
    )
    p_deny.set_defaults(func=cmd_deny_demo)

    p_demo = sub.add_parser(
        "demo", parents=[common], help="One-shot: signer + client self-test"
    )
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
