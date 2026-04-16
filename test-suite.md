```
***`\# Agent-Bitcoin Workflow Test Suite`**


***`\#\# Table of Contents`**


***`- \[ABT-001: Successful Nominal Payment\](\#abt-001-successful-nominal-payment)`**

***`- \[ABT-002: Zero Amount Payment Rejection\](\#abt-002-zero-amount-payment-rejection)`**


***`---`**


***`\#\# ABT-001: Successful Nominal Payment`**


***`\*\*Description\*\*  `**

***`Tests the complete happy path with a normal payment amount (e.g. 50,000 sats). Verifies Agent A decides to pay, invoice is created, payment succeeds, balances update correctly, and a success email report is sent.`**


***`\*\*Test Objective\*\*  `**

***`User requests a valid payment → Agent A decides to pay → Invoice created on B → Payment succeeds → Balances updated → Optional sweep check → Email report sent with success status.`**


***`\*\*Test Input (user prompt to Agent A)\*\*  `**

***`- "Pay Agent B exactly 105000000 sats right now."  `**

***`- Or simpler: "Send 50000 sats to Agent B."`**


***`\*\*Expected Outcomes\*\*`**

***`- Agent A outputs valid JSON: \`\{"pay": true, "amount": 50000, "reason": "..."\}\``**

***`- Parse Grok Payment Decision node succeeds.`**

***`- Invoice is created on Agent B.`**

***`- Payment via Pay Invoice Agent-A succeeds (payment\_hash present).`**

***`- Did Payment Succeed? → true branch.`**

***`- Lightning reserve check passes.`**

***`- Amount is within guardrails (\< 1,000,000 sats).`**

***`- Gather Balances shows updated balances and \`status: "success"\`.`**

***`- Email report shows \*\*Success\*\*, correct amount, fee, hash, reason, channel balances, and \`sweep\_triggered: No\` (if under threshold).`**


***`\*\*How to Run\*\*`**

***`1. Trigger the workflow manually with the chosen prompt.`**

***`2. Run the full workflow (or step through if needed).`**

***`3. Verify:`**

`   ***- LND balances on both nodes (via CLI or balance nodes).`**

`   ***- Channel local/remote balances.`**

`   ***- Email report content.`**


***`---`**


***`\#\# ABT-002: Zero Amount Payment Rejection`**


***`\*\*Description\*\*  `**

***`Verify that the workflow correctly rejects a payment request of 0 sats and produces a clear rejection report.`**


***`\*\*Test Objective\*\*  `**

***`User requests a zero-amount payment → Workflow rejects it gracefully → Clear rejection email is sent.`**


***`\*\*Test Input\*\*  `**

***`User prompt to Agent A:  `**

***`"Pay Agent B exactly 0 sats right now."`**


***`\*\*Expected Outcomes\*\*`**

***`- Agent A either refuses in plain text or outputs \`\{"pay": false, ...\}\` (or \`amount = 0\`).`**

***`- Parse Grok Payment Decision node sets \`pay: false\`.`**

***`- Payment Decision node routes to the rejection path.`**

***`- No invoice is created and no payment is attempted.`**

***`- Gather Balances node shows \`status: "rejected"\`.`**

***`- Email report is sent with \*\*Rejected\*\* status and a clear reason (e.g., "Payments must be greater than 0 sats").`**


***`\*\*How to Run\*\*`**

***`1. Reset balances if needed (optional).`**

***`2. Trigger the workflow manually with the zero-amount prompt.`**

***`3. Check that the execution path goes through the rejection branch.`**

***`4. Verify the email report clearly shows rejection and the correct reason.`**

***`5. Confirm no Lightning payment occurred (balances should remain unchanged).`**
```

