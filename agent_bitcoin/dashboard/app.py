"""FastAPI page for the read-only infrastructure map. Binds to 127.0.0.1."""

from __future__ import annotations

import argparse
import os
import sys

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from agent_bitcoin.dashboard.probes import (
    ProbeIO,
    RealProbeIO,
    collect_status,
    network_name,
)

BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_MAP_NODES = (
    ("bitcoin", "Bitcoin network"),
    ("channel", "Lightning channel"),
    ("payer", "Payer agent"),
    ("invoice", "Invoice agent"),
    ("nostr", "Nostr"),
    ("aperture", "Aperture"),
    ("origin", "Merchant origin"),
)

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Agent Bitcoin infrastructure</title>
<style>
  :root {
    --navy: #070b14;
    --card: #10192b;
    --cyan: #5ad7ff;
    --orange: #ff9a2e;
    --muted: #8b97ad;
    --up: #3dffb0;
    --down: #ff5d6c;
    --locked: #ffb020;
    --unknown: #8b97ad;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    background: var(--navy);
    color: var(--cyan);
    font: 16px/1.4 ui-sans-serif, system-ui, sans-serif;
  }
  header, footer {
    padding: 20px 28px 0;
  }
  h1 {
    margin: 0;
    font-size: 28px;
    font-weight: 600;
    color: var(--orange);
    letter-spacing: 0.02em;
  }
  header p, footer p { margin: 6px 0 0; color: var(--muted); }
  .map {
    position: relative;
    max-width: 980px;
    margin: 12px auto 28px;
    height: 640px;
  }
  svg.links { position: absolute; inset: 0; width: 100%; height: 100%; }
  svg.links line { stroke: #1e4d66; stroke-width: 2; }
  .card {
    position: absolute;
    width: 210px;
    min-height: 108px;
    padding: 12px 14px;
    background: var(--card);
    border: 1px solid var(--cyan);
    border-radius: 14px;
    box-shadow: 0 0 18px rgba(90, 215, 255, 0.12);
  }
  .card.orange { border-color: var(--orange); box-shadow: 0 0 18px rgba(255, 154, 46, 0.16); }
  .card.orange .label { color: var(--orange); }
  .label { font-size: 16px; font-weight: 650; }
  .state {
    display: inline-block;
    margin-top: 6px;
    font-size: 13px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .detail { margin-top: 6px; color: var(--muted); font-size: 13px; }
  .card[data-state="up"] .state { color: var(--up); }
  .card[data-state="down"] .state { color: var(--down); }
  .card[data-state="locked"] .state { color: var(--locked); }
  .card[data-state="unknown"] .state { color: var(--unknown); }
  #bitcoin { left: 385px; top: 24px; }
  #channel { left: 385px; top: 196px; }
  #payer { left: 48px; top: 196px; }
  #invoice { left: 722px; top: 196px; }
  #nostr { left: 48px; top: 390px; }
  #aperture { left: 722px; top: 390px; }
  #origin { left: 722px; top: 520px; }
  button {
    margin-top: 12px;
    background: transparent;
    color: var(--cyan);
    border: 1px solid var(--cyan);
    border-radius: 999px;
    padding: 6px 14px;
    cursor: pointer;
  }
  @media (max-width: 860px) {
    .map { height: auto; display: grid; gap: 16px; padding: 0 16px 24px; }
    svg.links { display: none; }
    .card { position: static; width: auto; }
  }
</style>
</head>
<body>
<header>
  <h1>Agent Bitcoin</h1>
  <p>Infrastructure map. Read only. This page does not pay or open a channel.</p>
  <p id="meta">loading</p>
  <button type="button" id="refresh">Refresh</button>
</header>
<div class="map">
  <svg class="links" viewBox="0 0 980 640" aria-hidden="true">
    <line x1="490" y1="132" x2="490" y2="196"/>
    <line x1="258" y1="250" x2="385" y2="250"/>
    <line x1="595" y1="250" x2="722" y2="250"/>
    <line x1="153" y1="304" x2="153" y2="390"/>
    <line x1="827" y1="304" x2="827" y2="390"/>
    <line x1="258" y1="444" x2="722" y2="444"/>
    <line x1="827" y1="498" x2="827" y2="520"/>
  </svg>
  <article class="card" id="bitcoin" data-state="unknown"><div class="label">Bitcoin network</div><div class="state"></div><div class="detail"></div></article>
  <article class="card orange" id="channel" data-state="unknown"><div class="label">Lightning channel</div><div class="state"></div><div class="detail"></div></article>
  <article class="card orange" id="payer" data-state="unknown"><div class="label">Payer agent</div><div class="state"></div><div class="detail"></div></article>
  <article class="card orange" id="invoice" data-state="unknown"><div class="label">Invoice agent</div><div class="state"></div><div class="detail"></div></article>
  <article class="card" id="nostr" data-state="unknown"><div class="label">Nostr</div><div class="state"></div><div class="detail"></div></article>
  <article class="card" id="aperture" data-state="unknown"><div class="label">Aperture</div><div class="state"></div><div class="detail"></div></article>
  <article class="card" id="origin" data-state="unknown"><div class="label">Merchant origin</div><div class="state"></div><div class="detail"></div></article>
</div>
<footer><p>Listens on 127.0.0.1 only.</p></footer>
<script>
const STATES = ["up", "down", "locked", "unknown"];
async function load() {
  const meta = document.getElementById("meta");
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error("status HTTP " + response.status);
    const data = await response.json();
    meta.textContent = (data.revision || "unknown") + " · " + (data.network || "");
    for (const node of data.nodes || []) {
      const card = document.getElementById(node.id);
      if (!card) continue;
      const state = STATES.indexOf(node.state) >= 0 ? node.state : "unknown";
      card.dataset.state = state;
      card.querySelector(".state").textContent = state;
      card.querySelector(".detail").textContent = node.detail || "";
    }
  } catch (err) {
    meta.textContent = "status probe failed";
  }
}
document.getElementById("refresh").addEventListener("click", load);
load();
setInterval(load, 15000);
</script>
</body>
</html>
"""


def resolve_host(raw: str | None) -> str:
    """Accept only the loopback address. Never bind a public interface."""
    host = (
        raw if raw is not None else os.environ.get("DASHBOARD_HOST") or BIND_HOST
    ).strip()
    if host != BIND_HOST:
        raise SystemExit("dashboard listens on 127.0.0.1 only")
    return BIND_HOST


def resolve_port(raw: str | None = None) -> int:
    text = (
        raw
        if raw is not None
        else os.environ.get("DASHBOARD_PORT") or str(DEFAULT_PORT)
    )
    try:
        port = int(text)
    except ValueError as exc:
        raise SystemExit("DASHBOARD_PORT must be an integer") from exc
    if port == 10009 or port == 20009 or not 1 <= port <= 65535:
        raise SystemExit("dashboard does not bind that port")
    return port


def resolve_network(argv: list[str] | None = None) -> str:
    """Default mainnet. `--network regtest` or `--network signet` selects the lab."""
    parser = argparse.ArgumentParser(prog="agent_bitcoin.dashboard")
    parser.add_argument(
        "--network",
        default="mainnet",
        choices=("mainnet", "regtest", "signet"),
    )
    args = parser.parse_args([] if argv is None else argv)
    return network_name(args.network)


def _probe_failed(network: str) -> dict[str, object]:
    """Generic map. The exception text stays off this payload."""
    return {
        "revision": "unknown",
        "network": network,
        "bind": BIND_HOST,
        "nodes": [
            {
                "id": node_id,
                "label": label,
                "state": "unknown",
                "detail": "probe failed",
            }
            for node_id, label in _MAP_NODES
        ],
        "links": [
            ["bitcoin", "channel"],
            ["channel", "payer"],
            ["channel", "invoice"],
            ["payer", "nostr"],
            ["invoice", "nostr"],
            ["invoice", "aperture"],
            ["aperture", "origin"],
        ],
    }


def create_app(io: ProbeIO | None = None, network: str | None = None) -> FastAPI:
    probe = io or RealProbeIO()
    chosen = network_name(network)
    app = FastAPI(title="Agent Bitcoin infrastructure", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def map_page() -> str:
        return _PAGE

    @app.get("/api/status")
    def status() -> JSONResponse:
        try:
            payload = collect_status(probe, network=chosen)
        except Exception:  # noqa: BLE001 — generic payload; no exception text
            payload = _probe_failed(chosen)
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    return app


def serve(argv: list[str] | None = None) -> None:
    import uvicorn

    host = resolve_host(os.environ.get("DASHBOARD_HOST"))
    port = resolve_port()
    # docker exec lncli does not consult the SDK mainnet latch.
    # Do not set AGENT_BITCOIN_ALLOW_AUTOPAY or AGENT_BITCOIN_ALLOW_MAINNET here.
    network = resolve_network(sys.argv[1:] if argv is None else argv)
    uvicorn.run(create_app(network=network), host=host, port=port, log_level="info")
