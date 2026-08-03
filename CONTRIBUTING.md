# Contributing to Agent-Bitcoin

Thank you for considering contributing to Agent-Bitcoin!<br><br>

## Pull requests (default branch)

`main` is protected (public Free-tier ruleset). **Do not push commits directly to `main`.**

1. Create a branch and open a pull request
2. Wait for CI job **`lint-and-test`** to pass
3. Merge when green — **no second human approval is required** (solo maintainer)

Security reporting: [SECURITY.md](SECURITY.md). Operator GitHub settings: [docs/security-hardening.md](docs/security-hardening.md#github-repository-security-free-tier-public-repo).

## Development Setup

```bash
git clone https://github.com/gpu7/agent-bitcoin.git
cd agent-bitcoin
uv sync
