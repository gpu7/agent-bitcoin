``` mermaid
graph TD;
    subgraph External["External Trigger"];
        User["User / Manual Trigger"];
    end;

    subgraph n8n["n8n Workflow"];
        AgentA["Agent-A (Grok Decision)"];
        Parse["Parse Grok Payment Decision"];
        Prepare["Prepare Invoice Data"];
        CreateInv["Create Invoice Agent-B"];
        PayInv["Pay Invoice Agent-A"];
        DidSucceed["Did Payment Succeed?"];
        Capture["Capture Payment Amount"];
        PaymentSucc["Payment Succeeded"];
        
        GetBalB["Get Lightning Balance Agent-B"];
        ReserveB["Lightning Wallet Reserve Check - Agent-B"];
        ShouldSweep["Should Sweep"];
        Gather["Gather Balances"];
        Email["Send Email Report"];
    end;

    subgraph LND_B["Agent B LND"];
        LND["Agent B LND Node"];
    end;

    User-->AgentA;
    AgentA-->Parse;
    Parse-->|pay = true|Prepare;
    Prepare-->CreateInv;
    CreateInv-->PayInv;
    PayInv-->DidSucceed;

    %% SUCCESS PATH
    DidSucceed-->|True|Capture;
    Capture-->PaymentSucc;
    PaymentSucc-->GetBalB;
    GetBalB-->ReserveB;
    ReserveB-->|True|ShouldSweep;
    ShouldSweep-->|No Sweep|Gather;
    ShouldSweep-->|Sweep Needed|Gather;

    %% REJECTION PATHS
    ReserveB-->|False|Gather;
    DidSucceed-->|False|Gather;

    Gather-->Email;

    CreateInv-.->LND;
    PayInv-.->LND;

    classDef success fill:#d4edda,stroke:#28a745;
    classDef reject fill:#f8d7da,stroke:#dc3545;
    class PaymentSucc,Gather,Email success;
    ```