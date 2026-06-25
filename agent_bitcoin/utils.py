# agent_bitcoin/utils.py
import base64


def validate_macaroon(macaroon: str) -> bool:
    """Basic validation that a macaroon is valid base64."""
    if not macaroon:
        return False
    try:
        base64.b64decode(macaroon, validate=True)
        return True
    except Exception:
        return False


def format_macaroon_header(macaroon_path: str) -> str:
    """Read a macaroon file and return base64 encoded string for header."""
    try:
        with open(macaroon_path, "rb") as f:
            macaroon_bytes = f.read()
        return base64.b64encode(macaroon_bytes).decode("utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"Macaroon file not found: {macaroon_path}")
    except Exception as e:
        raise ValueError(f"Failed to read macaroon: {e}")


def parse_lnd_response(stdout: str) -> dict:
    """
    Helper to parse raw lncli stdout (used by Execute nodes or direct calls).
    Useful for future direct LND integration.
    """
    # This can be expanded later
    return {"raw": stdout}


class NetworkConfig:
    """Helper to manage network-specific settings."""

    @staticmethod
    def get_default_port(network: str) -> int:
        ports = {
            "regtest": 8080,
            "testnet": 8080,
            "mainnet": 8080,
        }
        return ports.get(network, 8080)

    @staticmethod
    def get_rest_url(host: str, port: int, network: str = "regtest") -> str:
        return f"http://{host}:{port}/v1"
