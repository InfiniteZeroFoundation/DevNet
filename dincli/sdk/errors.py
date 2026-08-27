"""DIN-SDK domain error hierarchy + detail sanitization.

Pure module: no imports from ``dincli.cli``, ``typer``, or ``rich``. SDK
functions raise these instead of calling ``typer.Exit``/``sys.exit``; the CLI
maps them to exit codes, the daemon maps them to job errors and keys retries
off the stable ``code``.

See Developer/design/sdk-interface-proposal.md §4 (taxonomy) and §4a
(details sanitization).
"""
from __future__ import annotations

from typing import Any

# --- Reserved stable subcodes (proposal §4) ---------------------------------
# Pass as ``code=`` when raising; daemon retry policy keys off these strings.
TX_ESTIMATION_FAILED = "tx_estimation_failed"
TX_REVERTED = "tx_reverted"
TX_TIMEOUT = "tx_timeout"
TX_NONCE_CONFLICT = "tx_nonce_conflict"
TX_REPLACEMENT_UNDERPRICED = "tx_replacement_underpriced"
RECEIPT_MISSING = "receipt_missing"
RPC_UNREACHABLE = "rpc_unreachable"
IPFS_CID_MISMATCH = "ipfs_cid_mismatch"


class DinError(Exception):
    """Base class for all SDK domain errors.

    ``code`` is a stable, machine-readable string that flows into the JSON
    envelope's ``error.code`` (proposal §3). ``details`` is structured context
    that is *sanitized on construction* (proposal §4a) — it never carries
    secrets and its shape is bounded per ``code``.
    """

    code: str = "din_error"

    def __init__(self, message: str, *, code: str | None = None,
                 details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = sanitize_details(self.code, details or {})

    def to_error(self) -> dict[str, Any]:
        """Serialize to the envelope's ``error`` object (proposal §3)."""
        return {"code": self.code, "message": self.message, "details": self.details}


class ConfigError(DinError):
    code = "config_error"


class NetworkError(DinError):
    code = "network_unreachable"


class WalletError(DinError):
    code = "wallet_error"


class SignerUnavailable(DinError):
    code = "signer_unavailable"


class ManifestError(DinError):
    code = "manifest_error"


class IpfsError(DinError):
    code = "ipfs_error"


class ContractError(DinError):
    code = "contract_error"


class NotFoundError(DinError):
    code = "not_found"


class ValidationError(DinError):
    code = "validation_failed"


class TransactionError(DinError):
    code = "tx_failed"


class ConfirmationRequired(DinError):
    code = "confirmation_required"


class ChainIdMismatchError(DinError):
    """The configured RPC endpoint is on a different chain than the selected network."""
    code = "chain_id_mismatch"


# --- Detail sanitization (proposal §4a) -------------------------------------
# Allowlist-oriented: each error code declares the detail keys it may carry and
# their type. Anything not listed for a code is DROPPED — free-form details are
# unsafe by default. This is what keeps secrets out of long-lived daemon JSON
# logs; a generic scrubber would miss secrets nested in arbitrary values.

_MAX_STR = 256          # cap on ordinary string values
_MAX_TAIL = 2000        # cap on stdout/stderr-style tails

# Keys that must NEVER survive, regardless of error code.
_NEVER = frozenset({
    "private_key", "privatekey", "password", "passwd", "secret",
    "mnemonic", "seed", "api_key", "api_secret", "raw_signed_tx", "signed_tx",
})

# Per-code allowed keys -> normalizer kind.
# Kinds: "hex" (0x string), "int", "bool", "str" (bounded), "tail" (bounded tail), "host".
_ALLOWLIST: dict[str, dict[str, str]] = {
    "tx_failed": {"tx_hash": "hex", "nonce": "int", "broadcast": "bool", "reason": "str"},
    TX_ESTIMATION_FAILED: {"reason": "str", "gi": "int", "broadcast": "bool"},
    TX_REVERTED: {"tx_hash": "hex", "nonce": "int", "gi": "int", "block_number": "int",
                  "broadcast": "bool", "reason": "str"},
    TX_TIMEOUT: {"tx_hash": "hex", "nonce": "int", "broadcast": "bool"},
    TX_NONCE_CONFLICT: {"tx_hash": "hex", "nonce": "int", "broadcast": "bool"},
    TX_REPLACEMENT_UNDERPRICED: {"nonce": "int", "broadcast": "bool"},
    RECEIPT_MISSING: {"tx_hash": "hex", "nonce": "int", "broadcast": "bool"},
    "network_unreachable": {"endpoint_host": "host"},
    RPC_UNREACHABLE: {"endpoint_host": "host"},
    "ipfs_error": {"provider": "str", "status_code": "int", "path": "str", "stderr": "tail"},
    IPFS_CID_MISMATCH: {"requested_cid": "str", "computed_cid": "str"},
    "manifest_error": {"path": "str", "key": "str"},
    "contract_error": {"contract": "str", "function": "str"},
    "not_found": {"kind": "str", "id": "int"},
    "validation_failed": {"field": "str", "expected": "str", "actual": "str"},
    "wallet_error": {"account": "str"},
    "signer_unavailable": {"account": "str"},
    "config_error": {"key": "str"},
    "confirmation_required": {"operation": "str"},
    "chain_id_mismatch": {"network": "str", "expected_chain_id": "int", "actual_chain_id": "int"},
}


def _bounded_str(value: Any, limit: int = _MAX_STR) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


_UNPARSABLE_ENDPOINT = "<unparsable-endpoint>"


def _sanitize_host(value: Any) -> str:
    """Reduce a URL to scheme://hostname[:port] — never userinfo, path, query,
    params or fragment.

    Path-style API keys (``https://mainnet.infura.io/v3/<KEY>``,
    ``https://eth.alchemy.com/v2/<KEY>``) are how the two largest RPC
    providers authenticate, so the path is dropped along with the query
    string and fragment, not just userinfo. Input ``urlsplit`` cannot parse
    as a URL is never echoed back — it may itself be the secret — and instead
    yields a fixed placeholder.
    """
    text = str(value)
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(text)
        if parts.scheme and parts.netloc:
            host = parts.hostname or ""
            if parts.port:
                host = f"{host}:{parts.port}"
            return _bounded_str(f"{parts.scheme}://{host}")
    except Exception:
        pass
    return _UNPARSABLE_ENDPOINT


def _coerce(kind: str, value: Any) -> Any:
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if kind == "bool":
        return bool(value)
    if kind == "hex":
        text = str(value)
        return _bounded_str(text if text.startswith("0x") else "0x" + text)
    if kind == "host":
        return _sanitize_host(value)
    if kind == "tail":
        text = str(value)
        return text[-_MAX_TAIL:] if len(text) > _MAX_TAIL else text
    return _bounded_str(value)


def sanitize_details(code: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Return a sanitized copy of ``raw`` per the allowlist for ``code``.

    Keys not allowlisted for the code are dropped; never-allowed secret keys are
    always dropped; values are coerced/bounded by their declared kind. Codes
    with no schema yield an empty dict (free-form details are unsafe).
    """
    allowed = _ALLOWLIST.get(code, {})
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _NEVER or key not in allowed:
            continue
        coerced = _coerce(allowed[key], value)
        if coerced is not None:
            out[key] = coerced
    return out
