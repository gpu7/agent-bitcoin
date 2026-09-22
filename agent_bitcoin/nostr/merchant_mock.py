"""Localhost mock relay process for the merchant demo (``--offline-bus``).

Not a public relay and not a file bus. Binds 127.0.0.1 only.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(
            "usage: python -m agent_bitcoin.nostr.merchant_mock PORT", file=sys.stderr
        )
        return 2
    from agent_bitcoin.nostr.merchant_coord import serve_forever

    serve_forever(int(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
