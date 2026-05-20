# Agent-Bitcoin Workflow Test Suite

## Table of Contents

- [ABT-001: Successful Nominal Payment](#abt-001-successful-nominal-payment)
- [ABT-002: Zero Amount Payment Rejection](#abt-002-zero-amount-payment-rejection)
- [ABT-003: Minimum Amount Payment (1 sat)](#abt-003-minimum-amount-payment-1-sat)
- [ABT-004: Maximum Valid Amount (1,000,000 sats)](#abt-004-maximum-valid-amount-1000000-sats)
- [ABT-005: Oversize Payment Rejection (> 1,000,000 sats)](#abt-005-oversize-payment-rejection--1000000-sats)
- [ABT-006: Sweep Triggered](#abt-006-sweep-triggered)
- [ABT-007: Lightning Wallet Reserve Violation](#abt-007-lightning-wallet-reserve-violation)

---

## ABT-001: Successful Nominal Payment

**Description**  
Tests the complete happy path with a normal payment amount using the new Webhook Trigger.

**Test Objective**  
A swarm agent sends a valid payment request via webhook → Payment Decision Agent approves → full success path → correct email report with proper `from` field.

**Test Input (Webhook Payload)**

```bash
curl -X POST http://localhost:5678/webhook/agent-bitcoin-pay \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY_HERE" \
  -d '{
    "from": "Agent-X",
    "to": "Agent-B",
    "amount": 50000,
    "reason": "Payment for services rendered"
  }'
  ```

**Expected Outcomes**
- Payment Decision Agent returns `pay: true`
- Invoice is created on Agent-B
- Lightning payment is executed successfully
- Email report shows:
  - **From**: `Agent-X` (or the actual sender)
  - **Status**: ✅ Success
  - **Lightning Payment**: 50,000 sats
  - Valid **Payment Hash**
  - Clear **Reason**

**How to Run**
1. Ensure Agent A has sufficient outbound balance and an open channel to Agent B.
2. Execute the webhook curl command above.
3. Verify the workflow completes the success path.
4. Check the email report for correct `From`, amount, hash, and status.
5. Confirm Agent B’s Lightning balance increased by the correct amount.

**Success Criteria**
- No rejection occurs
- Payment Hash is present and valid
- Email clearly shows the correct sender (`from` field)
- Balances update correctly

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

## ABT-005: Oversize Payment Rejection (> 1,000,000 sats)

**Description**  
Tests that the workflow correctly rejects a payment request that exceeds the maximum allowed amount (1,000,000 sats) as defined by the payment size guardrail.

**Test Objective**  
User requests an oversize payment → Agent A or Agent-B guardrail rejects it → No payment is attempted → Email report shows clear rejection with appropriate reason.

**Test Input (user prompt to Agent A)**  
"Pay Agent B exactly 1000001 sats right now."

**Expected Outcomes**
- Agent A either refuses in plain text or outputs `{"pay": true, "amount": 1000001, ...}`.
- Agent-B Payment Size Guardrail catches the violation (amount > 1,000,000 sats).
- Workflow routes to rejection path (no invoice created, no payment sent).
- Gather Balances shows `status: "rejected"`.
- Email report shows **❌ Rejected** with a clear reason (e.g., "Payment amount exceeds maximum allowed limit of 1,000,000 sats").

**How to Run**
1. Trigger the workflow manually with the prompt "Pay Agent B exactly 1000001 sats right now."
2. Verify the execution path goes through the size guardrail rejection branch.
3. Confirm no Lightning payment occurred (balances unchanged).
4. Check that the email report clearly indicates rejection and the correct reason.

---

## ABT-006: Sweep Triggered

**Description**  
Tests that the workflow correctly triggers an on-chain sweep when the payment amount (or accumulated balance) meets or exceeds the sweep threshold.

**Test Objective**  
User requests a large enough payment → Payment succeeds → Should Sweep evaluates to true → Funds are swept from Lightning to on-chain Bitcoin wallet → Email report reflects sweep triggered.

**Test Input (user prompt to Agent A)**  
"Pay Agent B exactly 30001 sats right now." (or any amount large enough to trigger sweep based on your current threshold)

**Expected Outcomes**
- Agent A outputs valid JSON with a large `amount`.
- Payment succeeds.
- Lightning Wallet Reserve Check passes.
- Should Sweep evaluates to true.
- Sweep On-chain Agent-B executes successfully.
- Gather Balances shows `sweep_triggered: "Yes"`.
- Email report shows **Success** and `Sweep Triggered: Yes`.

**How to Run**
1. Ensure Agent B has sufficient Lightning balance.
2. Trigger the workflow with a large payment prompt.
3. Verify:
   - Should Sweep takes the true branch.
   - Sweep transaction is initiated.
   - Email report correctly shows sweep was triggered.
   - On-chain balance on Agent B increases after confirmation.

   ---

## ABT-007: Lightning Wallet Reserve Violation

**Description**  
Tests that the Lightning wallet reserve guardrail correctly prevents a payment that would drop Agent B's Lightning balance below the minimum reserve threshold (100,000 sats).

**Test Objective**  
User requests a payment that would violate the reserve → Lightning Wallet Reserve Check - Agent-B blocks it → Workflow rejects gracefully → Email report shows rejection due to reserve protection.

**Test Input (user prompt to Agent A)**  
"Pay Agent B exactly 4900000 sats right now." (adjust amount so that after payment Agent B's Lightning balance would fall below 100,000 sats)

**Expected Outcomes**
- Payment Decision proceeds initially.
- Lightning Wallet Reserve Check - Agent-B evaluates to false.
- Workflow routes to rejection path (Payment Blocked - Agent-B Reserve).
- No payment is executed.
- Gather Balances shows `status: "rejected"`.
- Email report shows **❌ Rejected** with reason related to Lightning wallet reserve protection.

**How to Run**
1. Reduce Agent B's Lightning balance close to the 100,000 sat reserve limit (if needed).
2. Trigger with a payment amount that would breach the reserve.
3. Verify the reserve check blocks the payment.
4. Confirm the email report clearly states the reserve violation as the reason.

---

