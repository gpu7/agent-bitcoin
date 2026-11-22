# Agensi public buyer check

Listing: [agent to agent lightning payment](https://www.agensi.io/skills/agent-to-agent-lightning-payment).

The check follows that page. It does not include the paid skill file, and it does not start LND, Docker, or a regtest chain.

## What the listing tells a buyer

| Listing step | What this check does |
|---|---|
| Connect an agent to `https://mcp.agensi.io/mcp/auth`, sign in, and click Allow | Not automated. The page requires an interactive sign-in. |
| Python 3.10+ and `pip install agent-bitcoin` | `--phase install` uses a new virtualenv and installs this package with pip. |
| Unlocked LND node | `--phase pay` uses a node the operator already unlocked. The script does not create one. |
| `AGENT_BITCOIN_ALLOW_MAINNET` for mainnet | The script does not set this. A mainnet pay without it fails with the SDK's own error. |
| SDK method `agent_bitcoin.pay_invoice` | `--phase install` calls that name with no invoice and prints the traceback. |
| Create or fetch an invoice, pay, return a hash | `--phase pay` creates a 500 sat invoice, pays it, and requires status `SUCCEEDED` plus a payment hash. |

The worked example on the listing is 500 sats. The pay phase uses that amount.

## Install phase

From a clean checkout:

```bash
python3 -m venv /tmp/agensi-buyer
/tmp/agensi-buyer/bin/pip install --upgrade pip
/tmp/agensi-buyer/bin/pip install .
/tmp/agensi-buyer/bin/python tests/deployment/agensi_public_buyer.py --phase install
```

`pip install .` is the same package the listing names (`agent-bitcoin`), built from this commit. The virtualenv has no dev extras. Success means the import worked. The traceback from `agent_bitcoin.pay_invoice()` is the text a buyer would see; the install phase still exits 0 after printing it.

Pull requests run this phase in `.github/workflows/agensi-public-buyer.yml`. The default `pytest` run does not collect the script.

## Pay phase

Manual. The operator supplies the unlocked LND node the listing requires.

```bash
/tmp/agensi-buyer/bin/python tests/deployment/agensi_public_buyer.py --phase pay
```

Success prints `status=SUCCEEDED`, `success=True`, and `payment_hash=present`. The hash, the invoice, and the preimage are not printed. Any exception is printed in full and the process exits 1.

GitHub can start the same phase with `workflow_dispatch` and phase `pay`. A hosted runner has no LND node, so that run fails with the connection error a buyer would see. It is not a pull-request check.
