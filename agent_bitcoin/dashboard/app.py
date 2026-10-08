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
  .story {
    max-width: 1080px;
    margin: 16px auto 0;
    padding: 0 24px;
  }
  .story svg {
    width: 100%;
    max-width: 640px;
    height: auto;
    display: block;
    margin: 0 auto;
  }
  .story svg text { font-family: ui-sans-serif, system-ui, sans-serif; }
  #payment-marker {
    offset-path: path("M 70 46 L 290 46");
    offset-rotate: 0deg;
    animation: glide 4.8s linear infinite;
  }
  @keyframes glide {
    from { offset-distance: 0%; }
    to { offset-distance: 100%; }
  }
  @media (prefers-reduced-motion: reduce) {
    #payment-marker { animation: none; offset-distance: 0%; }
  }
  .story figcaption {
    margin: 2px 0 0;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
  }
  .story-rule {
    margin: 12px 0 0;
    border: 0;
    border-top: 1px solid #7d8794;
    width: 100%;
  }
  .map {
    position: relative;
    max-width: 1080px;
    margin: 18px auto 32px;
  }
  .groups {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: minmax(220px, 0.85fr) minmax(420px, 1.4fr) minmax(220px, 0.85fr);
    gap: 22px;
    padding: 0 24px 8px;
  }
  .group {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 14px 14px 16px;
    border: 1px solid rgba(90, 215, 255, 0.28);
    border-radius: 18px;
    background: transparent;
  }
  .group h2 {
    margin: 0;
    color: var(--cyan);
    font-size: 12px;
    font-weight: 650;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }
  .pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  svg.links {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    z-index: 0;
    pointer-events: none;
  }
  svg.links line { stroke: #1e4d66; stroke-width: 2; }
  .card {
    position: relative;
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
  button {
    margin-top: 12px;
    background: transparent;
    color: var(--cyan);
    border: 1px solid var(--cyan);
    border-radius: 999px;
    padding: 6px 14px;
    cursor: pointer;
  }
  button.pressed { opacity: 0.62; }
  @media (max-width: 860px) {
    .story { padding: 0 16px; }
    .groups { grid-template-columns: 1fr; padding: 0 16px 24px; }
    svg.links { display: none; }
  }
  @media (max-width: 520px) {
    .pair { grid-template-columns: 1fr; }
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
<figure class="story" id="agent-animation">
  <svg viewBox="0 0 360 128" width="360" height="128" role="img" aria-label="Agent 1 sends 100 sats to Agent 2 over one Lightning channel">
    <title>Two agents and one Lightning channel</title>
    <line x1="64" y1="46" x2="296" y2="46" stroke="#ff9a2e" stroke-width="6" stroke-opacity="0.22" stroke-linecap="round"/>
    <line x1="64" y1="46" x2="296" y2="46" stroke="#ff9a2e" stroke-width="2.5" stroke-linecap="round"/>
    <circle cx="46" cy="46" r="18" fill="#10192b" stroke="#5ad7ff" stroke-width="2"/>
    <circle cx="314" cy="46" r="18" fill="#10192b" stroke="#5ad7ff" stroke-width="2"/>
    <text x="46" y="84" text-anchor="middle" fill="#5ad7ff" font-size="13">Agent 1</text>
    <text x="46" y="100" text-anchor="middle" fill="#8b97ad" font-size="11">agent npub</text>
    <text x="314" y="84" text-anchor="middle" fill="#5ad7ff" font-size="13">Agent 2</text>
    <text x="314" y="100" text-anchor="middle" fill="#8b97ad" font-size="11">agent npub</text>
    <g id="payment-marker">
      <circle cy="-14" r="4.5" fill="#ff9a2e"/>
      <text y="-22" text-anchor="middle" fill="#ff9a2e" font-size="11">100 sats</text>
    </g>
  </svg>
  <figcaption>A picture of an agent-to-agent payment, not a live channel.</figcaption>
  <hr class="story-rule">
</figure>
<div class="map" id="map">
  <svg class="links" id="links" aria-hidden="true"></svg>
  <div class="groups">
    <section class="group" id="group-chain">
      <h2>Chain</h2>
      <article class="card" id="bitcoin" data-state="unknown"><div class="label">Bitcoin network</div><div class="state"></div><div class="detail"></div></article>
      <article class="card orange" id="channel" data-state="unknown"><div class="label">Lightning channel</div><div class="state"></div><div class="detail"></div></article>
    </section>
    <section class="group" id="group-agents">
      <h2>Agents</h2>
      <div class="pair">
        <article class="card orange" id="payer" data-state="unknown"><div class="label">Payer agent</div><div class="state"></div><div class="detail"></div></article>
        <article class="card orange" id="invoice" data-state="unknown"><div class="label">Invoice agent</div><div class="state"></div><div class="detail"></div></article>
      </div>
      <article class="card" id="nostr" data-state="unknown"><div class="label">Nostr</div><div class="state"></div><div class="detail"></div></article>
    </section>
    <section class="group" id="group-merchant">
      <h2>Merchant</h2>
      <article class="card" id="aperture" data-state="unknown"><div class="label">Aperture</div><div class="state"></div><div class="detail"></div></article>
      <article class="card" id="origin" data-state="unknown"><div class="label">Merchant origin</div><div class="state"></div><div class="detail"></div></article>
    </section>
  </div>
</div>
<footer><p>Listens on 127.0.0.1 only.</p></footer>
<script>
const STATES = ["up", "down", "locked", "unknown"];
const LINKS = [
  ["bitcoin", "channel"],
  ["channel", "payer"],
  ["channel", "invoice"],
  ["payer", "nostr"],
  ["invoice", "nostr"],
  ["invoice", "aperture"],
  ["aperture", "origin"]
];
let currentLinks = LINKS;
function drawLinks(pairs) {
  currentLinks = pairs && pairs.length ? pairs : LINKS;
  const svg = document.getElementById("links");
  const map = document.getElementById("map");
  if (!svg || !map || getComputedStyle(svg).display === "none") return;
  const origin = map.getBoundingClientRect();
  svg.setAttribute("viewBox", "0 0 " + origin.width + " " + origin.height);
  svg.replaceChildren();
  for (const pair of currentLinks) {
    const left = document.getElementById(pair[0]);
    const right = document.getElementById(pair[1]);
    if (!left || !right) continue;
    const a = left.getBoundingClientRect();
    const b = right.getBoundingClientRect();
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(a.left + a.width / 2 - origin.left));
    line.setAttribute("y1", String(a.top + a.height / 2 - origin.top));
    line.setAttribute("x2", String(b.left + b.width / 2 - origin.left));
    line.setAttribute("y2", String(b.top + b.height / 2 - origin.top));
    svg.appendChild(line);
  }
}
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
    drawLinks(data.links);
  } catch (err) {
    meta.textContent = "status probe failed";
    drawLinks(currentLinks);
  }
}
const refresh = document.getElementById("refresh");
refresh.addEventListener("click", () => {
  refresh.classList.add("pressed");
  window.setTimeout(() => refresh.classList.remove("pressed"), 180);
  load();
});
window.addEventListener("resize", () => drawLinks(currentLinks));
drawLinks(LINKS);
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
