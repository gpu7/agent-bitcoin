## [23.1.0] - 2026-07-14

### Major Changes
- **Split architecture support**: AWS backend (`agent-payment-decision-lnd` + `bitcoind`) + Mac counterparty node
- **Persistent chain mode**: New `startup-aws.sh` (no aggressive reset) and `startup-aws-reset.sh` for full reset when needed
- **Improved startup scripts**: `startup-mac.sh` and `shutdown-mac.sh` for local testing
- **Better Docker Compose separation**: `docker-compose.regtest.aws.yml` and `docker-compose.regtest.mac.yml`

### Added
- Channel opening and Lightning payments between Mac and AWS nodes
- Automatic wallet detection (create vs unlock)
- Pre-warming and mining logic for faster startup
- TestPyPI publishing workflow

### Fixed
- Port binding and firewall issues on AWS (18443/9735)
- LND sync and "block height out of range" errors
- Wallet unlock reliability across restarts
- Docker service name and volume management

### Dependencies
- Updated to support latest Lightning Labs LND (v0.17.5-beta / v0.18.5-beta)

[Compare with previous version](https://github.com/gpu7/agent-bitcoin/compare/23.0.0...23.1.0)
