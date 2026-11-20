"""SDK envelope serialization (proposal §3).

Encodes typed dataclasses into the ``din-sdk-envelope/v1`` JSON shape used by
the daemon wire protocol. The encoder is metadata-driven: dataclass field
``metadata={"json": ...}`` tags control how each field is serialized.
"""
from __future__ import annotations

import dataclasses
import enum
from decimal import Decimal
from typing import Any

from web3 import Web3

from dincli.sdk import __version__ as SDK_VERSION

SCHEMA_VERSION = "din-sdk-envelope/v1"


def _encode_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, enum.Enum):
        return v.name
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return Web3.to_hex(v)
    if dataclasses.is_dataclass(v):
        return _encode_dataclass(v)
    if isinstance(v, dict):
        return {k: _encode_value(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_encode_value(item) for item in v]
    return v


def _encode_dataclass(obj: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in dataclasses.fields(obj):
        json_kind = f.metadata.get("json")
        if json_kind == "omit":
            continue
        raw = getattr(obj, f.name)
        if raw is None:
            out[f.name] = None
            continue
        if json_kind == "uint256_string":
            out[f.name] = str(int(raw))
        elif json_kind == "address":
            out[f.name] = Web3.to_checksum_address(raw)
        else:
            out[f.name] = _encode_value(raw)
    return out


def to_envelope(
    data: Any = None,
    *,
    error=None,
    network: str | None = None,
    chain_id: int | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    if error is not None:
        status, payload, err = "error", None, error.to_error()
    else:
        status, payload, err = "ok", (None if data is None else _encode_dataclass(data)), None
    meta: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "sdk_version": SDK_VERSION}
    if network is not None:
        meta["network"] = network
    if chain_id is not None:
        meta["chain_id"] = chain_id
    if correlation_id is not None:
        meta["correlation_id"] = correlation_id
    return {"status": status, "data": payload, "error": err, "meta": meta}
