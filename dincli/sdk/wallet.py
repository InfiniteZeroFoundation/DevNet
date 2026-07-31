"""Non-interactive keystore/account resolution.

Pure module: no imports from ``dincli.cli``, ``typer``, or ``rich``, and no
calls to ``getpass`` or any other blocking-IO prompt. SDK functions raise
``DinError`` subclasses; the CLI maps them to exit codes.

Functions moved verbatim from ``dincli/cli/utils.py`` are tagged with their
original line anchor so the extraction is traceable; the few deliberate
differences (e.g. switching ``Path(__file__)`` to ``files("dincli")`` for
portability) are noted inline.
"""
from __future__ import annotations

import json
import os
import re
import time
from importlib.resources import files
from pathlib import Path
from typing import Optional

from eth_account import Account
from eth_account.signers.local import LocalAccount

from dincli.sdk.config import CONFIG_DIR, get_env_key
from dincli.sdk.errors import SignerUnavailable, WalletError

# ---------------------------------------------------------------------------
# Constants — moved verbatim from dincli/cli/utils.py
# ---------------------------------------------------------------------------
_ACCOUNT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # :18
_PASSWORD_TTL_DEFAULT = 900  # :19
_PASSWORD_CACHE: dict[str, tuple[str, float]] = {}  # :20

# Sentinel so callers can inject an already-fetched DIN_WALLET_PASSWORD value
# (fetched once per unlock) while callers that omit it self-fetch as before.
_UNSET = object()  # :24

WALLET_FILE = CONFIG_DIR / "wallet.json"  # :44
WALLETS_DIR = CONFIG_DIR / "wallets"  # :45
LEGACY_WALLET_FILE = WALLET_FILE  # :47

# ---------------------------------------------------------------------------
# Wallet path helpers — moved verbatim from dincli/cli/utils.py
# ---------------------------------------------------------------------------


def validate_account_name(name: str) -> str:  # :51
    name = name.strip()
    if not _ACCOUNT_NAME_RE.match(name):
        raise ValueError(
            f"Invalid account name '{name}'. Must be 1-64 chars of A-Z, a-z, 0-9, '-', '_'."
        )
    return name


def wallet_path_for_name(name: str) -> Path:  # :60
    resolved = validate_account_name(name)
    return WALLETS_DIR / f"wallet_{resolved}.json"


def resolve_wallet_path(name: str) -> tuple[Path, bool]:  # :65
    named_path = wallet_path_for_name(name)
    if named_path.exists():
        return named_path, True
    if name == "default" and LEGACY_WALLET_FILE.exists():
        return LEGACY_WALLET_FILE, True
    return named_path, False


def ensure_wallets_dir() -> None:  # :74
    WALLETS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(WALLETS_DIR, 0o700)
    except OSError:
        pass


def atomic_write_wallet(path: Path, data: dict) -> None:  # :82
    ensure_wallets_dir()
    tmp_path = path.with_suffix(".json.tmp")
    try:
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _extract_keystore(data: dict) -> dict:  # :102
    if isinstance(data, dict) and "keystore" in data:
        inner = data["keystore"]
        if isinstance(inner, dict) and "crypto" in inner:
            return inner
    if isinstance(data, dict) and "crypto" in data:
        return data
    raise ValueError("Data is not a recognised keystore (wrapper, bare, or demo).")


# ---------------------------------------------------------------------------
# Demo account helpers — moved from dincli/cli/utils.py
# get_demo_account_index: Path(__file__) → files("dincli") for SDK portability
# ---------------------------------------------------------------------------


def get_demo_private_key(account_index: int) -> str:  # :122
    accounts_file = files("dincli").joinpath("config", "accounts.json")

    if not accounts_file.exists():
        raise FileNotFoundError(
            f"Demo accounts file not found: {accounts_file}\n"
            "Run `npx hardhat export-accounts` to generate it."
        )

    with open(accounts_file) as f:
        data = json.load(f)

    accounts = data.get("hardhat", [])
    if account_index < 0 or account_index >= len(accounts):
        raise IndexError(
            f"Account index {account_index} out of range. "
            f"Available: 0–{len(accounts) - 1}"
        )

    return accounts[account_index]["private_key"]


def get_demo_account_index(address: str) -> int:  # :146 — path changed to files()
    accounts_file = files("dincli").joinpath("config", "accounts.json")

    if not accounts_file.exists():
        raise FileNotFoundError(
            f"Demo accounts file not found: {accounts_file}\n"
            "Run `npx hardhat export-accounts` to generate it."
        )

    with open(accounts_file) as f:
        data = json.load(f)

    accounts = data.get("hardhat", [])
    target_address = address.lower()

    for idx, account in enumerate(accounts):
        if account["address"].lower() == target_address:
            return idx

    raise ValueError(f"Address {address} not found in demo accounts.")


# ---------------------------------------------------------------------------
# Password cache — moved verbatim from dincli/cli/utils.py
# ---------------------------------------------------------------------------


