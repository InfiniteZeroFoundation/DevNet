"""Explicit preparation of disposable wallets for the local integration suite."""

import json
from pathlib import Path

from eth_account import Account


# Public Anvil/Hardhat development seed; these accounts are for local tests only.
DEMO_MNEMONIC = "test test test test test test test test test test test junk"
DEMO_ADDRESSES = (
    "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
    "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
)


def generate_demo_accounts(accounts_path: Path) -> Path:
    """Write accounts 0/1 at the caller's explicit disposable package path.

    An existing destination is always refused, including a symlink. Never call
    this with a user's checkout/config path; the caller owns cleanup of the
    isolated package containing this file.
    """
    accounts_path = Path(accounts_path)
    if accounts_path.exists() or accounts_path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite demo accounts: {accounts_path}")

    Account.enable_unaudited_hdwallet_features()
    accounts = []
    for index, expected_address in enumerate(DEMO_ADDRESSES):
        account = Account.from_mnemonic(
            DEMO_MNEMONIC, account_path=f"m/44'/60'/0'/0/{index}"
        )
        if account.address != expected_address:
            raise ValueError(f"Unexpected public demo address for account {index}")
        accounts.append({
            "address": account.address,
            "private_key": "0x" + account.key.hex(),
        })

    accounts_path.parent.mkdir(parents=True, exist_ok=True)
    with accounts_path.open("x", encoding="utf-8") as file:
        json.dump({"hardhat": accounts}, file, indent=2)
        file.write("\n")
    return accounts_path


def bootstrap_demo(run) -> None:
    """Configure local demo mode and connect the two named test role wallets."""
    run(["system", "init"])
    run(["system", "configure-demo", "--mode", "yes"])
    run(["system", "configure-network", "--network", "local"])
    run(["system", "connect-demo-wallet", "dinrep", "--account", "0", "--yes"])
    run(["system", "connect-demo-wallet", "modelowner", "--account", "1", "--yes"])
