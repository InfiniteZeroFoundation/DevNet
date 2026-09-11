"""Tests for dincli.sdk.operations.platform (task_110926_15 §3.6).

Covers the envelope round-trip for both operations, the platform-address
policy table (§3.2) against a fixture ``din_info.json``, every network in the
*real shipped* ``din_info.json`` (the regression guard for the "no address
metadata" decision), and the infrastructure error mapping (§3.3).
"""
import json

import pytest
from web3 import Web3

from dincli.sdk import operations as ops
from dincli.sdk.errors import ConfigError, ContractError, SignerUnavailable, ValidationError
from dincli.sdk.manifest import load_din_info
from dincli.sdk.operations import platform as platform_ops
from dincli.sdk.serialize import to_envelope

VALID_ADDRESS = "0x" + "ab" * 20


class FakeSession:
    """Minimal stand-in for DinSession — only what the operations read.

    A real DinSession's ``network``/``w3``/``address`` are lazy properties;
    this fake matches that surface without needing a live RPC or keystore.
    """

    def __init__(self, network="local", w3=None, address=None, address_error=None):
        self.network = network
        self.w3 = w3
        self._address = address
        self._address_error = address_error

    @property
    def address(self):
        if self._address_error is not None:
            raise self._address_error
        return self._address


# ---------------------------------------------------------------------------
# get_platform_addresses — envelope round-trip + address policy table
# ---------------------------------------------------------------------------


def test_get_platform_addresses_envelope_round_trip():
    session = FakeSession(network="local")
    result = ops.get_platform_addresses(session)
    envelope = to_envelope(result, network=session.network, chain_id=1337)

    assert envelope["status"] == "ok"
    assert envelope["error"] is None
    assert envelope["meta"]["network"] == "local"
    assert envelope["meta"]["chain_id"] == 1337
    assert "schema_version" in envelope["meta"]
    assert "sdk_version" in envelope["meta"]
    data = envelope["data"]
    assert "present" not in data
    assert data["network"] == "local"
    assert data["coordinator"] == load_din_info()["local"]["coordinator"]
    json.dumps(envelope)


def test_every_shipped_network_envelopes_without_raising():
    """Regression guard for §3.2: mainnet's "0x..." placeholders must not
    make to_checksum_address raise, because PlatformAddresses carries no
    "address" encoder metadata."""
    din_info = load_din_info()
    assert "mainnet" in din_info  # guards against the fixture silently vanishing
    for network in din_info:
        session = FakeSession(network=network)
        result = ops.get_platform_addresses(session)
        envelope = to_envelope(result, network=network)
        assert envelope["status"] == "ok"
        json.dumps(envelope)


def test_platform_addresses_policy_matrix(monkeypatch):
    """§3.2's five value-shapes, against a fixture din_info.json entry."""
    fixture = {
        "fixture_net": {
            # "coordinator" key absent entirely
            "token": None,
            "stake": "",
            "representative": "0x...",  # malformed/placeholder
            "registry": VALID_ADDRESS,
        }
    }
    monkeypatch.setattr(platform_ops, "load_din_info", lambda: fixture)

    session = FakeSession(network="fixture_net")
    result = ops.get_platform_addresses(session)

    assert result.coordinator is None and "coordinator" not in result.present
    assert result.token is None and "token" in result.present
    assert result.stake == "" and "stake" in result.present
    assert result.representative == "0x..." and "representative" in result.present
    assert result.registry == VALID_ADDRESS and "registry" in result.present

    envelope = to_envelope(result, network="fixture_net")
    data = envelope["data"]
    assert data["coordinator"] is None
    assert data["token"] is None
    assert data["stake"] == ""
    assert data["representative"] == "0x..."
    assert data["registry"] == VALID_ADDRESS
    assert "present" not in data
    json.dumps(envelope)


# ---------------------------------------------------------------------------
# get_stake — stake_wei as a string, error mapping
# ---------------------------------------------------------------------------


class _FakeGetStakeFn:
    def __init__(self, value=None, exc=None):
        self._value = value
        self._exc = exc

    def __call__(self, address):
        return self

    def call(self):
        if self._exc is not None:
            raise self._exc
        return self._value


class _FakeContract:
    def __init__(self, value=None, exc=None):
        self.functions = self
        self._fn = _FakeGetStakeFn(value=value, exc=exc)

    def getStake(self, address):
        return self._fn(address)


def _fixture_din_info():
    return {"local": {"stake": VALID_ADDRESS}}


def test_get_stake_wei_is_a_decimal_string(monkeypatch):
    monkeypatch.setattr(platform_ops, "load_din_info", _fixture_din_info)
    monkeypatch.setattr(
        platform_ops, "get_contract_instance",
        lambda *a, **kw: _FakeContract(value=123456789012345678901234),
    )

    session = FakeSession(network="local", w3=object())
    result = ops.get_stake(session, address=VALID_ADDRESS)

    envelope = to_envelope(result, network="local")
    assert envelope["data"]["stake_wei"] == "123456789012345678901234"
    assert isinstance(envelope["data"]["stake_wei"], str)
    assert envelope["data"]["address"] == Web3.to_checksum_address(VALID_ADDRESS)
    assert envelope["data"]["stake_contract"] == Web3.to_checksum_address(VALID_ADDRESS)
    json.dumps(envelope)


