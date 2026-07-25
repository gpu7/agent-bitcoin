# Security Policy

## Supported Versions

| Version  | Supported          |
|:-------- |:------------------ |
| 24.0.0   | :white_check_mark: |
| < 24.0.0 | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please report it responsibly.

**Please do not report security vulnerabilities through public GitHub issues.**

### How to Report

Send a detailed report to:

**Email:** richardcaseyhpc@protonmail.com

Please include the following information in your report:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (if known)
- Affected version(s)

### Response Time

- We will acknowledge receipt of your report within **48 hours**.
- We aim to provide a full response within **7 business days**.

### Responsible Disclosure

We request that you:
- Do not publicly disclose the vulnerability until we have had time to address it.
- Give us reasonable time to fix the issue before publishing.

## Security Updates

Security fixes will be released as soon as possible and announced in the [CHANGELOG.md](CHANGELOG.md) and via GitHub Releases.

## Security Best Practices

### For everyone

- Always use the latest stable version
- Never expose private keys, seed phrases, macaroons, or RPC credentials
- Never commit `.env` files, key material, or wallet backups to version control
- Use strong, unique passwords for wallets and a password manager
- Treat any secret that has appeared in chat, tickets, or logs as compromised for high-value use

### For operators and integrators

- Configure secrets via environment variables or a secrets manager—not hard-coded source
- Restrict administrative, API, and RPC/ZMQ interfaces to trusted networks (not `0.0.0.0/0`)
- When operator IPs change, refresh firewall/security-group rules before relying on remote access
- Run nodes with least-privilege principles
- Keep host systems, Docker images, and dependencies updated (automatic security updates where appropriate)
- Prefer regtest (or testnet) until mainnet deployment is an explicit, reviewed decision
- Harden backend hosts (SSH key-only, minimal exposure of control planes) in addition to application controls
- Keep node stacks network-pinned (regtest compose/scripts must not silently target mainnet)
- Treat node RPC credentials and macaroons as secrets; use strong unique material outside isolated regtest labs

### What we do not publish

We document security posture at a high level. We do not publish operational secrets, private infrastructure details that enable abuse, or exploit write-ups in public docs.

---

**Thank you** for helping keep Agent-Bitcoin secure.
