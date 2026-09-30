"""
Backward-compatibility shim.

The implementation moved to ``dincli.sdk.ipfs`` as part of the SDK extraction
(issue #20). This module re-exports it so existing
``from dincli.services.ipfs import ...`` call sites keep working.
New code should import from ``dincli.sdk.ipfs``.
"""
from dincli.sdk.ipfs import (  # noqa: F401
    upload_to_ipfs,
    retrieve_from_ipfs,
    _ensure_file_exists,
    _load_custom_fn,
    _normalize_path,
    _provider_label,
    _require_custom_service_path,
)

__all__ = [
    "upload_to_ipfs",
    "retrieve_from_ipfs",
]
