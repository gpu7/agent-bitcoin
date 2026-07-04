#!/usr/bin/env python3
"""
Simple AWS Backend Balance Test for PoC
"""

import argparse
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://localhost:8000", help="AWS Backend URL")
    args = parser.parse_args()

    url = args.backend_url.rstrip('/')

    print(f"🚀 Testing AWS Backend Balance at {url}\n")

    try:
        r = requests.get(f"{url}/balance")
        r.raise_for_status()
        data = r.json()

        print("✅ Balance check successful!")
        print(f"Lightning Balance : {data['lightning']['balance']} sats")
        print(f"On-chain Balance  : {data['onchain']['total_balance']} sats")
        print(f"Total             : {data['total_sat']} sats")

    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()