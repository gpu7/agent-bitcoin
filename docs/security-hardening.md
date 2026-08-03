# Security hardening (Phase 6 — mainnet readiness)

**Audience:** Operator.
**Related:** [SECURITY.md](../SECURITY.md) · [mainnet-pilot.md](./mainnet-pilot.md) · [lnd-client.md](./lnd-client.md) · [daily-ops-signet.md](./daily-ops-signet.md)

**Goal:** Close lab habits that would be fatal with real funds. This is a checklist and policy doc — not a penetration test.

---

## Secrets inventory (keep offline)

Maintain this list in a **password manager**, not git.

| Secret | Where used | Rotate when |
|--------|------------|-------------|
| LND wallet password(s) | Mac + AWS unlock | Suspected leak; operator change |
| LND seed / cipher seed | Recovery | Never store in chat/AMI public |
| `AGENT_BITCOIN_API_KEY` | Backend HTTP | Leak, staff change, before mainnet pilot |
| AWS SSH key | Instance access | Compromise / key loss |
| AWS API keys (if any) | SG script, console | Quarterly or on leak |
| bitcoind RPC password | Compose (lab often weak) | **Must be unique strong** on mainnet |
| Exported macaroons | gRPC clients | After export to wrong host; prefer short-lived |
| AMI snapshots | AWS | Treat as containing encrypted wallet; **private only** |
| Spend ledger path | Daily caps | Low sensitivity; still private host |

**Rotation (API key example):**

```bash
openssl rand -hex 32   # new key
# set AGENT_BITCOIN_API_KEY on server; restart uvicorn
# revoke old key by not deploying it; update clients
```

---

## Network exposure (must-pass)

| Port / service | Lab OK? | Mainnet pilot |
|----------------|---------|-----------------|
| SSH 22 | Your IP /32 | Your IP /32 only |
| LND P2P (19735 signet / 9735 mainnet) | Peers you need | Peers you need; not world unless intentional |
| LND gRPC 10009 / host map 20009 / 30009 | Localhost or private | **Never** `0.0.0.0/0` |
| Backend 8000 | Localhost or private + key | **127.0.0.1** or private NIC + TLS reverse proxy |
| bitcoind RPC/ZMQ | Trusted only | Strong password; not public |

`./update-aws-sg-my-ip.sh` refreshes admin/Mac ports for your current IP. It must **not** open gRPC to the world. Review SG after changes:

```bash
aws ec2 describe-security-groups --group-ids "$SG_ID" --query 'SecurityGroups[0].IpPermissions'
```

---

## Lab vs mainnet credentials

| Item | Lab (regtest/signet) | Mainnet |
|------|----------------------|---------|
| bitcoind RPC user/pass | Often `lightning`/`lightning` | **Unique strong**; never reuse lab |
| Compose files | May document lab defaults | Separate compose/env; no committed secrets |
| Wallet seed | Lab disposable risk | New seed; offline backup |
| AMI | Private; still treat as wallet host | Private; encrypt; access-controlled |

Signet compose may keep lab RPC passwords for convenience. **Mainnet must not copy those values.**

---

## Backend bind and rate limit

Defaults (after Phase 6 code):

| Env | Default | Meaning |
|-----|---------|---------|
| `BACKEND_HOST` | `127.0.0.1` | Do not listen on all interfaces by default |
| `BACKEND_PORT` | `8000` | |
| `BACKEND_RATE_LIMIT_PER_MIN` | `60` | Per-client soft limit on mutating routes (`0` = off) |

```bash
export BACKEND_HOST=127.0.0.1
export BACKEND_PORT=8000
export AGENT_BITCOIN_API_KEY=...
# LND_* as needed
uv run uvicorn backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
```

For remote access: SSH tunnel or reverse proxy with TLS — not open `0.0.0.0:8000` on a public EIP.

---

## Macaroon / gRPC hygiene

- Export under `~/.lnd-export/…` with `chmod 600`
- Prefer **invoice** macaroon for receive-only agents (later)
- Admin macaroon = full control; never email or commit
- gitignore already blocks `*.macaroon`, `*.cert` patterns; also avoid `lnd-backups/` in git

---

## Git and local paths

Ensure these never land in commits:

- `.env`, seeds, macaroons, `~/lnd-backups/`, `~/.lnd-export/`
- Accidental scp artifacts (`ubuntu@…` files)
- AWS access keys, wallet passwords, Nostr `nsec` / weak passphrase material

```bash
git status   # clean of secrets before every push
```

### `git-secrets` (required operator tooling)

