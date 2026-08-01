"""Unit tests for LND transport selection (docker vs grpc)."""

from unittest.mock import MagicMock, patch

import pytest

from agent_bitcoin.exceptions import ConfigurationError
from agent_bitcoin.lightning import (
    DockerLNDClient,
    GrpcLNDClient,
    create_lnd_client,
    _resolve_transport,
)


def test_default_transport_is_docker(clear_payment_env, monkeypatch):
    monkeypatch.delenv("LND_TRANSPORT", raising=False)
    assert _resolve_transport() == "docker"


def test_create_lnd_client_docker(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_TRANSPORT", "docker")
    monkeypatch.setenv("LND_NETWORK", "signet")
    monkeypatch.setenv("LND_CONTAINER", "agent-bitcoin-lnd-signet")
    client = create_lnd_client()
    assert isinstance(client, DockerLNDClient)
    assert client.transport == "docker"
    assert client.network == "signet"


def test_create_lnd_client_grpc_requires_paths(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_TRANSPORT", "grpc")
    monkeypatch.setenv("LND_NETWORK", "signet")
    monkeypatch.delenv("LND_TLS_CERT_PATH", raising=False)
    monkeypatch.delenv("LND_MACAROON_PATH", raising=False)
    with pytest.raises(ConfigurationError, match="LND_TLS_CERT_PATH"):
        create_lnd_client()


def test_create_lnd_client_grpc_with_mock(clear_payment_env, monkeypatch, tmp_path):
    cert = tmp_path / "tls.cert"
    mac = tmp_path / "admin.macaroon"
    cert.write_bytes(b"fake-cert")
    mac.write_bytes(b"fake-mac")
    monkeypatch.setenv("LND_TRANSPORT", "grpc")
    monkeypatch.setenv("LND_NETWORK", "signet")
    monkeypatch.setenv("LND_GRPC_HOST", "127.0.0.1")
    monkeypatch.setenv("LND_GRPC_PORT", "10009")
    monkeypatch.setenv("LND_TLS_CERT_PATH", str(cert))
    monkeypatch.setenv("LND_MACAROON_PATH", str(mac))

    mock_raw = MagicMock()
    with patch("lndgrpc.LNDClient", return_value=mock_raw) as ctor:
        client = create_lnd_client()
        assert isinstance(client, GrpcLNDClient)
        assert client.transport == "grpc"
        ctor.assert_called_once()
        assert client.ip_address == "127.0.0.1:10009"


def test_lnd_client_factory_compat(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_TRANSPORT", "docker")
    monkeypatch.setenv("LND_NETWORK", "regtest")
    from agent_bitcoin.lightning import LNDClient

    client = LNDClient()
    assert isinstance(client, DockerLNDClient)
