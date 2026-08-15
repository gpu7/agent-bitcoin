"""Tiny HTTP origin for the Aperture L402 PoC (no LND, no payments)."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _payload(path: str) -> tuple[int, dict]:
    network = os.environ.get("L402_NETWORK", "regtest").strip() or "regtest"
    if path.split("?", 1)[0] == "/health":
        return 200, {"ok": True, "service": "l402-demo"}
    if path.split("?", 1)[0] == "/paid/hello":
        return 200, {
            "ok": True,
            "service": "l402-demo",
            "network": network,
            "msg": "hello",
        }
    return 404, {"ok": False, "error": "not found"}


class OriginHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        status, body = _payload(self.path)
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args: object) -> None:
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    host = os.environ.get("L402_ORIGIN_HOST", "0.0.0.0")
    port = int(os.environ.get("L402_ORIGIN_PORT", "8090"))
    httpd = ThreadingHTTPServer((host, port), OriginHandler)
    print(f"l402 origin listening on {host}:{port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
