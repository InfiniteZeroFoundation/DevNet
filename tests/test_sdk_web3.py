from unittest.mock import MagicMock

import pytest
from dincli.sdk import web3 as sdk_web3
from dincli.sdk.errors import NetworkError, RPC_UNREACHABLE


def test_get_w3_raises_network_error_on_unreachable(monkeypatch):
    monkeypatch.setattr(sdk_web3, "resolve_network_value", lambda *a, **kw: "http://unreachable:8545")

    fake_w3 = MagicMock()
    fake_w3.is_connected.return_value = False
    MockWeb3 = MagicMock()
    MockWeb3.HTTPProvider = MagicMock(return_value=MagicMock())
    MockWeb3.return_value = fake_w3
    monkeypatch.setattr(sdk_web3, "Web3", MockWeb3)

    with pytest.raises(NetworkError) as exc:
        sdk_web3.get_w3("testnet")
    assert exc.value.code == RPC_UNREACHABLE
    assert "http://unreachable:8545" in exc.value.message
    assert exc.value.details["endpoint_host"] == "http://unreachable:8545"


def test_get_w3_returns_web3_instance_on_success(monkeypatch):
    monkeypatch.setattr(sdk_web3, "resolve_network_value", lambda *a, **kw: "http://reachable:8545")

    fake_w3 = MagicMock()
    fake_w3.is_connected.return_value = True
    MockWeb3 = MagicMock()
    MockWeb3.HTTPProvider = MagicMock(return_value=MagicMock())
    MockWeb3.return_value = fake_w3
    monkeypatch.setattr(sdk_web3, "Web3", MockWeb3)

    result = sdk_web3.get_w3("testnet")
    assert result is fake_w3
