#!/usr/bin/env python3
"""Optional xAI Grok how-to. L402 and the SDK pay Lightning without this.

Requires XAI_API_KEY in the environment. Never commit the key.
Uses grok-4-1-fast-reasoning (same default as PaymentDecisionAgent).
"""

from __future__ import annotations

import os
import sys

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_xai import ChatXAI

MODEL = "grok-4-1-fast-reasoning"
PROMPT = "Reply in one sentence: can a Lightning L402 client pay without an LLM?"


def main() -> int:
    key = (os.environ.get("XAI_API_KEY") or "").strip()
    if not key:
        print(
            "Missing XAI_API_KEY. Export it locally; never commit it. "
            "L402 still works without Grok.",
            file=sys.stderr,
        )
        return 1
    llm = ChatXAI(model=MODEL, api_key=key, temperature=0)
    msg = llm.invoke(
        [
            SystemMessage(content="One short sentence. Do not pay or request keys."),
            HumanMessage(content=PROMPT),
        ]
    )
    print(getattr(msg, "content", msg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
