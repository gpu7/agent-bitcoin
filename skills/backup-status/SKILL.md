---
name: backup status
description: Reports whether a channel backup file is present and how old it is.
summary: Check backup metadata only. Do not open the file.
version: 1.0.0
tags: lightning, backup, status
keywords: channel.backup, lnd-backups, agent-bitcoin
use_cases: See if a channel backup file is present before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Backup status

Read channel backup metadata. Do not write a backup file and do not copy one. Do not print file bytes.

Do not sign in to Agensi from this skill.

## Check

```python
from pathlib import Path

root = Path.home() / "lnd-backups"
names = {"channel.backup", "channel-all.backup"}
```

Report whether `root` exists. If it does, report whether any matching file exists, that file's `st_mtime`, and the age in days and hours. Use the newest match. Do not open the file.

Inside the regtest container, metadata only:

```bash
docker exec agent-payment-decision-lnd stat -c '%Y %s' /home/lnd/.lnd/data/chain/bitcoin/regtest/channel.backup
```

`%Y` is the modification time in unix seconds. `%s` is the size in bytes. A missing file is reported as absent. This `stat` does not need an unlocked wallet. If a later `lncli` call fails with `wallet locked`, stop and say the wallet is locked.

There is no SDK helper for this check.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
