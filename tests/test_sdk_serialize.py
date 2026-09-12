"""Tests for dincli.sdk.serialize (issue #20 Part A)."""
from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from dincli.sdk.errors import ValidationError
from dincli.sdk.serialize import SCHEMA_VERSION, _encode_dataclass, to_envelope
from dincli.sdk.state import GIState


@dataclass
class _Fix:
    gi: int
    fee_wei: int = field(metadata={"json": "uint256_string"})
    owner: str = field(metadata={"json": "address"})
    blob: bytes = b"\x00\xab"
    price: Decimal = Decimal("1.5")
    raw: object = field(default=None, metadata={"json": "omit"})


@dataclass
class _EnumWrap:
    state: GIState


@dataclass
class _NullableTagged:
    reward: int | None = field(default=None, metadata={"json": "uint256_string"})
    owner: str | None = field(default=None, metadata={"json": "address"})


def test_uint256_stringification():
    encoded = _encode_dataclass(_Fix(gi=1, fee_wei=10**18, owner="0x" + "0" * 40,
                                     blob=b"", price=Decimal("0"), raw=None))
    assert encoded["fee_wei"] == "1000000000000000000"


def test_omit():
    encoded = _encode_dataclass(_Fix(gi=1, fee_wei=0, owner="0x" + "0" * 40,
                                     blob=b"", price=Decimal("0"), raw="should_be_gone"))
    assert "raw" not in encoded


def test_nullable_tagged_fields_serialize_to_null():
    encoded = _encode_dataclass(_NullableTagged(reward=None, owner=None))
    assert encoded["reward"] is None
    assert encoded["owner"] is None


def test_small_int_passthrough():
    encoded = _encode_dataclass(_Fix(gi=42, fee_wei=0, owner="0x" + "0" * 40,
                                     blob=b"", price=Decimal("0"), raw=None))
    assert encoded["gi"] == 42


def test_bytes_to_hex():
    encoded = _encode_dataclass(_Fix(gi=0, fee_wei=0, owner="0x" + "0" * 40,
                                     blob=b"\x00\xab", price=Decimal("0"), raw=None))
    assert encoded["blob"] == "0x00ab"


def test_checksummed_address():
    addr = "0xcf18dba482899e5d32b2e48b5242ef30b61c0cd0"
    encoded = _encode_dataclass(_Fix(gi=0, fee_wei=0, owner=addr,
                                     blob=b"", price=Decimal("0"), raw=None))
    assert encoded["owner"] != addr.lower()
    assert encoded["owner"] == "0xcf18DBa482899e5D32b2E48B5242eF30b61c0Cd0"


def test_enum_to_name():
    encoded = _encode_dataclass(_EnumWrap(state=GIState.LMSstarted))
    assert encoded["state"] == "LMSstarted"


def test_decimal_to_string():
    encoded = _encode_dataclass(_Fix(gi=0, fee_wei=0, owner="0x" + "0" * 40,
                                     blob=b"", price=Decimal("1.5"), raw=None))
    assert encoded["price"] == "1.5"


def test_envelope_success():
    result = to_envelope(
        _Fix(gi=0, fee_wei=0, owner="0x" + "0" * 40, blob=b"", price=Decimal("0"), raw=None),
        network="sepolia_op_devnet",
        chain_id=11155420,
    )
    assert result["status"] == "ok"
    assert result["data"] is not None
    assert result["error"] is None
    assert result["meta"]["schema_version"] == SCHEMA_VERSION
    assert "sdk_version" in result["meta"]
    assert result["meta"]["network"] == "sepolia_op_devnet"
    assert result["meta"]["chain_id"] == 11155420


def test_envelope_success_null_data():
    result = to_envelope(None, network="sepolia", chain_id=11155420)
    assert result["status"] == "ok"
    assert result["data"] is None
    assert result["error"] is None


def test_envelope_error():
    err = ValidationError("x", details={"field": "gi_state", "expected": "x", "actual": "y"})
    result = to_envelope(None, error=err)
    assert result["status"] == "error"
    assert result["data"] is None
    assert result["error"]["code"] == "validation_failed"
    assert result["error"]["details"]["field"] == "gi_state"
    assert result["meta"]["schema_version"] == SCHEMA_VERSION


def test_envelope_correlation_id():
    result = to_envelope(None, correlation_id="abc-123")
    assert result["meta"]["correlation_id"] == "abc-123"
