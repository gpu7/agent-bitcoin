---
title: Agent-Bitcoin n8n Workflow - C4 Model
---

%% C1 - System Context
C4Context
    title System Context - Agent-Bitcoin Lightning Payment System

    Person(user, "User / Trigger", "Triggers the workflow manually or via schedule")
    System(n8n, "n8n Workflow Engine", "Orchestrates autonomous AI agents and LND interactions")
    System_Ext(lnd_a, "Agent A LND Node", "Lightning wallet & node for Agent A (payer)")
    System_Ext(lnd_b, "Agent B LND Node", "Lightning wallet & node for Agent B (receiver + invoice creator)")
    System_Ext(bitcoind, "Bitcoin regtest Node", "Provides on-chain blocks and funding")
    System_Ext(email, "Email / Notification System", "Sends payment reports")

    Rel(user, n8n, "Triggers workflow", "Manual / Schedule")
    Rel(n8n, lnd_a, "Decides & sends payments", "gRPC/REST")
    Rel(n8n, lnd_b, "Creates invoices & receives payments", "gRPC/REST")
    Rel(n8n, bitcoind, "Monitors / sweeps on-chain", "RPC")
    Rel(n8n, email, "Sends reports", "SMTP / API")

%% C2 - Container Diagram (main focus for your workflow)
C4Container
    title Container Diagram - Agent-Bitcoin n8n Workflow

    Person(user, "User", "Triggers payment workflow")
    Container(n8n, "n8n Orchestrator", "Node-based workflow engine", "Runs agents, guardrails, and LND calls")
    
    Container_Boundary(agent_a, "Agent A") {
        Component(grok_a, "Agent A (Grok)", "Langchain agent", "Decides whether to pay + enforces guardrails")
    }
    
    Container_Boundary(agent_b, "Agent B") {
        Component(lnd_b_rest, "Agent B LND", "Lightning node (REST/gRPC)", "Creates invoices, receives payments, checks balances")
        Component(sweep_b, "Sweep Logic", "On-chain sweep component", "Moves funds from Lightning to Bitcoin wallet when threshold met")
    }
    
    Container_Boundary(infra, "Infrastructure") {
        ContainerDb(bitcoind, "Bitcoin regtest", "bitcoind node", "Provides blocks and on-chain funding")
    }
    
    Container(email, "Email Reporter", "Notification container", "Sends final payment report")

    Rel(user, n8n, "Triggers", "Manual / API")
    Rel(n8n, grok_a, "Runs decision logic", "Langchain")
    Rel(grok_a, lnd_b_rest, "Requests invoice creation", "HTTP/gRPC")
    Rel(n8n, lnd_b_rest, "Pays invoice & checks balances", "HTTP/gRPC")
    Rel(lnd_b_rest, sweep_b, "Triggers sweep when conditions met", "Internal")
    Rel(lnd_b_rest, bitcoind, "Monitors / sweeps on-chain", "RPC")
    Rel(n8n, email, "Sends report", "After payment or rejection")

    Rel_D(lnd_a, lnd_b, "Lightning channel", "Funded on regtest")