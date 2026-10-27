"""Local unit coverage for integration setup, without starting its services."""

import json

import pytest
from eth_account import Account

from tests.dincli.demo import bootstrap_demo, generate_demo_accounts, prepare_demo_accounts



def test_generate_demo_accounts_uses_public_anvil_accounts(tmp_path):
    accounts_path = tmp_path / "dincli" / "config" / "accounts.json"

    assert generate_demo_accounts(accounts_path) == accounts_path

    data = json.loads(accounts_path.read_text(encoding="utf-8"))
    assert set(data) == {"hardhat"}
    assert len(data["hardhat"]) == 2
    assert [account["address"] for account in data["hardhat"]] == [
        "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    ]
    assert data["hardhat"][0]["private_key"] == (
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    )
    for account in data["hardhat"]:
        assert set(account) == {"address", "private_key"}
        assert account["private_key"].startswith("0x")
        assert len(account["private_key"]) == 66
        assert Account.from_key(account["private_key"]).address == account["address"]
    assert list(tmp_path.rglob("accounts.json")) == [accounts_path]


def test_generate_demo_accounts_preserves_existing_file(tmp_path):
    accounts_path = tmp_path / "accounts.json"
    original = b'{"custom": "user data"}\n'
    accounts_path.write_bytes(original)

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        generate_demo_accounts(accounts_path)

    assert accounts_path.read_bytes() == original


def test_generate_demo_accounts_refuses_dangling_symlink(tmp_path):
    target = tmp_path / "missing.json"
    accounts_path = tmp_path / "accounts.json"
    accounts_path.symlink_to(target)

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        generate_demo_accounts(accounts_path)

    assert accounts_path.is_symlink()
    assert not target.exists()


def test_bootstrap_demo_uses_noninteractive_commands_in_order():
    commands = []

    bootstrap_demo(commands.append)

    assert commands == [
        ["system", "init"],
        ["system", "configure-demo", "--mode", "yes"],
        ["system", "configure-network", "--network", "local"],
        ["system", "connect-demo-wallet", "dinrep", "--account", "0", "--yes"],
        ["system", "connect-demo-wallet", "modelowner", "--account", "1", "--yes"],
    ]


def test_bootstrap_demo_stops_after_runner_failure():
    commands = []

    def failing_run(args):
        commands.append(args)
        raise RuntimeError("command failed")

    with pytest.raises(RuntimeError, match="command failed"):
        bootstrap_demo(failing_run)

    assert commands == [["system", "init"]]


def test_prepare_demo_accounts_preserves_checked_in_public_accounts():
    from pathlib import Path

    accounts_path = Path(__file__).resolve().parents[1] / "dincli/config/accounts.json"
    original = accounts_path.read_bytes()
    assert prepare_demo_accounts(accounts_path) is False
    assert accounts_path.read_bytes() == original


def test_prepare_demo_accounts_reports_ownership_of_generated_file(tmp_path):
    accounts_path = tmp_path / "accounts.json"
    assert prepare_demo_accounts(accounts_path) is True
    assert accounts_path.exists()


@pytest.mark.parametrize("invalid", ["malformed-json", "missing-account", "wrong-address", "wrong-key"])
def test_prepare_demo_accounts_rejects_invalid_data_without_changing_it(tmp_path, invalid):
    accounts_path = tmp_path / "accounts.json"
    generate_demo_accounts(accounts_path)
    data = json.loads(accounts_path.read_text())
    if invalid == "missing-account":
        data["hardhat"].pop()
    elif invalid == "wrong-address":
        data["hardhat"][0]["address"] = data["hardhat"][1]["address"]
    elif invalid == "wrong-key":
        data["hardhat"][0]["private_key"] = data["hardhat"][1]["private_key"]
    accounts_path.write_text("invalid" if invalid == "malformed-json" else json.dumps(data))
    original = accounts_path.read_bytes()
    with pytest.raises(ValueError, match="Invalid public demo accounts"):
        prepare_demo_accounts(accounts_path)
    assert accounts_path.read_bytes() == original


def test_prepare_demo_accounts_refuses_symlink(tmp_path):
    target = tmp_path / "public-accounts.json"
    generate_demo_accounts(target)
    accounts_path = tmp_path / "accounts.json"
    accounts_path.symlink_to(target)
    with pytest.raises(ValueError, match="Refusing symlink"):
        prepare_demo_accounts(accounts_path)
    assert accounts_path.is_symlink()
