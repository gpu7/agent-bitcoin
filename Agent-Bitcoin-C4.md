``` mermaid
graph TD;
    subgraph External["External Trigger"];
        User["User / Manual Trigger"];
    end;

    subgraph n8n["n8n Workflow"];
        AgentA["Agent-A (Grok Decision)"];
        Parse["Parse Grok Payment Decision"];
        PaymentDecision["Payment Decision"];
        PrepareInvoice["Prepare Invoice Data"];
        CreateInv["Create Invoice Agent-B"];
        ExtractRequest["Extract Payment Request"];
        ExtractAmount["Extract Payment Amount from Invoice"];
        SizeGuardrail["Agent-B Payment Size Guardrail"];
        PayInv["Pay Invoice Agent-A"];
        DidSucceed["Did Payment Succeed?"];
        Capture["Capture Payment Amount"];
        PaymentSucc["Payment Succeeded"];
        
        GetBalB["Get Lightning Balance Agent-B"];
        ReserveCheckB["Lightning Wallet Reserve Check - Agent-B"];
        ShouldSweep["Should Sweep"];
        
        Merge["Merge"];
        Gather["Gather Balances"];
        Email["Send Email Report"];
        
        PaymentFailed["Payment Failed"];
        BlockedReserve["Payment Blocked - Agent-B Reserve"];
        RejectedByB["Payment Rejected by Agent-B"];
        PrepareDataB["Prepare Data for Agent-B"];
    end;

    subgraph LND_B["Agent B LND"];
        LND["Agent B LND Node"];
    end;

    User-->AgentA;
    AgentA-->Parse;
    Parse-->PaymentDecision;
    PaymentDecision-->|pay = true|PrepareInvoice;
    PrepareInvoice-->CreateInv;
    CreateInv-->ExtractRequest;
    ExtractRequest-->ExtractAmount;
    ExtractAmount-->SizeGuardrail;
    SizeGuardrail-->|Valid|PayInv;
    SizeGuardrail-->|Invalid|RejectedByB;
    PayInv-->DidSucceed;
    
    %% SUCCESS PATH
    DidSucceed-->|True|Capture;
    Capture-->PaymentSucc;
    PaymentSucc-->GetBalB;
    GetBalB-->ReserveCheckB;
    ReserveCheckB-->|True|ShouldSweep;
    ShouldSweep-->|No Sweep|Merge;
    ShouldSweep-->|Sweep Needed|Merge;

    %% REJECTION / BLOCKED PATHS
    ReserveCheckB-->|False|BlockedReserve;
    DidSucceed-->|False|PaymentFailed;
    PaymentFailed-->Merge;
    BlockedReserve-->Merge;
    RejectedByB-->Merge;
    PrepareDataB-->Merge;

    %% Final reporting
    Merge-->Gather;
    Gather-->Email;

    %% External calls
    CreateInv-.->LND;
    PayInv-.->LND;

    classDef success fill:#d4edda,stroke:#28a745,stroke-width:3px;
    classDef reject fill:#f8d7da,stroke:#dc3545,stroke-width:3px;
    class PaymentSucc,Merge,Gather,Email success;
    class BlockedReserve,PaymentFailed,RejectedByB,PrepareDataB reject;
    ```