def test_get_stake_falls_back_to_session_address(monkeypatch):
    monkeypatch.setattr(platform_ops, "load_din_info", _fixture_din_info)
    monkeypatch.setattr(
        platform_ops, "get_contract_instance",
        lambda *a, **kw: _FakeContract(value=0),
    )

    session = FakeSession(network="local", w3=object(), address=VALID_ADDRESS)
    result = ops.get_stake(session)
    assert result.address == Web3.to_checksum_address(VALID_ADDRESS)


def test_get_stake_explicit_invalid_address_raises_validation_error(monkeypatch):
    monkeypatch.setattr(platform_ops, "load_din_info", _fixture_din_info)

    session = FakeSession(network="local", w3=object())
    with pytest.raises(ValidationError) as exc_info:
        ops.get_stake(session, address="not-an-address")
    assert exc_info.value.code == "validation_failed"


def test_get_stake_no_address_no_signer_propagates_signer_unavailable(monkeypatch):
    monkeypatch.setattr(platform_ops, "load_din_info", _fixture_din_info)

    err = SignerUnavailable("No password available for wallet 'default'.")
    session = FakeSession(network="local", w3=object(), address_error=err)

    with pytest.raises(SignerUnavailable) as exc_info:
        ops.get_stake(session)
    assert exc_info.value is err  # propagated unchanged, not re-wrapped


# ---------------------------------------------------------------------------
# Error path — to_envelope(error=...), infrastructure failures as DinError
# ---------------------------------------------------------------------------


def test_config_error_through_to_envelope():
    err = ConfigError("Network 'nowhere' is not configured in din_info.json.", details={"key": "nowhere"})
    envelope = to_envelope(error=err)
    assert envelope["status"] == "error"
    assert envelope["data"] is None
    assert envelope["error"]["code"] == "config_error"
    json.dumps(envelope)


def test_malformed_din_info_json_raises_config_error(monkeypatch):
    def raise_decode_error():
        json.loads("{not valid json")

    monkeypatch.setattr(platform_ops, "load_din_info", raise_decode_error)

    session = FakeSession(network="local")
    with pytest.raises(ConfigError) as exc_info:
        ops.get_platform_addresses(session)
    assert exc_info.value.code == "config_error"


def test_network_absent_from_din_info_raises_config_error(monkeypatch):
    monkeypatch.setattr(platform_ops, "load_din_info", lambda: {"local": {}})

    session = FakeSession(network="does_not_exist")
    with pytest.raises(ConfigError) as exc_info:
        ops.get_platform_addresses(session)
    assert exc_info.value.code == "config_error"


def test_missing_abi_artifact_raises_contract_error(monkeypatch):
    monkeypatch.setattr(platform_ops, "load_din_info", _fixture_din_info)

    def fake_get_contract_instance(*a, **kw):
        raise FileNotFoundError("Contract artifact not found at: /nowhere/DinValidatorStake.json")

    monkeypatch.setattr(platform_ops, "get_contract_instance", fake_get_contract_instance)

    session = FakeSession(network="local", w3=object())
    with pytest.raises(ContractError) as exc_info:
        ops.get_stake(session, address=VALID_ADDRESS)
    assert exc_info.value.code == "contract_error"


def test_failing_getstake_call_raises_contract_error(monkeypatch):
    monkeypatch.setattr(platform_ops, "load_din_info", _fixture_din_info)
    monkeypatch.setattr(
        platform_ops, "get_contract_instance",
        lambda *a, **kw: _FakeContract(exc=RuntimeError("execution reverted")),
    )

    session = FakeSession(network="local", w3=object())
    with pytest.raises(ContractError) as exc_info:
        ops.get_stake(session, address=VALID_ADDRESS)
    assert exc_info.value.code == "contract_error"


def test_stake_address_absent_raises_config_error(monkeypatch):
    monkeypatch.setattr(platform_ops, "load_din_info", lambda: {"local": {"stake": None}})

    session = FakeSession(network="local", w3=object())
    with pytest.raises(ConfigError) as exc_info:
        ops.get_stake(session, address=VALID_ADDRESS)
    assert exc_info.value.code == "config_error"


# ---------------------------------------------------------------------------
# Malformed network ENTRY (not just a malformed/missing field within it) —
# independent review, task_110926_14/15, finding 5. A parseable din_info.json
# whose network entry isn't a JSON object at all (null, a string, a list) used
# to pass _load_din_info_entry()'s checks (valid JSON, key present) and then
# leak a raw TypeError/AttributeError out of get_platform_addresses()/
# get_stake() instead of a DinError.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("malformed_entry", [None, "0xdeadbeef", []])
def test_malformed_network_entry_raises_config_error_for_addresses(monkeypatch, malformed_entry):
    monkeypatch.setattr(platform_ops, "load_din_info", lambda: {"local": malformed_entry})

    session = FakeSession(network="local")
    with pytest.raises(ConfigError) as exc_info:
        ops.get_platform_addresses(session)
    assert exc_info.value.code == "config_error"


@pytest.mark.parametrize("malformed_entry", [None, "0xdeadbeef", []])
def test_malformed_network_entry_raises_config_error_for_stake(monkeypatch, malformed_entry):
    monkeypatch.setattr(platform_ops, "load_din_info", lambda: {"local": malformed_entry})

    session = FakeSession(network="local", w3=object())
    with pytest.raises(ConfigError) as exc_info:
        ops.get_stake(session, address=VALID_ADDRESS)
    assert exc_info.value.code == "config_error"
