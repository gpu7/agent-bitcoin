"""Parse and serialize ``nostr+walletconnect://`` connection URIs (NIP-47)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from agent_bitcoin.nwc.errors import NWCURIError

NWC_SCHEME = "nostr+walletconnect"


def _is_hex(value: str, length: int) -> bool:
    if len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class NWCConnectionURI:
    """Parsed NIP-47 connection string.

    The URI embeds the **client** secret and the **wallet service** public key.
    Agents store this string; they do not need LND macaroons.
    """

    wallet_pubkey: str
    relays: tuple[str, ...]
    secret: str
    lud16: str | None = None
    extra: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _is_hex(self.wallet_pubkey, 64):
            raise NWCURIError(
                "wallet pubkey must be 32-byte hex (64 characters), "
                f"got length {len(self.wallet_pubkey)}"
            )
        if not _is_hex(self.secret, 64):
            raise NWCURIError(
                "secret must be 32-byte hex (64 characters), "
                f"got length {len(self.secret)}"
            )
        if not self.relays:
            raise NWCURIError("at least one relay= query parameter is required")

    def to_uri(self) -> str:
        """Serialize back to a connection string."""
        pairs: list[tuple[str, str]] = [("relay", r) for r in self.relays]
        pairs.append(("secret", self.secret))
        if self.lud16:
            pairs.append(("lud16", self.lud16))
        for key, values in sorted(self.extra.items()):
            for v in values:
                pairs.append((key, v))
        query = urlencode(pairs, quote_via=quote, safe=":/")
        return f"{NWC_SCHEME}://{self.wallet_pubkey}?{query}"


def parse_nwc_uri(uri: str) -> NWCConnectionURI:
    """Parse a ``nostr+walletconnect://`` URI.

    Raises:
        NWCURIError: on missing scheme, secret, relay, or invalid hex keys.
    """
    raw = (uri or "").strip()
    if not raw:
        raise NWCURIError("empty NWC URI")

    # urlparse treats nostr+walletconnect as scheme when written correctly
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme != NWC_SCHEME:
        raise NWCURIError(f"unsupported scheme {scheme!r}; expected {NWC_SCHEME!r}")

    wallet_pubkey = (parsed.netloc or parsed.path.lstrip("/")).strip()
    if not wallet_pubkey:
        raise NWCURIError("missing wallet service pubkey in URI host")

    qs = parse_qs(parsed.query, keep_blank_values=False)
    relays = tuple(unquote(r) for r in qs.get("relay", []) if r)
    secrets = qs.get("secret", [])
    if not secrets:
        raise NWCURIError("missing required secret= query parameter")
    secret = secrets[0].strip()
    lud16_list = qs.get("lud16", [])
    lud16 = unquote(lud16_list[0]) if lud16_list else None

    known = {"relay", "secret", "lud16"}
    extra: dict[str, tuple[str, ...]] = {}
    for key, values in qs.items():
        if key in known:
            continue
        extra[key] = tuple(unquote(v) for v in values)

    return NWCConnectionURI(
        wallet_pubkey=wallet_pubkey.lower(),
        relays=relays,
        secret=secret.lower(),
        lud16=lud16,
        extra=extra,
    )


def build_nwc_uri(
    wallet_pubkey: str,
    *,
    secret: str,
    relays: Sequence[str],
    lud16: str | None = None,
) -> str:
    """Build a connection URI from parts (validates via :class:`NWCConnectionURI`)."""
    return NWCConnectionURI(
        wallet_pubkey=wallet_pubkey.strip().lower(),
        relays=tuple(relays),
        secret=secret.strip().lower(),
        lud16=lud16,
    ).to_uri()
