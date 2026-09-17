#!/usr/bin/env python3
"""Optional local Ollama how-to. Does not use XAI_API_KEY. No LND.

Default: http://127.0.0.1:11434  model llama3.2
  ollama pull llama3.2
  ollama serve   # if not already running
"""

from __future__ import annotations

import os
import sys

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.2"
PROMPT = "Reply in one sentence: can a Lightning L402 client pay without an LLM?"


def main() -> int:
    host = (os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
    model = os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
    llm = ChatOllama(model=model, base_url=host, temperature=0)
    try:
        msg = llm.invoke([HumanMessage(content=PROMPT)])
    except Exception as exc:
        print(
            f"Ollama not reachable or model missing ({host}, {model}). "
            f"Start Ollama and run: ollama pull {model}\n{type(exc).__name__}",
            file=sys.stderr,
        )
        return 1
    print(getattr(msg, "content", msg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
