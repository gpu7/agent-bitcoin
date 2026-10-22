"""ABT-L402-001 / ABT-L402-002 — offline L402 header + pay-and-retry."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_bitcoin.constants import DEFAULT_L402_PRICE_SATS
from agent_bitcoin.exceptions import PaymentError
from agent_bitcoin.l402.client import (
    L402Client,
    authorization_value,
    parse_www_authenticate,
)
from l402.origin import _payload, demo_pdf_bytes, demo_png_bytes, dispatch


def test_payment_result_captures_preimage() -> None:
    from agent_bitcoin.lightning import _payment_result_from_lncli_dict

    result = _payment_result_from_lncli_dict(
        {
            "payment_hash": "aa" * 32,
            "payment_preimage": "bb" * 32,
            "status": "SUCCEEDED",
            "value_sat": "1000",
        }
    )
    assert result.success is True
    assert result.preimage == "bb" * 32
    assert result.amount == 1000


def test_default_l402_price_matches_min_pay() -> None:
    from agent_bitcoin.constants import DEFAULT_MIN_PAYMENT_SATS

    assert DEFAULT_L402_PRICE_SATS == 100
    assert DEFAULT_MIN_PAYMENT_SATS == 100
    assert DEFAULT_L402_PRICE_SATS >= DEFAULT_MIN_PAYMENT_SATS


def test_paid_urls_default_to_100() -> None:
    from agent_bitcoin.l402.client import (
        FINANCE_L402_PRICE_SATS,
        expected_price_sats_for_url,
    )

    assert FINANCE_L402_PRICE_SATS == 100
    finance = "http://127.0.0.1:8081/paid/finance/mempool-feerate"
    nostr = "http://127.0.0.1:8081/paid/nostr/event-verify?x=1"
    security = "https://agent-bitcoin.net/paid/security/l402-challenge-inspect"
    lightning = "https://agent-bitcoin.net/paid/lightning/ln-channel-stats"
    bitcoin = "https://agent-bitcoin.net/paid/bitcoin/btc-fee-estimate"
    chain = "https://agent-bitcoin.net/paid/bitcoin/btc-chain-status"
    network = "https://agent-bitcoin.net/paid/bitcoin/btc-network-info"
    mempool = "https://agent-bitcoin.net/paid/bitcoin/btc-mempool-info"
    peer = "https://agent-bitcoin.net/paid/bitcoin/btc-peer-info"
    node = "https://agent-bitcoin.net/paid/lightning/ln-node-info"
    difficulty = "https://agent-bitcoin.net/paid/bitcoin/btc-difficulty"
    block_tip = "https://agent-bitcoin.net/paid/bitcoin/btc-block-tip"
    block_header = "https://agent-bitcoin.net/paid/bitcoin/btc-block-header"
    tx_summary = "https://agent-bitcoin.net/paid/bitcoin/btc-tx-summary"
    address_balance = "https://agent-bitcoin.net/paid/bitcoin/btc-address-balance"
    uptime = "https://agent-bitcoin.net/paid/bitcoin/btc-uptime"
    deployment = "https://agent-bitcoin.net/paid/bitcoin/btc-deployment-info"
    mining = "https://agent-bitcoin.net/paid/bitcoin/btc-mining-info"
    mempool_fees = "https://agent-bitcoin.net/paid/bitcoin/btc-mempool-fees"
    chain_tips = "https://agent-bitcoin.net/paid/bitcoin/btc-chain-tips"
    invoice_inspect = "https://agent-bitcoin.net/paid/lightning/ln-invoice-inspect"
    channel_liquidity = "https://agent-bitcoin.net/paid/lightning/ln-channel-liquidity"
    peer_status = "https://agent-bitcoin.net/paid/lightning/ln-peer-status"
    path_estimate = "https://agent-bitcoin.net/paid/lightning/ln-path-estimate"
    payment_status = "https://agent-bitcoin.net/paid/lightning/ln-payment-status"
    node_link = "https://agent-bitcoin.net/paid/nostr/nostr-node-link"
    channel_policy = "https://agent-bitcoin.net/paid/lightning/ln-channel-policy"
    invoice_create = "https://agent-bitcoin.net/paid/lightning/ln-invoice-create"
    preimage_verify = "https://agent-bitcoin.net/paid/lightning/ln-preimage-verify"
    pay_check = "https://agent-bitcoin.net/paid/lightning/ln-pay-check"
    node_card = "https://agent-bitcoin.net/paid/lightning/ln-node-card"
    address_resolve = "https://agent-bitcoin.net/paid/lightning/ln-address-resolve"
    liquidity_hint = "https://agent-bitcoin.net/paid/lightning/ln-payee-liquidity-hint"
    nip05_verify = "https://agent-bitcoin.net/paid/nostr/nip05-verify"
    route_options = "https://agent-bitcoin.net/paid/lightning/ln-route-options"
    invoice_amount = "https://agent-bitcoin.net/paid/lightning/ln-invoice-amount-check"
    profile_summary = "https://agent-bitcoin.net/paid/nostr/nostr-profile-summary"
    channel_reserve = (
        "https://agent-bitcoin.net/paid/lightning/ln-channel-reserve-check"
    )
    assert expected_price_sats_for_url(finance) == 100
    assert expected_price_sats_for_url(nostr) == 100
    assert expected_price_sats_for_url(security) == 100
    assert expected_price_sats_for_url(lightning) == 100
    assert expected_price_sats_for_url(bitcoin) == 100
    assert expected_price_sats_for_url(chain) == 100
    assert expected_price_sats_for_url(network) == 100
    assert expected_price_sats_for_url(mempool) == 100
    assert expected_price_sats_for_url(peer) == 100
    assert expected_price_sats_for_url(node) == 100
    assert expected_price_sats_for_url(difficulty) == 100
    assert expected_price_sats_for_url(block_tip) == 100
    assert expected_price_sats_for_url(block_header) == 100
    assert expected_price_sats_for_url(tx_summary) == 100
    assert expected_price_sats_for_url(address_balance) == 100
    assert expected_price_sats_for_url(uptime) == 100
    assert expected_price_sats_for_url(deployment) == 100
    assert expected_price_sats_for_url(mining) == 100
    assert expected_price_sats_for_url(mempool_fees) == 100
    assert expected_price_sats_for_url(chain_tips) == 100
    assert expected_price_sats_for_url(invoice_inspect) == 100
    assert expected_price_sats_for_url(channel_liquidity) == 100
    assert expected_price_sats_for_url(peer_status) == 100
    assert expected_price_sats_for_url(path_estimate) == 100
    assert expected_price_sats_for_url(payment_status) == 100
    assert expected_price_sats_for_url(node_link) == 100
    assert expected_price_sats_for_url(channel_policy) == 100
    assert expected_price_sats_for_url(invoice_create) == 100
    assert expected_price_sats_for_url(preimage_verify) == 100
    assert expected_price_sats_for_url(pay_check) == 100
    assert expected_price_sats_for_url(node_card) == 100
    assert expected_price_sats_for_url(address_resolve) == 100
    assert expected_price_sats_for_url(liquidity_hint) == 100
    assert expected_price_sats_for_url(nip05_verify) == 100
    assert expected_price_sats_for_url(route_options) == 100
    assert expected_price_sats_for_url(invoice_amount) == 100
    assert expected_price_sats_for_url(profile_summary) == 100
    assert expected_price_sats_for_url(channel_reserve) == 100
    assert expected_price_sats_for_url("http://127.0.0.1:8081/paid/hello") == 100
    assert expected_price_sats_for_url("http://127.0.0.1:8081/paid/report.pdf") == 100
    assert expected_price_sats_for_url("http://127.0.0.1:8081/paid/script.pdf") == 100
    assert expected_price_sats_for_url("http://127.0.0.1:8081/paid/badge.png") == 100
    assert (
        expected_price_sats_for_url("http://127.0.0.1:8081/paid/finance/fee-for-vsize")
        == 100
    )
    assert (
        expected_price_sats_for_url(
            "http://127.0.0.1:8081/paid/finance/ln-invoice-decode"
        )
        == 100
    )


def test_aperture_yaml_prices_are_100_and_health_is_free() -> None:
    root = Path(__file__).resolve().parents[1] / "l402"
    for name in (
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
        "aperture.mainnet.yaml",
    ):
        text = (root / name).read_text(encoding="utf-8")
        assert "price: 1000" not in text
        assert "price: 100" in text
        assert '- "^/health$"' in text
        assert '- "^/\\\\.well-known/l402-services$"' in text
        assert '- "^/\\\\.well-known/402index-verify\\\\.txt$"' in text


def test_parse_www_authenticate_aperture() -> None:
    header = 'L402 macaroon="abc+/=", invoice="lnbcrt10u1ptestinvoice"'
    challenge = parse_www_authenticate(header)
    assert challenge.macaroon == "abc+/="
    assert challenge.invoice == "lnbcrt10u1ptestinvoice"


def test_parse_www_authenticate_lsat_alias() -> None:
    header = 'LSAT macaroon="m", invoice="lnbcrt1x"'
    challenge = parse_www_authenticate(header)
    assert challenge.macaroon == "m"
    assert challenge.invoice.startswith("lnbcrt")


def test_header_map_joins_duplicate_www_authenticate() -> None:
    from email.message import Message

    from agent_bitcoin.l402.client import _header_map, _www_authenticate

    msg = Message()
    msg.add_header("Www-Authenticate", 'LSAT macaroon="m", invoice="ln1"')
    msg.add_header("Www-Authenticate", 'L402 macaroon="m", invoice="ln1"')
    mapped = _header_map(msg)
    header = _www_authenticate(mapped)
    assert header
    challenge = parse_www_authenticate(header)
    assert challenge.invoice == "ln1"


def test_parse_www_authenticate_rejects_junk() -> None:
    with pytest.raises(ValueError, match="unrecognized"):
        parse_www_authenticate("Bearer token")
    with pytest.raises(ValueError, match="missing"):
        parse_www_authenticate("")


def test_authorization_value() -> None:
    preimage = "ab" * 32
    assert authorization_value("mac", preimage) == f"L402 mac:{preimage}"
    with pytest.raises(ValueError, match="preimage"):
        authorization_value("mac", "zz")


def _yaml_double_quoted(value: str) -> str:
    """Undo the escapes in a YAML double-quoted scalar."""
    out: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            out.append("\\" if nxt == "\\" else nxt)
            index += 2
            continue
        out.append(value[index])
        index += 1
    return "".join(out)


def _aperture_http_status(path: str, text: str) -> int:
    """Status Aperture returns before the origin sees a non-free path."""
    import re

    for chunk in re.split(r"(?m)^  - name: ", text)[1:]:
        path_match = re.search(r'(?m)^    pathregexp: "(.*)"\s*$', chunk)
        price_match = re.search(r"(?m)^    price: (\d+)\s*$", chunk)
        if path_match is None or price_match is None:
            continue
        path_re = re.compile(_yaml_double_quoted(path_match.group(1)))
        if path_re.search(path) is None:
            continue
        whitelist = re.search(
            r"(?m)^    authwhitelistpaths:\n((?:      - .*\n)+)",
            chunk,
        )
        if whitelist is not None:
            for raw in re.findall(r'- "(.*)"', whitelist.group(1)):
                if re.compile(_yaml_double_quoted(raw)).search(path):
                    return 200
        if int(price_match.group(1)) == 0:
            return 200
        return 402
    return 404


def test_well_known_l402_services_is_public_json() -> None:
    root = Path(__file__).resolve().parents[1] / "l402"
    status, content_type, body = dispatch("/.well-known/l402-services")
    assert status == 200
    assert content_type == "application/json"
    doc = json.loads(body)
    assert doc["services"] == [
        {
            "url": "https://agent-bitcoin.net/paid/finance/btc-usd",
            "name": "agent-bitcoin: btc-usd",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin price in USD. Current BTC-USD rate and sats per USD from a public source. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/finance/mempool-feerate",
            "name": "agent-bitcoin: mempool-feerate",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin mempool fee rates. Sat/vB bands for fast, medium, and slow confirmation. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/finance/mempool-backlog",
            "name": "agent-bitcoin: mempool-backlog",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin mempool backlog. Transaction count, virtual size, and total fee. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/finance/fee-for-vsize",
            "name": "agent-bitcoin: fee-for-vsize",
            "method": "GET",
            "price_sats": 100,
            "description": "Fee in sats for a given virtual size. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/finance/confirm-target",
            "name": "agent-bitcoin: confirm-target",
            "method": "GET",
            "price_sats": 100,
            "description": "Map a confirmation wait time or band to sat/vB. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/finance/ln-invoice-decode",
            "name": "agent-bitcoin: ln-invoice-decode",
            "method": "POST",
            "price_sats": 100,
            "description": "Parse a Lightning BOLT11 invoice. Returns amount, expiry, and payee. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/finance/ln-invoice-preflight",
            "name": "agent-bitcoin: ln-invoice-preflight",
            "method": "POST",
            "price_sats": 100,
            "description": "Check whether a Lightning invoice is safe to pay. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/finance/ln-path-fee-hint",
            "name": "agent-bitcoin: ln-path-fee-hint",
            "method": "POST",
            "price_sats": 100,
            "description": "First-path fee hint from the operator LND. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/finance/btc-address-validate",
            "name": "agent-bitcoin: btc-address-validate",
            "method": "POST",
            "price_sats": 100,
            "description": "Check a Bitcoin address. Returns network and type, or a short reason if invalid. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-fee-estimate",
            "name": "agent-bitcoin: btc-fee-estimate",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core estimatesmartfee for 1, 3, and 6 blocks, in sats per vbyte. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-chain-status",
            "name": "agent-bitcoin: btc-chain-status",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core chain height, sync progress, and prune state from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-network-info",
            "name": "agent-bitcoin: btc-network-info",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core version, protocol, and connection counts from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-mempool-info",
            "name": "agent-bitcoin: btc-mempool-info",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core mempool size, memory, and minimum fee from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-peer-info",
            "name": "agent-bitcoin: btc-peer-info",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core peer count and a short address list from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-difficulty",
            "name": "agent-bitcoin: btc-difficulty",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core difficulty, chainwork, and blocks until the next retarget from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-block-tip",
            "name": "agent-bitcoin: btc-block-tip",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core tip height, block hash, and median time from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-block-header",
            "name": "agent-bitcoin: btc-block-header",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core block header for one height from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-address-balance",
            "name": "agent-bitcoin: btc-address-balance",
            "method": "POST",
            "price_sats": 100,
            "description": "Bitcoin Core confirmed UTXO balance for one address from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-uptime",
            "name": "agent-bitcoin: btc-uptime",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core uptime and version from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-mempool-fees",
            "name": "agent-bitcoin: btc-mempool-fees",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core mempool minimum fee and fee bands from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/bitcoin/btc-chain-tips",
            "name": "agent-bitcoin: btc-chain-tips",
            "method": "GET",
            "price_sats": 100,
            "description": "Bitcoin Core chain tips from the operator bitcoind. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/lightning/ln-invoice-inspect",
            "name": "agent-bitcoin: ln-invoice-inspect",
            "method": "POST",
            "price_sats": 100,
            "description": "LND decode of one BOLT11 invoice. Read-only. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/lightning/ln-path-estimate",
            "name": "agent-bitcoin: ln-path-estimate",
            "method": "POST",
            "price_sats": 100,
            "description": "LND route estimate for one destination. Does not pay. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/nostr/nostr-node-link",
            "name": "agent-bitcoin: nostr-node-link",
            "method": "POST",
            "price_sats": 100,
            "description": "Public Nostr npub and whether it matches this node's Lightning id. No nsec. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/nostr/nip05-verify",
            "name": "agent-bitcoin: nip05-verify",
            "method": "POST",
            "price_sats": 100,
            "description": "Check a NIP-05 name against an npub. No nsec. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/nostr/nostr-profile-summary",
            "name": "agent-bitcoin: nostr-profile-summary",
            "method": "POST",
            "price_sats": 100,
            "description": "Short public Nostr profile summary. No nsec and no nip05 check. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/nostr/event-verify",
            "name": "agent-bitcoin: event-verify",
            "method": "POST",
            "price_sats": 100,
            "description": "Check a Nostr event id and signature locally. No relay. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/nostr/npub-decode",
            "name": "agent-bitcoin: npub-decode",
            "method": "POST",
            "price_sats": 100,
            "description": "Decode a Nostr npub, note, nprofile, or nevent to hex. Rejects nsec. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/lightning/ln-preimage-verify",
            "name": "agent-bitcoin: ln-preimage-verify",
            "method": "POST",
            "price_sats": 100,
            "description": "SHA-256 check that a preimage matches a payment hash. No LND. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/lightning/ln-pay-check",
            "name": "agent-bitcoin: ln-pay-check",
            "method": "POST",
            "price_sats": 100,
            "description": "Decide whether one invoice or destination is payable. Does not pay. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/lightning/ln-address-resolve",
            "name": "agent-bitcoin: ln-address-resolve",
            "method": "POST",
            "price_sats": 100,
            "description": "Read a Lightning address pay range. Does not request an invoice. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/lightning/ln-route-options",
            "name": "agent-bitcoin: ln-route-options",
            "method": "POST",
            "price_sats": 100,
            "description": "LND route options for one destination. Does not pay. Lightning L402.",
        },
        {
            "url": "https://agent-bitcoin.net/paid/lightning/ln-invoice-amount-check",
            "name": "agent-bitcoin: ln-invoice-amount-check",
            "method": "POST",
            "price_sats": 100,
            "description": "LND check of whether an invoice amount is open or fixed. Read-only. Lightning L402.",
        },
    ]
    paid = (
        "/paid/hello",
        "/paid/finance/btc-usd",
        "/paid/report.pdf",
        "/paid/nostr/npub-decode",
        "/paid/security/l402-challenge-inspect",
        "/paid/lightning/ln-channel-stats",
        "/paid/lightning/ln-node-info",
        "/paid/bitcoin/btc-fee-estimate",
        "/paid/bitcoin/btc-chain-status",
        "/paid/bitcoin/btc-network-info",
        "/paid/bitcoin/btc-mempool-info",
        "/paid/bitcoin/btc-peer-info",
        "/paid/bitcoin/btc-difficulty",
        "/paid/bitcoin/btc-block-tip",
        "/paid/bitcoin/btc-block-header",
        "/paid/bitcoin/btc-tx-summary",
        "/paid/bitcoin/btc-address-balance",
        "/paid/bitcoin/btc-uptime",
        "/paid/bitcoin/btc-deployment-info",
        "/paid/bitcoin/btc-mining-info",
        "/paid/bitcoin/btc-mempool-fees",
        "/paid/bitcoin/btc-chain-tips",
        "/paid/lightning/ln-invoice-inspect",
        "/paid/lightning/ln-channel-liquidity",
        "/paid/lightning/ln-peer-status",
        "/paid/lightning/ln-path-estimate",
        "/paid/lightning/ln-payment-status",
        "/paid/lightning/ln-channel-policy",
        "/paid/lightning/ln-invoice-create",
        "/paid/lightning/ln-preimage-verify",
        "/paid/lightning/ln-pay-check",
        "/paid/lightning/ln-node-card",
        "/paid/lightning/ln-address-resolve",
        "/paid/lightning/ln-payee-liquidity-hint",
        "/paid/lightning/ln-route-options",
        "/paid/lightning/ln-invoice-amount-check",
        "/paid/lightning/ln-channel-reserve-check",
        "/paid/nostr/nostr-node-link",
        "/paid/nostr/nip05-verify",
        "/paid/nostr/nostr-profile-summary",
    )
    for name in (
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
        "aperture.mainnet.yaml",
    ):
        text = (root / name).read_text(encoding="utf-8")
        assert _aperture_http_status("/.well-known/l402-services", text) == 200
        assert _aperture_http_status("/.well-known/402index-verify.txt", text) == 200
        assert _aperture_http_status("/health", text) == 200
        for path in paid:
            assert _aperture_http_status(path, text) == 402


def test_402index_verify_file_is_plain_text() -> None:
    token = b"33fc5253f7b8faf9d350dc2e7bb9ddf3aaaffc78954467520e7b2bbd86296016"
    status, content_type, body = dispatch("/.well-known/402index-verify.txt")
    assert status == 200
    assert content_type == "text/plain"
    assert body.strip() == token
    status, content_type, _body = dispatch(
        "/.well-known/402index-verify.txt", method="POST"
    )
    assert status == 405
    assert content_type == "application/json"


def test_origin_paths() -> None:
    status, body = _payload("/health")
    assert status == 200
    assert body["ok"] is True
    status, body = _payload("/paid/hello")
    assert status == 200
    assert body["service"] == "l402-demo"
    assert body["msg"] == "hello"
    status, _ = _payload("/other")
    assert status == 404


def test_origin_pdf_report() -> None:
    status, content_type, body = dispatch("/paid/report.pdf")
    assert status == 200
    assert content_type == "application/pdf"
    assert body.startswith(b"%PDF-1.4")
    assert b"%%EOF" in body
    assert b"agent-bitcoin L402 demo report" in body
    assert b"paid file download worked" in body


def test_demo_pdf_includes_network() -> None:
    pdf = demo_pdf_bytes("mainnet")
    assert b"network: mainnet" in pdf


def test_origin_png_badge() -> None:
    status, content_type, body = dispatch("/paid/badge.png")
    assert status == 200
    assert content_type == "image/png"
    assert body.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IEND" in body[-12:]
    assert body[12:16] == b"IHDR"
    width = int.from_bytes(body[16:20], "big")
    height = int.from_bytes(body[20:24], "big")
    assert width == 560
    assert height == 200


def test_demo_png_changes_with_network() -> None:
    assert demo_png_bytes("mainnet") != demo_png_bytes("regtest")
    assert demo_png_bytes("mainnet").startswith(b"\x89PNG")


def test_origin_network_from_env(monkeypatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "signet")
    _, body = _payload("/paid/hello")
    assert body["network"] == "signet"
    monkeypatch.setenv("L402_NETWORK", "mainnet")
    _, body = _payload("/paid/hello")
    assert body["network"] == "mainnet"


def _payer(preimage: str = "cd" * 32) -> MagicMock:
    payer = MagicMock()
    payer.min_payment_sats = 1000
    payer.lnd.decode_pay_req.return_value = {"num_satoshis": "1000"}
    payer.pay_invoice.return_value = MagicMock(
        success=True, preimage=preimage, status="SUCCEEDED"
    )
    return payer


def test_fetch_pays_on_402_and_retries(clear_payment_env) -> None:
    payer = _payer()
    header = 'L402 macaroon="MAC", invoice="lnbcrt1inv"'
    client = L402Client(payer, expected_price_sats=1000)

    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.side_effect = [
            (402, {"WWW-Authenticate": header}, b"pay"),
            (200, {"Content-Type": "application/json"}, b'{"ok": true}'),
        ]
        resp = client.fetch("http://example.test/paid/hello")

    assert resp.status_code == 200
    assert resp.paid is True
    assert resp.json()["ok"] is True
    payer.pay_invoice.assert_called_once()
    auth_call = mock_get.call_args_list[1]
    got_auth = auth_call.kwargs.get("auth")
    if got_auth is None and len(auth_call.args) > 1:
        got_auth = auth_call.args[1]
    assert got_auth == f"L402 MAC:{'cd' * 32}"


def test_fetch_passthrough_without_402(clear_payment_env) -> None:
    payer = _payer()
    client = L402Client(payer)
    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.return_value = (200, {}, b'{"ok": true, "service": "l402-demo"}')
        resp = client.fetch("http://example.test/health")
    assert resp.status_code == 200
    assert resp.paid is False
    payer.pay_invoice.assert_not_called()


def test_fetch_rejects_wrong_price(clear_payment_env) -> None:
    payer = _payer()
    payer.lnd.decode_pay_req.return_value = {"num_satoshis": "2000"}
    client = L402Client(payer, expected_price_sats=1000)
    header = 'L402 macaroon="MAC", invoice="lnbcrt1inv"'
    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.return_value = (402, {"WWW-Authenticate": header}, b"")
        with pytest.raises(ValueError, match="expected price"):
            client.fetch("http://example.test/paid/hello")
    payer.pay_invoice.assert_not_called()


def test_fetch_rejects_below_minimum(clear_payment_env) -> None:
    payer = _payer()
    payer.lnd.decode_pay_req.return_value = {"num_satoshis": "21"}
    client = L402Client(payer, expected_price_sats=1000)
    header = 'L402 macaroon="MAC", invoice="lnbcrt1inv"'
    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.return_value = (402, {"WWW-Authenticate": header}, b"")
        with pytest.raises(ValueError, match="below minimum"):
            client.fetch("http://example.test/paid/hello")
    payer.pay_invoice.assert_not_called()


def test_fetch_post_retries_same_body(clear_payment_env) -> None:
    payer = _payer()
    header = 'L402 macaroon="MAC", invoice="lnbcrt1inv"'
    client = L402Client(payer, expected_price_sats=1000)
    payload = {"dest_pubkey": "02" + ("ab" * 32), "amount_sats": 1000}

    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.side_effect = [
            (402, {"WWW-Authenticate": header}, b"pay"),
            (200, {"Content-Type": "application/json"}, b'{"ok": true}'),
        ]
        resp = client.fetch(
            "http://example.test/paid/finance/ln-path-fee-hint",
            method="POST",
            json_body=payload,
        )

    assert resp.status_code == 200
    assert resp.paid is True
    assert mock_get.call_count == 2
    for call in mock_get.call_args_list:
        assert call.kwargs.get("method") == "POST"
        assert call.kwargs.get("data") == json.dumps(payload).encode("utf-8")


def test_fetch_rejects_failed_pay(clear_payment_env) -> None:
    payer = _payer()
    payer.pay_invoice.return_value = MagicMock(success=False, status="FAILED")
    header = 'L402 macaroon="MAC", invoice="lnbcrt1inv"'
    client = L402Client(payer, expected_price_sats=1000)
    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.return_value = (402, {"WWW-Authenticate": header}, b"")
        with pytest.raises(PaymentError, match="failed"):
            client.fetch("http://example.test/paid/hello")
