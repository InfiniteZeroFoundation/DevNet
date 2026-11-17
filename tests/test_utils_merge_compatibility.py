"""Keep SDK wallet re-exports intact beside the CLI secret-write helper."""

import pytest

from dincli.cli import utils
from dincli.sdk import wallet


@pytest.mark.parametrize(
    "name",
    [
        "validate_account_name",
        "wallet_path_for_name",
        "resolve_wallet_path",
        "ensure_wallets_dir",
        "atomic_write_wallet",
        "_extract_keystore",
    ],
)
def test_wallet_helpers_remain_sdk_reexports(name):
    # The develop insertion of write_private_text was next to these removed
    # definitions. Restoring them would silently shadow the SDK exports.
    assert getattr(utils, name) is getattr(wallet, name)


def test_wallet_paths_still_use_sdk_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(wallet, "WALLETS_DIR", tmp_path)
    expected = tmp_path / "wallet_merge-test.json"
    assert utils.wallet_path_for_name("merge-test") == expected
    assert utils.resolve_wallet_path("merge-test") == (expected, False)
    utils.atomic_write_wallet(expected, {"merge": "sdk"})
    assert utils.resolve_wallet_path("merge-test") == (expected, True)
