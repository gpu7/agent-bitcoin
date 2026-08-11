#!/usr/bin/env bash
# Patch lndclient router_client.go payInvoice to set TimeoutSeconds for SendPaymentV2.
set -euo pipefail
FILE="${1:?path to router_client.go}"

if grep -q 'TimeoutSeconds:' "$FILE"; then
  # Already has some TimeoutSeconds assignments; still ensure payInvoice block is fixed.
  :
fi

python3 - "$FILE" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path).read()
# Match the payInvoice SendPaymentRequest literal that omits TimeoutSeconds.
old = """\treq := &routerrpc.SendPaymentRequest{
\t\tFeeLimitSat:       int64(maxFee),
\t\tPaymentRequest:    invoice,
\t\tDestCustomRecords: customRecords,
\t}"""
new = """\treq := &routerrpc.SendPaymentRequest{
\t\tFeeLimitSat:       int64(maxFee),
\t\tPaymentRequest:    invoice,
\t\tDestCustomRecords: customRecords,
\t\t// LND requires timeout_seconds > 0 (see routerrpc router_backend).
\t\tTimeoutSeconds:    60,
\t}"""
if old not in text:
    # try spaces-only variant
    old2 = old.replace('\t', '    ')
    new2 = new.replace('\t', '    ')
    if old2 in text:
        text = text.replace(old2, new2, 1)
    else:
        # broader regex
        pat = re.compile(
            r'req := &routerrpc\.SendPaymentRequest\{\s*'
            r'FeeLimitSat:\s*int64\(maxFee\),\s*'
            r'PaymentRequest:\s*invoice,\s*'
            r'DestCustomRecords:\s*customRecords,\s*'
            r'\}',
            re.M,
        )
        m = pat.search(text)
        if not m:
            sys.stderr.write("ERROR: could not find payInvoice SendPaymentRequest block to patch\n")
            sys.exit(1)
        if "TimeoutSeconds" in m.group(0):
            sys.stderr.write("OK: TimeoutSeconds already present in matched block\n")
            sys.exit(0)
        repl = (
            "req := &routerrpc.SendPaymentRequest{\n"
            "\t\tFeeLimitSat:       int64(maxFee),\n"
            "\t\tPaymentRequest:    invoice,\n"
            "\t\tDestCustomRecords: customRecords,\n"
            "\t\tTimeoutSeconds:    60,\n"
            "\t}"
        )
        text = pat.sub(repl, text, count=1)
else:
    text = text.replace(old, new, 1)

open(path, "w").write(text)
if "TimeoutSeconds:    60" not in open(path).read() and "TimeoutSeconds: 60" not in open(path).read():
    # accept any TimeoutSeconds in file after patch near PaymentRequest invoice
    if "TimeoutSeconds" not in open(path).read():
        sys.stderr.write("ERROR: patch applied but TimeoutSeconds not found\n")
        sys.exit(1)
print("Patched", path)
PY
