"""
Backward-compatibility shim.

The implementation moved to ``dincli.sdk.contracts`` as part of the SDK
extraction (issue #20). This module re-exports it so existing
``from dincli.cli.contract_utils import ...`` call sites keep working.
New code should import from ``dincli.sdk.contracts``.
"""
from dincli.sdk.contracts import (  # noqa: F401
    erc20_abi,
    router_abi,
    get_contract_instance,
)

__all__ = [
    "erc20_abi",
    "router_abi",
    "get_contract_instance",
]
