"""Example: call the Backend HTTP API with API key auth."""

import os
from typing import Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()


class AgentBitcoinAPI:
    """AI agent-friendly wrapper for the Backend API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = (api_key or os.getenv("AGENT_BITCOIN_API_KEY") or "").strip()
        if not self.api_key:
            raise RuntimeError(
                "Set AGENT_BITCOIN_API_KEY in the environment or pass api_key="
            )

    def _headers(self) -> Dict[str, str]:
        return {"X-API-Key": self.api_key}

    def create_invoice(self, memo: str, amount_sats: int) -> Dict:
        response = requests.post(
            f"{self.base_url}/invoices",
            json={"memo": memo, "amount_sats": amount_sats},
            headers=self._headers(),
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def get_balance(self) -> Dict:
        response = requests.get(
            f"{self.base_url}/balance",
            headers=self._headers(),
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def pay_invoice(self, payment_request: str) -> Dict:
        response = requests.post(
            f"{self.base_url}/pay",
            json={"payment_request": payment_request},
            headers=self._headers(),
            timeout=120,
        )
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    api = AgentBitcoinAPI()

    print("Current balance:", api.get_balance().get("total_sat"), "sats\n")

    invoice = api.create_invoice(memo="Payment for AI service", amount_sats=10000)
    print("Invoice created:")
    print("Payment Request:", (invoice.get("payment_request") or "")[:80] + "...")
    print("r_hash:", invoice.get("r_hash"))
