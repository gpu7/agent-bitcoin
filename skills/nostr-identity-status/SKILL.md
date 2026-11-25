---
name: nostr identity status
description: Reports the local Nostr public identity from public key files only.
summary: Show whether a key directory exists and print a short and full npub.
version: 1.0.0
tags: nostr, identity, npub
keywords: npub, short_npub, nostr-poc, agent-bitcoin
use_cases: Report a local Nostr public identity before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Nostr identity status

Read public Nostr identity files with the agent-bitcoin SDK. Read public files only. Do not generate keys and do not change files.

Do not sign in to Agensi from this skill.

## Check

```python
import os
from pathlib import Path

from agent_bitcoin.dashboard.npub import short_npub

candidates = []
if os.environ.get("NOSTR_POC_DIR"):
    candidates.append(Path(os.environ["NOSTR_POC_DIR"]))
candidates.extend([Path(".nostr-poc"), Path(".nostr-poc-mainnet")])
```

`default_npub_dir()` is the checkout path for `.nostr-poc-mainnet`. The list above also checks `NOSTR_POC_DIR` and `.nostr-poc`.

For each candidate, report whether the directory exists and whether any `*.pub.json` file is present. Usual names are `alice.pub.json` and `bob.pub.json`. For each public file, read the `npub` string. When `short_npub` returns a value other than `agent npub`, report that short form (`npub1…` plus the last four characters) and the full npub. When it returns `agent npub`, skip that file and do not print the raw field.

Do not open `*.enc.json`. Do not print a value that does not start with `npub1`.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
