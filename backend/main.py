from fastapi import FastAPI, HTTPException
import os
import time

from agent_bitcoin.lightning import LNDClient

app = FastAPI(title="Agent-Bitcoin Backend API")

FEE_SATS = int(os.getenv("FEE_SATS", 1000))
FEE_ADDRESS = os.getenv("FEE_ADDRESS")

client = LNDClient()

@app.get("/")
async def root():
    return {"status": "running", "message": "Backend is up. LND may still be starting."}

@app.get("/balance")
async def get_balance():
    try:
        # Try a few times quickly
        for _ in range(5):
            try:
                ln = client._run("channelbalance")
                onchain = client._run("walletbalance")
                return {
                    "lightning": ln,
                    "onchain": onchain,
                    "total_sat": int(ln.get("balance", 0)) + int(onchain.get("confirmed_balance", 0))
                }
            except Exception as e:
                if "starting up" in str(e).lower() or "not yet ready" in str(e).lower():
                    time.sleep(3)
                    continue
                raise
        return {"status": "starting", "message": "LND is still starting up. Please wait and try again."}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
