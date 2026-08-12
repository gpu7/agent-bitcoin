"""Unit tests for NWC connection URI parse/serialize."""

from __future__ import annotations

import pytest

from agent_bitcoin.nwc import NWCURIError, build_nwc_uri, parse_nwc_uri

# Example from NIP-47 (public sample values)
EXAMPLE = (
    "nostr+walletconnect://"
    "b889ff5b1513b641e2a139f661a661364979c5beee91842f8f0ef42ab558e9d4"
    "?relay=wss%3A%2F%2Frelay.damus.io"
    "&secret=71a8c14c1407c113601079c4302dab36460f0ccd0ad506f1f2dc73b5100e4f3c"
)


def test_parse_nip47_example() -> None:
    conn = parse_nwc_uri(EXAMPLE)
    assert (
        conn.wallet_pubkey
        == "b889ff5b1513b641e2a139f661a661364979c5beee91842f8f0ef42ab558e9d4"
    )
    assert conn.relays == ("wss://relay.damus.io",)
    assert (
        conn.secret
        == "71a8c14c1407c113601079c4302dab36460f0ccd0ad506f1f2dc73b5100e4f3c"
    )
    assert conn.lud16 is None


def test_round_trip_build_parse() -> None:
    uri = build_nwc_uri(
        "b889ff5b1513b641e2a139f661a661364979c5beee91842f8f0ef42ab558e9d4",
        secret="71a8c14c1407c113601079c4302dab36460f0ccd0ad506f1f2dc73b5100e4f3c",
        relays=["wss://relay.example.com", "wss://relay2.example.com"],
        lud16="user@example.com",
    )
    conn = parse_nwc_uri(uri)
    assert len(conn.relays) == 2
    assert conn.lud16 == "user@example.com"
    # re-serialize still parses
    again = parse_nwc_uri(conn.to_uri())
    assert again.wallet_pubkey == conn.wallet_pubkey
    assert again.secret == conn.secret


def test_missing_secret() -> None:
    bad = (
        "nostr+walletconnect://"
        "b889ff5b1513b641e2a139f661a661364979c5beee91842f8f0ef42ab558e9d4"
        "?relay=wss://relay.damus.io"
    )
    with pytest.raises(NWCURIError, match="secret"):
        parse_nwc_uri(bad)


def test_missing_relay() -> None:
    bad = (
        "nostr+walletconnect://"
        "b889ff5b1513b641e2a139f661a661364979c5beee91842f8f0ef42ab558e9d4"
        "?secret=71a8c14c1407c113601079c4302dab36460f0ccd0ad506f1f2dc73b5100e4f3c"
    )
    with pytest.raises(NWCURIError, match="relay"):
        parse_nwc_uri(bad)


def test_bad_scheme() -> None:
    with pytest.raises(NWCURIError, match="scheme"):
        parse_nwc_uri("https://example.com/?secret=aa&relay=wss://r")


def test_short_pubkey() -> None:
    with pytest.raises(NWCURIError, match="pubkey"):
        parse_nwc_uri(
            "nostr+walletconnect://abcd"
            "?relay=wss://r"
            "&secret=71a8c14c1407c113601079c4302dab36460f0ccd0ad506f1f2dc73b5100e4f3c"
        )
