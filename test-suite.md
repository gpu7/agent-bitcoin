# Agent-Bitcoin Workflow Test Suite

## Table of Contents

- [ABT-001: Successful Nominal Payment](#abt-001-successful-nominal-payment)
- [ABT-002: Zero Amount Payment Rejection](#abt-002-zero-amount-payment-rejection)

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