Use [git-secrets](https://github.com/awslabs/git-secrets) so commits and history are scanned for common credential patterns (especially AWS keys). Install once per developer machine that touches this repo; re-scan before mainnet prep or any backup that might include a clone of the tree.

**Install (macOS):**

```bash
brew install git-secrets
cd /path/to/agent-bitcoin   # repo root
```

**Hooks (recommended — blocks matching secrets at commit time):**

```bash
git secrets --install
git secrets --register-aws   # common AWS key patterns
```

`--install` wires pre-commit / commit-msg / prepare-commit-msg hooks for **this clone**. Run it again after a fresh clone. Hooks are local; they are not committed for other developers unless you document the install (this section).

**Scan working tree / staged files:**

```bash
git secrets --scan
```

**Scan entire history** (do this before a public mirror, AMI bake that includes `.git`, or long-lived backup of the repo):

```bash
git secrets --scan-history
```

**If a scan fails:** treat the hit as a real secret until proven otherwise. Do **not** “fix” by rewriting history casually on a shared branch without a rotation plan. Rotate the credential first, then scrub history only with an explicit operator decision (and force-push policy). Lab false positives (documented dummy keys in examples) can be allowlisted carefully with `git secrets --add --allowed …` — prefer fixing the example over broad allowlists.

Optional: add project-specific patterns for LND/macaroon-looking blobs if you find gaps; AWS register covers the most common cloud leak class.

### TruffleHog (required operator tooling — full git history)

Use [TruffleHog](https://github.com/trufflesecurity/trufflehog) as a deeper secret scan of the **entire git history** (entropy + detector verification). It complements `git-secrets` (fast pattern hooks): run both. Prefer a scan **before mainnet prep**, before publishing a mirror, or before any long-lived backup that includes `.git`.

**Install (macOS):**

```bash
brew install trufflehog
```

**Scan this repo’s history** (run from *outside* the repo directory — recommended by TruffleHog for `file://` paths):

```bash
# From *outside* the repo directory
trufflehog git file:///path/to/agent-bitcoin --results=verified,unknown
```

Replace `/path/to/agent-bitcoin` with the absolute path to your clone (example: `file:///Users/you/agent-bitcoin`).

| Flag / filter | Meaning |
|---------------|---------|
| `git file:///…` | Scan local git history via filesystem URL |
| `--results=verified,unknown` | Report verified findings and unknown (needs review); skips known false-positive classes when possible |

**How it differs from `git-secrets`:**

| Tool | Best for |
|------|----------|
| `git-secrets` | Pre-commit hooks; quick AWS-pattern scan of tree/history |
| TruffleHog | Broader detectors + verification over full history |

**If TruffleHog reports findings:** treat `verified` hits as real secrets until proven otherwise. Rotate first, then decide on history rewrite only with an explicit operator plan. Document any accepted false positives offline (password manager notes) — do not commit real secrets “justified” as lab fixtures.

You can also scan a remote clone without a local checkout (`trufflehog git https://github.com/gpu7/agent-bitcoin.git …`); prefer your clean local `main` so you know exactly which commit range was scanned.

---

## Operator checklist (Phase 6 exit)

- [ ] Secrets inventory exists offline (password manager)
- [ ] API key rotated at least once if it was ever shared in chat
- [ ] SG reviewed: no world-open gRPC; Mac IP current for P2P/admin
- [ ] Backend will use `BACKEND_HOST=127.0.0.1` (or private) for pilot
- [ ] Understand mainnet ≠ lab passwords
- [ ] AMI remains private
- [ ] Read [SECURITY.md](../SECURITY.md) reporting path
- [ ] `git-secrets` installed; hooks installed; `git secrets --register-aws` done
- [ ] `git secrets --scan` clean on working tree
- [ ] `git secrets --scan-history` run at least once (and before mainnet / full repo backup)
- [ ] TruffleHog installed; `trufflehog git file:///…/agent-bitcoin --results=verified,unknown` run at least once (and before mainnet / full repo backup)

---

## Incident quick path

1. Contain (stop backend, revoke SG, stop LND if needed)
2. Rotate API keys, SSH, and consider wallet password change
3. Revoke exported macaroons (bake new; delete old files)
4. Restore only from trusted backup ([lnd-backup-restore.md](./lnd-backup-restore.md))
5. Report product vulns privately (SECURITY.md email)

---

## Phase 6 deliverables

- [x] This hardening checklist
- [x] SECURITY.md mainnet readiness pointer
- [x] Backend default localhost + optional rate limit
- [x] gitignore backup/export paths
- [x] `git-secrets` install / scan / history-scan documented (operator tooling)
- [x] TruffleHog full-history scan documented (operator tooling)
- [ ] Operator completes checklist above before Phase 8
