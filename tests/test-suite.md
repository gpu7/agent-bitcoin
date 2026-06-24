# Agent-Bitcoin Workflow Test Suite

## Table of Contents

- [Agent-Bitcoin Workflow Test Suite](#agent-bitcoin-workflow-test-suite)
  - [Table of Contents](#table-of-contents)
  - [ABT-001: Nominal Payment](#abt-001-nominal-payment)
  - [ABT-002: Under Payment (\< 1 sat)](#abt-002-under-payment--1-sat)
  - [ABT-003: Over Payment (\> 1,000,000 sats)](#abt-003-over-payment--1000000-sats)

---

## ABT-001: Nominal Payment

**Description**  
Tests the complete workflow with a normal payment amount.

**Test Objective**  
A swarm agent sends a valid payment request via webhook → Payment Decision Agent approves → full success path (Create Invoice → Pay Invoice → Parse Payment Result) → correct email report with proper `from` field and extracted amount.

**Test Input (Webhook Payload)**

```bash
curl -X POST http://localhost:5678/webhook/agent-bitcoin-pay \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY_HERE" \
  -d '{
    "from": "Agent-X",
    "to": "Agent-B",
    "amount": 1000,
    "reason": "Payment for services rendered"
  }'
  ```

**Expected Outcomes**
- Payment Decision Agent returns `pay: true`
- Invoice is created on Agent-B
- Lightning payment is executed successfully
- `Parse Payment Result` correctly extracts `amount`, `payment_hash`, and `preimage`
- Email report shows:
  - **From**: `Agent-X`
  - **To**: `Agent-B`
  - **Status**: ✅ Success
  - **Payment Amount**: 1,000 sats
  - Valid **Payment Hash**
  - Valid **Preimage**
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

## ABT-002: Under Payment (< 1 sat)

**Description**  
Tests that the workflow correctly rejects a payment request with zero (or invalid) amount sent via the Webhook Trigger.

**Test Objective**  
A swarm agent sends a payment request with amount = 0 → Payment Decision Agent rejects it → workflow takes the rejection path → email report clearly shows rejection with appropriate reason.

**Test Input (Webhook Payload)**

```bash
curl -X POST http://localhost:5678/webhook/agent-bitcoin-pay \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY_HERE" \
  -d '{
    "from": "Agent-X",
    "to": "Agent-B",
    "amount": 0,
    "reason": "Payment is < 1 sat."
  }'
  ```

**Expected Outcomes**
- Payment Decision Agent returns `pay: false`
- Workflow follows the rejection path
- No Lightning payment is attempted
- Email report shows:
  - **Status**: ❌ Rejected
  - **Reason**: Clear explanation (e.g. "Amount must be at least 1 sat")
  - **From**: `Agent-X`

**How to Run**
1. Execute the webhook curl command above (with `amount: 0`).
2. Verify the workflow takes the rejection path.
3. Check the email report for correct rejection status and clear reason.
4. Confirm no payment was made and balances did not change.

**Success Criteria**
- Payment is rejected
- Email clearly indicates rejection with a meaningful reason
- No Lightning payment occurs
- `from` field is correctly displayed in the report

---

## ABT-003: Over Payment (> 1,000,000 sats)

**Description**  
Tests that the workflow correctly rejects a payment request that exceeds the maximum allowed amount (1,000,000 sats).

**Test Objective**  
User requests an oversize payment → No payment is attempted → Email report shows clear rejection with appropriate reason.

**Test Input (user prompt to Agent A)**  
```bash
curl -X POST http://localhost:5678/webhook/agent-bitcoin-pay \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY_HERE" \
  -d '{
    "from": "Agent-X",
    "to": "Agent-B",
    "amount": 1000001,
    "reason": "Payment is > 1,000,000 sats."
  }'
  ```

**Expected Outcomes**
- Agent-X either refuses in plain text or outputs `{"pay": true, "amount": 1000001, ...}`.
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
