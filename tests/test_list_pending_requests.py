"""
Unit tests for the GraphQL integration in dindao list-pending-requests.

Covers:
  - GraphQL path: model registration requests returned from subgraph
  - GraphQL path: manifest update requests returned from subgraph
  - Fallback to RPC when the subgraph endpoint is unreachable
  - Fallback to RPC when the subgraph returns a GraphQL error body
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import dincli.cli.dindao as dindao_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(data: dict | None = None, errors: list | None = None, status: int = 200):
    """Build a minimal requests.Response-like mock."""
    body: dict = {}
    if errors is not None:
        body["errors"] = errors
    elif data is not None:
        body["data"] = data
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock(
        side_effect=None if status < 400 else Exception(f"HTTP {status}")
    )
    resp.json = MagicMock(return_value=body)
    return resp


class _DummyW3:
    def from_wei(self, amount: int, unit: str) -> str:
        assert unit == "ether"
        return str(amount / 10**18)


def _make_ctx(w3=None):
    """Minimal ctx.obj that satisfies the command's usage."""
    w3 = w3 or _DummyW3()
    console_messages: list = []

    class _Console:
        def print(self, msg, *args, **kwargs):
            console_messages.append(msg)

    registry_contract = MagicMock()
    # Default: no requests on-chain (used only in fallback paths)
    registry_contract.functions.totalModelRequests.return_value.call.return_value = 0
    registry_contract.functions.totalManifestRequests.return_value.call.return_value = 0

    ctx_obj = MagicMock()
    ctx_obj.get_en_w3_account_console.return_value = ("local", w3, MagicMock(), _Console())
    ctx_obj.get_deployed_din_registry_contract.return_value = registry_contract

    ctx = MagicMock()
    ctx.obj = ctx_obj
    return ctx, console_messages, registry_contract


# ---------------------------------------------------------------------------
# GraphQL — model registration requests
# ---------------------------------------------------------------------------


def test_graphql_model_path():
    ctx, msgs, registry = _make_ctx()
    fake_data = {
        "modelRegistrationRequests": [
            {"requestId": "0", "requester": "0xABCD", "isOpenSource": True, "feePaid": "5000000000000000000"},
            {"requestId": "1", "requester": "0xDEAD", "isOpenSource": False, "feePaid": "10000000000000000000"},
        ]
    }
    with patch.object(dindao_module._requests, "post", return_value=_make_response(fake_data)):
        dindao_module.list_pending_requests.callback(ctx, req_type="model")

    output = "\n".join(str(m) for m in msgs)
    assert "Request ID 0" in output
    assert "0xABCD" in output
    assert "Request ID 1" in output
    assert "0xDEAD" in output
    # RPC must NOT have been called when GraphQL succeeded
    registry.functions.totalModelRequests.assert_not_called()


def test_graphql_model_path_empty():
    ctx, msgs, registry = _make_ctx()
    fake_data = {"modelRegistrationRequests": []}
    with patch.object(dindao_module._requests, "post", return_value=_make_response(fake_data)):
        dindao_module.list_pending_requests.callback(ctx, req_type="model")

    output = "\n".join(str(m) for m in msgs)
    assert "No pending model registration requests" in output
    registry.functions.totalModelRequests.assert_not_called()


# ---------------------------------------------------------------------------
# GraphQL — manifest update requests
# ---------------------------------------------------------------------------


def test_graphql_manifest_path():
    ctx, msgs, registry = _make_ctx()
    fake_data = {
        "manifestUpdateRequests": [
            {
                "requestId": "0",
                "model": {"modelId": "3"},
                "requester": "0xCAFE",
                "feePaid": "1000000000000000000",
            }
        ]
    }
    with patch.object(dindao_module._requests, "post", return_value=_make_response(fake_data)):
        dindao_module.list_pending_requests.callback(ctx, req_type="manifest")

    output = "\n".join(str(m) for m in msgs)
    assert "Request ID 0" in output
    assert "Model ID: 3" in output
    assert "0xCAFE" in output
    registry.functions.totalManifestRequests.assert_not_called()


# ---------------------------------------------------------------------------
# Fallback — connection error
# ---------------------------------------------------------------------------


def test_rpc_fallback_on_connection_error():
    ctx, msgs, registry = _make_ctx()
    # Subgraph unreachable
    with patch.object(
        dindao_module._requests, "post", side_effect=ConnectionError("refused")
    ):
        dindao_module.list_pending_requests.callback(ctx, req_type="model")

    # RPC loop must have been invoked
    registry.functions.totalModelRequests.return_value.call.assert_called_once()


def test_rpc_fallback_on_graphql_error_body():
    ctx, msgs, registry = _make_ctx()
    error_resp = _make_response(errors=[{"message": "subgraph not found"}])
    with patch.object(dindao_module._requests, "post", return_value=error_resp):
        dindao_module.list_pending_requests.callback(ctx, req_type="model")

    # GraphQL returned errors — must fall through to RPC
    registry.functions.totalModelRequests.return_value.call.assert_called_once()


def test_rpc_fallback_on_http_error():
    ctx, msgs, registry = _make_ctx()
    bad_resp = _make_response(status=503)
    with patch.object(dindao_module._requests, "post", return_value=bad_resp):
        dindao_module.list_pending_requests.callback(ctx, req_type="model")

    registry.functions.totalModelRequests.return_value.call.assert_called_once()