def _cache_password_in_memory(name: str, password: str, env_pass=_UNSET) -> None:  # :255
    if env_pass is _UNSET:
        env_pass = get_env_key("DIN_WALLET_PASSWORD")
    if env_pass:
        return
    ttl = int(os.environ.get("DIN_PASSWORD_TTL", _PASSWORD_TTL_DEFAULT))
    _PASSWORD_CACHE[name] = (password, time.time() + ttl)


def _clear_memory_cache(name: str | None = None) -> bool:  # :264
    if name is not None:
        return _PASSWORD_CACHE.pop(name, None) is not None
    _PASSWORD_CACHE.clear()
    return True


# ---------------------------------------------------------------------------
# Stale session cleanup — SDK file operation only (console.print stays in CLI)
# ---------------------------------------------------------------------------


def _clean_stale_session_file() -> bool:
    session_file = CONFIG_DIR / ".session"
    if session_file.exists():
        try:
            session_file.unlink()
            return True
        except OSError:
            pass
    return False


# ---------------------------------------------------------------------------
# New: non-interactive password / keystore / account resolution (§1b)
# ---------------------------------------------------------------------------


def resolve_password(name: str, *, env_pass=_UNSET) -> str | None:
    """Non-interactive half of utils._get_password: env var, then TTL cache.

    Returns None when neither source has one — the caller decides whether to
    prompt. Never blocks on stdin.
    """
    if env_pass is _UNSET:
        env_pass = get_env_key("DIN_WALLET_PASSWORD")
    if env_pass:
        return env_pass

    now = time.time()
    entry = _PASSWORD_CACHE.get(name)
    if entry is not None:
        cached_pw, expiry = entry
        if now < expiry:
            return cached_pw
        del _PASSWORD_CACHE[name]

    return None


def load_keystore(name: str) -> dict:
    """Read + validate the on-disk wallet. Raises WalletError (missing/malformed).

    No format or location change (§7).
    """
    wallet_path, exists = resolve_wallet_path(name)
    if not exists:
        raise WalletError(
            f"No wallet found for name '{name}' at {wallet_path}. "
            f"Run `dincli system register-wallet --name {name}` first."
        )

    try:
        with open(wallet_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise WalletError(
            f"No wallet found for name '{name}' at {wallet_path}. "
            f"Run `dincli system register-wallet --name {name}` first."
        ) from e

    return data


def account_from_keystore(keystore: dict, password: str) -> LocalAccount:
    """Decrypt. Raises WalletError on bad password/corrupt keystore."""
    try:
        keystore_data = _extract_keystore(keystore)
        private_key = Account.decrypt(keystore_data, password)
        return Account.from_key(private_key)
    except (ValueError, TypeError) as e:
        raise WalletError("Invalid password or corrupted keystore.") from e


def load_account_noninteractive(name: str = "default") -> LocalAccount:
    """load_account minus every prompt. Demo-mode plaintext short-circuit preserved.

    Raises SignerUnavailable when no non-interactive password source is
    available, WalletError when the keystore is missing/malformed or decryption
    fails.
    """
    data = load_keystore(name)

    if data.get("demo_mode") is True:
        private_key = data["private_key"]
        return Account.from_key(private_key)

    password = resolve_password(name)
    if password is None:
        raise SignerUnavailable(
            f"No password available for wallet '{name}'.",
            details={"account": name},
        )

    account = account_from_keystore(data, password)
    _cache_password_in_memory(name, password)
    _clean_stale_session_file()
    return account


# ---------------------------------------------------------------------------
# SignerProvider implementations (SDK-side, non-interactive) — §1c
# ---------------------------------------------------------------------------


class KeystoreSigner:
    """Non-interactive signer backed by keystore + env/TTL-cache password.

    Satisfies the SignerProvider protocol: address(), can_decrypt(),
    sign_transaction(tx). Never prompts — raises SignerUnavailable when no
    password is available non-interactively.
    """

    def __init__(self, wallet_name: str = "default"):
        self._wallet_name = wallet_name
        self._account: LocalAccount | None = None

    @property
    def local_account(self) -> LocalAccount:
        if self._account is None:
            self._account = load_account_noninteractive(self._wallet_name)
        return self._account

    def address(self) -> str:
        return self.local_account.address

    def can_decrypt(self) -> bool:
        try:
            self.local_account
            return True
        except (SignerUnavailable, WalletError):
            return False

    def sign_transaction(self, tx: dict):
        """Sign a transaction dict and return a SignedTransaction."""
        return self.local_account.sign_transaction(tx)


class PrivateKeySigner:
    """Non-interactive signer backed by a raw private key (demo mode / injected)."""

    def __init__(self, private_key: str):
        self._account = Account.from_key(private_key)

    @property
    def local_account(self) -> LocalAccount:
        return self._account

    def address(self) -> str:
        return self._account.address

    def can_decrypt(self) -> bool:
        return True

    def sign_transaction(self, tx: dict):
        return self._account.sign_transaction(tx)
