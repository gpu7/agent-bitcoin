import requests
from typing import Dict, Optional

class AgentBitcoinAPI:
    """AI Agent-friendly wrapper for the Backend API"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def create_invoice(self, memo: str, amount_sats: int) -> Dict:
        """Create a Lightning invoice"""
        response = requests.post(
            f"{self.base_url}/invoices",
            json={"memo": memo, "amount_sats": amount_sats}
        )
        response.raise_for_status()
        return response.json()

    def get_balance(self) -> Dict:
        """Get current balance"""
        response = requests.get(f"{self.base_url}/balance")
        response.raise_for_status()
        return response.json()

    def pay_invoice(self, payment_request: str) -> Dict:
        """Pay a Lightning invoice"""
        response = requests.post(
            f"{self.base_url}/payments",
            json={"payment_request": payment_request}
        )
        response.raise_for_status()
        return response.json()

    def check_invoice(self, payment_hash: str) -> Dict:
        """Check status of an invoice"""
        response = requests.get(f"{self.base_url}/invoices/{payment_hash}")
        response.raise_for_status()
        return response.json()


# ======================
# Example Usage for AI Agent
# ======================

if __name__ == "__main__":
    api = AgentBitcoinAPI()
    
    print("Current balance:", api.get_balance()["total_sat"], "sats\n")
    
    # Create invoice
    invoice = api.create_invoice(
        memo="Payment for AI service",
        amount_sats=10000
    )
    print("Invoice created:")
    print("Payment Request:", invoice["payment_request"][:80] + "...")
    print("Payment Hash:", invoice["payment_hash"])
    
    # In a real agent, you would now share the payment_request with the user/other agent