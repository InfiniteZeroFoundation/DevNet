"""CLI SignerProvider adapter — the interactive boundary.

This module is the ONLY place in the codebase allowed to prompt for a wallet
password. The SDK's ``KeystoreSigner`` resolves credentials non-interactively
(env var, then in-memory TTL cache) and raises ``SignerUnavailable`` rather than
blocking; this adapter wraps it and adds the ``getpass`` fallback plus the
retry-on-stale-cache message.

Why it exists (remediation R5 / RC-1): without it, ``DinContext.account`` and
``DinSession.account`` resolved wallets through two independent paths that
disagreed whenever the wallet name came from ``DIN_WALLET_NAME`` or the config
file — the CLI displayed one address while the transaction was signed by
another. Injecting this adapter into the session makes the session the single
source of truth for which key signs.

See Developer/design/sdk-interface-proposal.md §2 (the two-adapter design).
"""
from __future__ import annotations

from getpass import getpass

from eth_account.signers.local import LocalAccount
from rich.console import Console

from dincli.sdk.errors import SignerUnavailable, WalletError
from dincli.sdk.wallet import (
    _cache_password_in_memory,
    _clean_stale_session_file,
    _clear_memory_cache,
    account_from_keystore,
    load_account_noninteractive,
    load_keystore,
    resolve_wallet_path,
)

console = Console()


class InteractiveKeystoreSigner:
    """SignerProvider backed by the on-disk keystore, allowed to prompt.

    Resolution order is unchanged from the pre-SDK ``load_account``:
      1. ``DIN_WALLET_PASSWORD`` environment variable
      2. in-memory TTL cache (keyed by wallet name)
      3. interactive ``getpass`` prompt
    On a stale cached password it clears the cache, prints the legacy
    ``Cached password failed, prompting...`` notice, and retries once.
    """

    def __init__(self, wallet_name: str = "default"):
        self._wallet_name = wallet_name
        self._account: LocalAccount | None = None

    # -- SignerProvider ---------------------------------------------------

    def address(self) -> str:
        return self.local_account.address

    def can_decrypt(self) -> bool:
        try:
            self.local_account
            return True
        except (SignerUnavailable, WalletError, ValueError, FileNotFoundError):
            return False

    def sign_transaction(self, tx: dict):
        return self.local_account.sign_transaction(tx)

    # -- resolution -------------------------------------------------------

    @property
    def local_account(self) -> LocalAccount:
        if self._account is None:
            self._account = self._resolve()
        return self._account

    def _resolve(self) -> LocalAccount:
        name = self._wallet_name
        try:
            return load_account_noninteractive(name)
        except SignerUnavailable:
            # No env var, no cached password — prompting is this layer's job.
            pass
        except WalletError:
            wallet_path, exists = resolve_wallet_path(name)
            if not exists:
                raise FileNotFoundError(
                    f"No wallet found for name '{name}' at {wallet_path}. "
                    f"Run `dincli system register-wallet --name {name}` first."
                )
            if not _clear_memory_cache(name):
                raise ValueError("Invalid password or corrupted keystore.")
            console.print("[yellow]Cached password failed, prompting...[/yellow]")

        data = load_keystore(name)
        if data.get("demo_mode") is True:
            from eth_account import Account
            return Account.from_key(data["private_key"])

        password = getpass("Enter wallet password: ")
        try:
            account = account_from_keystore(data, password)
        except WalletError:
            raise ValueError("Invalid password or corrupted keystore.")
        _cache_password_in_memory(name, password)
        _clean_stale_session_file()
        return account
