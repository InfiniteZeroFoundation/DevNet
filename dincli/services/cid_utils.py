"""
Backward-compatibility shim.

The implementation moved to ``dincli.sdk.cid`` as part of the SDK extraction
(issue #20). This module re-exports it so existing
``from dincli.services.cid_utils import ...`` call sites keep working.
New code should import from ``dincli.sdk.cid``.
"""
from dincli.sdk.cid import (  # noqa: F401
    get_bytes32_from_cid,
    get_cid_from_bytes32,
    get_cidv1base32_from_cid,
    validate_cid,
)

__all__ = [
    "get_bytes32_from_cid",
    "get_cid_from_bytes32",
    "get_cidv1base32_from_cid",
    "validate_cid",
]
