"""Transaction display and receipt handling with optional explorer metadata."""
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from hexbytes import HexBytes
from rich.console import Console

from dincli.cli import utils


TX_HASH_STRING = "0x" + "AbC123ef" * 8
TX_HASH_BYTES = bytes.fromhex(TX_HASH_STRING[2:])
TX_HASH_HEXBYTES = HexBytes(TX_HASH_BYTES)


@pytest.fixture
def captured_console(monkeypatch):
    output = StringIO()
    console = Console(file=output, width=240, color_system=None, force_terminal=False)
    monkeypatch.setattr(utils, "console", console)
    return console, output


@pytest.mark.parametrize(
    ("network", "explorer"),
    [("local", None), ("sepolia_op_devnet", "https://sepolia-optimism.etherscan.io")],
)
def test_bundled_explorer_metadata(network, explorer, captured_console):
    _, output = captured_console
    config = utils.load_din_info()
    if explorer is None:
        assert "explorer" not in config[network]
    else:
        assert config[network]["explorer"] == explorer

    utils.print_tx_info(TX_HASH_STRING, network)

    expected = f"Transaction hash: {TX_HASH_STRING}\n"
    if explorer:
        expected += f"Transaction url: {explorer}/tx/{TX_HASH_STRING}\n"
    assert output.getvalue() == expected


@pytest.mark.parametrize("metadata", [{}, {"explorer": ""}, {"explorer": None}])
def test_absent_explorer_prints_hash_only(metadata, monkeypatch, captured_console):
    monkeypatch.setattr(utils, "load_din_info", lambda: {"local": metadata})
    utils.print_tx_info(TX_HASH_STRING, "local")
    assert captured_console[1].getvalue() == f"Transaction hash: {TX_HASH_STRING}\n"


@pytest.mark.parametrize("network", ["unknown", None])
def test_missing_network_prints_hash_only(network, monkeypatch, captured_console):
    monkeypatch.setattr(utils, "load_din_info", lambda: {"local": {}})
    if network is None:
        utils.print_tx_info(TX_HASH_STRING)
    else:
        utils.print_tx_info(TX_HASH_STRING, network)
    assert captured_console[1].getvalue() == f"Transaction hash: {TX_HASH_STRING}\n"


def test_suppressing_url_does_not_load_metadata(monkeypatch, captured_console):
    loader = Mock(side_effect=AssertionError("metadata should not be loaded"))
    monkeypatch.setattr(utils, "load_din_info", loader)
    utils.print_tx_info(TX_HASH_STRING, "local", print_url=False)
    loader.assert_not_called()
    assert captured_console[1].getvalue() == f"Transaction hash: {TX_HASH_STRING}\n"


@pytest.mark.parametrize("explorer", ["http://localhost:4000", "http://localhost:4000/"])
@pytest.mark.parametrize("tx_hash", [TX_HASH_STRING, TX_HASH_BYTES, TX_HASH_HEXBYTES])
def test_custom_local_explorer_preserves_hash_format(
    explorer, tx_hash, monkeypatch, captured_console
):
    monkeypatch.setattr(utils, "load_din_info", lambda: {"local": {"explorer": explorer}})
    utils.print_tx_info(tx_hash, "local")
    expected_hash = tx_hash.hex() if isinstance(tx_hash, bytes) else tx_hash
    assert captured_console[1].getvalue() == (
        f"Transaction hash: {expected_hash}\n"
        f"Transaction url: http://localhost:4000/tx/{expected_hash}\n"
    )


def test_missing_explorer_does_not_interrupt_receipt_wait(monkeypatch, captured_console):
    console, output = captured_console
    monkeypatch.setattr(utils, "load_din_info", lambda: {"local": {}})
    tx_hash = TX_HASH_HEXBYTES
    receipt = SimpleNamespace(status=1)
    eth = SimpleNamespace(
        estimate_gas=Mock(return_value=21000),
        send_raw_transaction=Mock(return_value=tx_hash),
        wait_for_transaction_receipt=Mock(return_value=receipt),
    )
    account = SimpleNamespace(
        sign_transaction=Mock(return_value=SimpleNamespace(raw_transaction=b"signed"))
    )
    context = SimpleNamespace(obj=SimpleNamespace(
        get_en_w3_account_console=lambda: (
            "local", SimpleNamespace(eth=eth), account, console
        ),
        get_tx_params=lambda: {"nonce": 0},
    ))
    contract_function = SimpleNamespace(build_transaction=Mock(return_value={"nonce": 0}))

    result = utils.build_and_send_tx(
        context, contract_function, "Sending transaction", "Transaction succeeded",
        "Transaction failed", exit_on_failure=False,
    )

    eth.send_raw_transaction.assert_called_once_with(b"signed")
    eth.wait_for_transaction_receipt.assert_called_once_with(tx_hash)
    assert result is receipt
    text = output.getvalue()
    assert f"Transaction hash: {tx_hash.hex()}\n" in text
    assert "✓ Transaction succeeded" in text
    assert "Transaction failed" not in text
    assert "Exception:" not in text
    assert "Transaction url:" not in text
    assert "http" not in text
