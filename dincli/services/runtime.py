"""
Backward-compatibility shim.

The implementation moved to ``dincli.sdk.runtime`` as part of the SDK
extraction (issue #20). This module re-exports it so existing
``from dincli.services.runtime import ...`` call sites keep working.
New code should import from ``dincli.sdk.runtime``.
"""
from dincli.sdk.runtime import (  # noqa: F401
    ServiceRuntimeContext,
    build_service_runtime_context,
)

__all__ = [
    "ServiceRuntimeContext",
    "build_service_runtime_context",
]
