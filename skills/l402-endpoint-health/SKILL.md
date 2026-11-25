---
name: l402 endpoint health
description: Checks an L402 /health path and a 402 challenge without completing it.
summary: Report HTTP status and whether a challenge has a macaroon and an invoice.
version: 1.0.0
tags: lightning, l402, health
keywords: l402, health, 402, parse_www_authenticate, agent-bitcoin
use_cases: Confirm an L402 endpoint is up before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# L402 endpoint health

Read an L402 endpoint with a GET. Do not complete a challenge.

Do not sign in to Agensi from this skill.

## Check

```python
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agent_bitcoin import parse_www_authenticate


def probe(url: str) -> tuple[int, str | None, bytes]:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read(512)
            header = response.headers.get("WWW-Authenticate")
            return response.status, header, body
    except HTTPError as exc:
        return exc.code, exc.headers.get("WWW-Authenticate"), exc.read(512)
```

The base URL is the one the user supplied. The local example is `http://127.0.0.1:8081`.

`GET {base}/health` should be status 200. Report that status and a short text body.

`GET {base}/paid/hello` should be status 402 Payment Required. Pass the `WWW-Authenticate` value to `parse_www_authenticate`. Report whether `macaroon` and `invoice` are non-empty. Do not print either value, the header, or the body of the 402.

## curl

When the SDK is not available:

```bash
curl -sS -o /dev/null -D - "$BASE/health"
curl -sS -o /dev/null -D - "$BASE/paid/hello"
```

Report the status line only. Do not copy the `WWW-Authenticate` value into the answer.

## What to keep private

Do not print wallet secrets, macaroons, preimages, or BOLT11 invoices.
