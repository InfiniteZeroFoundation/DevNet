"""DinSession + SignerProvider protocol — lazy, non-interactive runtime context.

DinSession is the SDK's shared runtime: it lazily resolves network, web3,
account, and config, and never prints, exits, or prompts. The CLI's DinContext
delegates to it for those properties (§4a of the plan); the daemon constructs
its own session at startup.

SignerProvider is a Protocol that both SDK signers (KeystoreSigner,
PrivateKeySigner) and the daemon's interactive adapter satisfy. Any
SignerProvider can be injected into a DinSession for per-use-case key
management without threading interactive dependencies through the SDK.

Daemon adapter contract (D3):
  The daemon's SignerProvider adapter is backed by session-held state
  bootstrapped once, interactively, at ``dind start`` — held in memory for
  that daemon's lifetime. Config changes mid-run arrive via a separate
  ``dind config`` command (interactive there is fine) plus a non-interactive
  ``dind load config`` trigger; the daemon process itself never blocks on stdin
  mid-run, and any missing credential raises ``SignerUnavailable`` for the job
  layer to turn into a job error. This is explicitly not a raw env-var lookup.

  A reference implementation of the daemon adapter lives under ``tests/``
  (see test_sdk_session.py::TestDaemonAdapter) — it is the real CLI adapter
  only, and no code edits land on ``feat/din-daemon`` this task.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from web3 import Web3

from dincli.sdk.config import load_config, resolve_network
from dincli.sdk.errors import NetworkError, RPC_UNREACHABLE
from dincli.sdk.wallet import KeystoreSigner


@runtime_checkable
class SignerProvider(Protocol):
    """Protocol that every signer — SDK and daemon adapter — satisfies."""

    def address(self) -> str: ...
    def can_decrypt(self) -> bool: ...
    def sign_transaction(self, tx: dict): ...


def _resolve_w3(network: str) -> Web3:
    """Lazy web3 factory for DinSession."""
    from dincli.sdk.config import resolve_network_value

    rpc_url = resolve_network_value(network, "rpc_url")
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            raise NetworkError(
                f"Could not connect to Ethereum node at {rpc_url}",
                code=RPC_UNREACHABLE,
                details={"endpoint_host": rpc_url},
            )
        return w3
    except NetworkError:
        raise
    except Exception as e:
        raise NetworkError(
            f"Could not connect to Ethereum node for network '{network}': {e}",
            code=RPC_UNREACHABLE,
            details={"endpoint_host": rpc_url},
        ) from e


class DinSession:
    """Lazily resolves network, web3, account, config. No printing, no exit, no prompts.

    Default signer when none supplied: ``KeystoreSigner(wallet_name)`` —
    non-interactive, so a bare ``DinSession()`` can never hang.
    """

    def __init__(self, network: str | None = None,
                 wallet: str | None = None,
                 signer: SignerProvider | None = None):
        self._network_arg = network
        self._wallet_name = wallet
        self._signer: SignerProvider | None = signer

        self._resolved_network: str | None = None
        self._w3: Web3 | None = None
        self._config: dict | None = None

    # -- lazy properties --------------------------------------------------

    @property
    def network(self) -> str:
        if self._resolved_network is None:
            self._resolved_network = resolve_network(self._network_arg)
        return self._resolved_network

    @property
    def w3(self) -> Web3:
        if self._w3 is None:
            self._w3 = _resolve_w3(self.network)
        return self._w3

    @property
    def config(self) -> dict:
        if self._config is None:
            self._config = load_config()
        return self._config

    @property
    def signer(self) -> SignerProvider:
        if self._signer is None:
            self._signer = KeystoreSigner(self._wallet_name or "default")
        return self._signer

    @property
    def account(self):
        """Lazily resolved via signer. Raises SignerUnavailable / WalletError."""
        if not hasattr(self, "_account"):
            self._account = self.signer.local_account
        return self._account

    @property
    def address(self) -> str:
        """Cheap — no decrypt, delegates to signer.address()."""
        return self.signer.address()
