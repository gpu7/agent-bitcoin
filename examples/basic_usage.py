"""Basic usage example for Agent-Bitcoin SDK."""

from agent_bitcoin import create_client


def main():
    # Initialize core Lightning client
    client = create_client()  # noqa: F841

    print("✅ Agent-Bitcoin client created successfully!")
    print("Ready for Lightning operations.")


if __name__ == "__main__":
    main()
