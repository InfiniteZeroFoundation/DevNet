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


@pytest.mark.parametrize("code", ["tx_estimation_failed", "tx_failed", "tx_reverted"])
@pytest.mark.parametrize("redact", [False, True])
@pytest.mark.parametrize("with_cause", [False, True])
def test_sdk_transaction_errors_respect_redaction(monkeypatch, code, redact, with_cause):
    from types import SimpleNamespace
    from dincli.sdk import tx
    from dincli.sdk.errors import TransactionError

    secret = "synthetic-audit-payload-secret"
    error = TransactionError(secret, code=code)
    if with_cause:
        error.__cause__ = RuntimeError(secret)

    def fail(*args, **kwargs):
        raise error

    output = []
    console = SimpleNamespace(print=output.append)
    ctx = SimpleNamespace(obj=SimpleNamespace(
        session=object(),
        get_en_w3_account_console=lambda: (None, None, None, console),
    ))
    monkeypatch.setattr(tx, "send", fail)
    assert utils.build_and_send_tx(
        ctx, object(), "Sending", "Sent", "Failed",
        exit_on_failure=False, redact_exception=redact,
    ) is None
    rendered = "\n".join(output)
    assert (secret in rendered) == (not redact and code != "tx_reverted")
    if redact and code == "tx_estimation_failed":
        assert "Transaction estimation failed." in rendered
