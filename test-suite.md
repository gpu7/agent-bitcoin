# Agent-Bitcoin Workflow Test Suite

## Table of Contents

- [ABT-001: Successful Nominal Payment](#abt-001-successful-nominal-payment)
- [ABT-002: Zero Amount Payment Rejection](#abt-002-zero-amount-payment-rejection)
- [ABT-003: Minimum Amount Payment (1 sat)](#abt-003-minimum-amount-payment-1-sat)
- [ABT-004: Maximum Valid Amount (1,000,000 sats)](#abt-004-maximum-valid-amount-1000000-sats)

---

## ABT-001: Successful Nominal Payment

**Description**  
Tests the complete happy path with a normal payment amount.

**Test Objective**  
User requests a valid payment → full success path → correct email report.

**Test Input**  
"Pay Agent B exactly 50000 sats right now."

**Expected Outcomes**
- Agent A outputs valid JSON with `pay: true`
- Invoice created and payment succeeds
- Email report shows **✅ Success** with correct amount and details

**How to Run**
1. Trigger workflow with the prompt
2. Verify email report shows success
3. Check balances updated correctly

---

## ABT-002: Zero Amount Payment Rejection

**Description**  
Verify rejection of 0 sat payment.

**Test Input**  
"Pay Agent B exactly 0 sats right now."

**Expected Outcomes**
- Workflow rejects the payment
- Email report shows **❌ Rejected** with clear reason

**How to Run**
1. Trigger with zero amount prompt
2. Confirm rejection path and email content

---

## ABT-003: Minimum Amount Payment (1 sat)

**Description**  
Tests the workflow with the smallest valid payment amount (1 sat). Verifies that the system correctly handles the minimum allowed amount, creates a valid 1-sat invoice, processes the payment successfully, and generates a proper success email report.

**Test Objective**  
User requests a 1-sat payment → Agent A decides to pay → Invoice created on B with correct 1-sat amount → Payment succeeds → Email report shows success with accurate 1-sat amount.

**Test Input (user prompt to Agent A)**  
"Pay Agent B exactly 1 sat right now."

**Expected Outcomes**
- Agent A outputs valid JSON: `{"pay": true, "amount": 1, "reason": "..."}`
- Parse Grok Payment Decision node succeeds.
- Invoice is created on Agent B with exactly 1 sat.
- Payment via Pay Invoice Agent-A succeeds (payment_hash present).
- Did Payment Succeed? → true branch.
- Lightning reserve check passes (assuming sufficient balance).
- Amount passes size guardrail (≥ 1 sat).
- Gather Balances shows correct 1-sat payment and `status: "success"`.
- Email report shows **Success**, Lightning Payment = 1 sat, correct reason, and updated balances.

**How to Run**
1. Trigger the workflow manually with the prompt "Pay Agent B exactly 1 sat right now."
2. Run the full workflow.
3. Verify:
   - The created Lightning invoice decodes to exactly 1 sat.
   - Payment succeeds and a payment_hash is generated.
   - Email report shows correct amount (1 sat) and Success status.
   - Balances are updated appropriately (no unexpected rounding or scaling).

---

## ABT-004: Maximum Valid Amount (1,000,000 sats)

**Description**  
Tests the workflow with the maximum allowed payment amount (1,000,000 sats). Verifies that the system correctly handles the upper limit of the payment size guardrail, creates a valid invoice, processes the payment successfully, and generates a proper success email report.

**Test Objective**  
User requests the maximum valid payment (1,000,000 sats) → Agent A decides to pay → Invoice created on B with correct amount → Payment succeeds → Email report shows success with accurate 1,000,000 sat amount.

**Test Input (user prompt to Agent A)**  
"Pay Agent B exactly 1000000 sats right now."

**Expected Outcomes**
- Agent A outputs valid JSON: `{"pay": true, "amount": 1000000, "reason": "..."}`
- Parse Grok Payment Decision node succeeds.
- Invoice is created on Agent B with exactly 1,000,000 sats.
- Payment via Pay Invoice Agent-A succeeds (payment_hash present).
- Did Payment Succeed? → true branch.
- Lightning reserve check passes (assuming sufficient balance).
- Amount exactly equals the maximum allowed (≤ 1,000,000 sats) → passes size guardrail.
- Gather Balances shows correct 1,000,000 sat payment and `status: "success"`.
- Email report shows **Success**, Lightning Payment = 1,000,000 sats, correct reason, and updated balances.

**How to Run**
1. Trigger the workflow manually with the prompt "Pay Agent B exactly 1000000 sats right now."
2. Run the full workflow.
3. Verify:
   - The created Lightning invoice decodes to exactly 1,000,000 sats.
   - Payment succeeds and a payment_hash is generated.
   - Email report shows correct amount (1,000,000 sats) and Success status.
   - Balances are updated appropriately (no unexpected rounding or scaling).

---