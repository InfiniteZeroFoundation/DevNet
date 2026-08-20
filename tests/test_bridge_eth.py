"""Tests for `dincli system bridge-eth`.

Run through the real Typer app via CliRunner — never by calling the
handler directly. Calling the function directly bypasses the `system`
callback, which is the exact mechanism §3.1 fixes.
"""

from __future__ import annotations

import math
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from eth_account import Account
from typer.testing import CliRunner

from dincli.main import app
from dincli.services import bridge as bridge_service

runner = CliRunner()

L1 = bridge_service.L1_CHAIN_ID
L2 = bridge_service.L2_CHAIN_ID


# ------------------------------------------------------------------ #
#  Helpers                                                            #
# ------------------------------------------------------------------ #

def make_w3(chain_id, *, balance=10**18, bridge_code=b"\x01", eoa_code=b"", paused=False):
    """Build a MagicMock Web3 whose eth namespace answers like a node."""
    w3 = MagicMock()
    w3.eth.chain_id = chain_id

    def get_code(address):
        if address == bridge_service.L1_STANDARD_BRIDGE_SEPOLIA:
            return bridge_code
        return eoa_code

    w3.eth.get_code.side_effect = get_code
    w3.eth.get_balance.return_value = balance
    w3.eth.get_block.return_value = {"baseFeePerGas": 10**9}
    w3.eth.max_priority_fee = 10**9
    w3.eth.get_transaction_count.return_value = 5
    w3.eth.estimate_gas.return_value = 100_000
    w3.eth.contract.return_value.functions.paused.return_value.call.return_value = paused
    w3.from_wei.side_effect = lambda value, unit: f"{value}_{unit}"
    return w3


def make_account(address="0x" + "11" * 20):
    acct = MagicMock()
    acct.address = address
    acct.key = bytes.fromhex("22" * 32)
    return acct


def patch_context(monkeypatch, *, l1_w3, l2_w3, account):
    """Point the context's account/w3 loads and the L1 connect at mocks."""
    # develop's context calls load_account(name=...) (context.py:79), so the
    # patch must accept the keyword — main's zero-arg lambda does not.
    monkeypatch.setattr("dincli.cli.context.load_account", lambda name=None: account)
    monkeypatch.setattr("dincli.cli.context.get_w3", lambda network: l2_w3)
    monkeypatch.setattr("dincli.services.bridge.connect_l1_rpc", lambda url: l1_w3)


def bridge_args(*extra, network="sepolia_op_devnet", amount="0.01"):
    return [
        "--network", network,
        "system", "bridge-eth",
        "--amount", amount,
        "--l1-rpc-url", "http://rpc.example/sentinel",
        *extra,
    ]


def fail_if_called(name):
    def boom(*args, **kwargs):
        raise AssertionError(f"{name} must not be called")
    return boom


# ------------------------------------------------------------------ #
#  Ordering and refusal                                               #
# ------------------------------------------------------------------ #

def test_wrong_network_zero_rpc(monkeypatch):
    """Wrong network is refused before any RPC — the §3.1 skip-list fix."""
    monkeypatch.setattr("dincli.cli.context.load_account", fail_if_called("load_account"))
    monkeypatch.setattr("dincli.cli.context.get_w3", fail_if_called("get_w3"))
    monkeypatch.setattr(
        "dincli.services.bridge.connect_l1_rpc", fail_if_called("connect_l1_rpc")
    )

    result = runner.invoke(app, bridge_args(network="local"))

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "requires network 'sepolia_op_devnet'" in result.output


def test_l1_chain_mismatch(monkeypatch):
    account = make_account()
    l2_w3 = make_w3(L2)
    l1_w3 = make_w3(999999)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)

    result = runner.invoke(app, bridge_args())

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "L1 chain ID mismatch" in result.output


def test_l2_chain_mismatch(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(999999)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)

    result = runner.invoke(app, bridge_args())

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "L2 chain ID mismatch" in result.output


def test_bridge_without_bytecode(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1, bridge_code=b"")
    l2_w3 = make_w3(L2)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)

    result = runner.invoke(app, bridge_args())

    assert result.exit_code == 1
    assert "bridge proxy has no bytecode on L1" in result.output


def test_bridge_paused(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1, paused=True)
    l2_w3 = make_w3(L2)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)

    result = runner.invoke(app, bridge_args())

    assert result.exit_code == 1
    assert "paused" in result.output


def test_sender_with_l1_code(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1, eoa_code=b"\x60")
    l2_w3 = make_w3(L2)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)

    result = runner.invoke(app, bridge_args())

    assert result.exit_code == 1
    assert "Sender (L1)" in result.output


def test_recipient_with_l2_code(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2, eoa_code=b"\x60")
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)

    result = runner.invoke(app, bridge_args())

    assert result.exit_code == 1
    assert "Recipient (L2)" in result.output


def test_missing_l1_rpc_config_names_both_routes(monkeypatch):
    monkeypatch.setattr("dincli.cli.system.get_env_key", lambda key, verbose=False: None)

    # No --l1-rpc-url flag: only the env route is available.
    result = runner.invoke(
        app,
        ["--network", "sepolia_op_devnet", "system", "bridge-eth", "--amount", "0.01"],
    )

    assert result.exit_code == 1
    assert "--l1-rpc-url" in result.output
    assert "SEPOLIA_L1_RPC_URL" in result.output


# ------------------------------------------------------------------ #
#  Transaction construction                                           #
# ------------------------------------------------------------------ #

def test_buffered_gas_uses_ceiling(monkeypatch):
    l1_w3 = make_w3(L1)
    l1_w3.eth.estimate_gas.return_value = 100_001  # ×1.2 = 120001.2

    tx, estimated = bridge_service.prepare_transaction(
        l1_w3=l1_w3,
        sender="0x" + "11" * 20,
        amount_wei=10**18,
    )

    assert estimated == 100_001
    assert tx["gas"] == math.ceil(100_001 * 1.20)


def test_never_sends_21000(monkeypatch):
    l1_w3 = make_w3(L1)
    l1_w3.eth.estimate_gas.return_value = 21_000

    tx, _ = bridge_service.prepare_transaction(
        l1_w3=l1_w3,
        sender="0x" + "11" * 20,
        amount_wei=10**18,
    )

    assert tx["gas"] != 21_000
    assert tx["gas"] == math.ceil(21_000 * 1.20)


def test_affordability_uses_buffered_gas_times_fee_cap():
    l1_w3 = make_w3(L1)
    value = 10**18
    gas_limit = 120_000
    max_fee = 3 * 10**9
    required = value + gas_limit * max_fee

    # Exactly affordable passes.
    l1_w3.eth.get_balance.return_value = required
    bridge_service.affordability_check(
        l1_w3=l1_w3,
        sender="0x" + "11" * 20,
        value=value,
        gas_limit=gas_limit,
        max_fee_per_gas=max_fee,
    )

    # One wei short fails.
    l1_w3.eth.get_balance.return_value = required - 1
    with pytest.raises(bridge_service.PreflightRejected):
        bridge_service.affordability_check(
            l1_w3=l1_w3,
            sender="0x" + "11" * 20,
            value=value,
            gas_limit=gas_limit,
            max_fee_per_gas=max_fee,
        )


def test_nonce_uses_pending():
    l1_w3 = make_w3(L1)

    bridge_service.prepare_transaction(
        l1_w3=l1_w3,
        sender="0x" + "11" * 20,
        amount_wei=10**18,
    )

    l1_w3.eth.get_transaction_count.assert_called_once_with("0x" + "11" * 20, "pending")


def test_max_fee_ge_priority_fee():
    l1_w3 = make_w3(L1)

    tx, _ = bridge_service.prepare_transaction(
        l1_w3=l1_w3,
        sender="0x" + "11" * 20,
        amount_wei=10**18,
    )

    assert tx["maxFeePerGas"] >= tx["maxPriorityFeePerGas"]


def test_signed_tx_carries_l1_chain_id():
    l1_w3 = make_w3(L1)

    tx, _ = bridge_service.prepare_transaction(
        l1_w3=l1_w3,
        sender="0x" + "11" * 20,
        amount_wei=10**18,
    )

    assert tx["chainId"] == L1


def test_sign_deposit_computes_hash_locally():
    account = Account.from_key(bytes.fromhex("22" * 32))
    tx = {
        "from": account.address,
        "to": bridge_service.L1_STANDARD_BRIDGE_SEPOLIA,
        "value": 10**18,
        "data": b"",
        "chainId": L1,
        "nonce": 0,
        "maxFeePerGas": 3 * 10**9,
        "maxPriorityFeePerGas": 10**9,
        "gas": 120_000,
    }

    signed, tx_hash = bridge_service.sign_deposit(sender_account=account, tx=tx)

    assert tx_hash.startswith("0x")
    assert not tx_hash.startswith("0x0x")
    assert len(tx_hash) == 66
    assert bridge_service._hex0x(signed.hash) == tx_hash


def test_broadcast_uses_a_real_signed_transaction_object():
    """Exercise the real broadcast path with a genuinely signed tx.

    Every other broadcast test monkeypatches broadcast_and_wait or passes a
    MagicMock, and a MagicMock invents any attribute you ask it for — so an
    incorrect attribute name on the signed object passes those tests and
    fails only at the moment of broadcast. eth-account 0.13 renamed
    rawTransaction to raw_transaction; this asserts we send the real bytes.
    """
    account = Account.from_key(bytes.fromhex("33" * 32))
    tx = {
        "from": account.address,
        "to": bridge_service.L1_STANDARD_BRIDGE_SEPOLIA,
        "value": 10**15,
        "data": b"",
        "chainId": L1,
        "nonce": 0,
        "maxFeePerGas": 3 * 10**9,
        "maxPriorityFeePerGas": 10**9,
        "gas": 700_000,
    }
    signed, tx_hash = bridge_service.sign_deposit(sender_account=account, tx=tx)

    l1_w3 = MagicMock()
    receipt = MagicMock()
    receipt.status = 1
    receipt.blockNumber = 4242
    receipt.transactionHash = signed.hash
    l1_w3.eth.wait_for_transaction_receipt.return_value = receipt

    returned_hash, block = bridge_service.broadcast_and_wait(
        l1_w3=l1_w3, signed=signed, tx_hash=tx_hash
    )

    assert returned_hash == tx_hash
    assert block == 4242

    # The exact signed bytes must reach the node — not a MagicMock attribute.
    sent = l1_w3.eth.send_raw_transaction.call_args[0][0]
    assert sent == signed.raw_transaction
    assert isinstance(bytes(sent), bytes) and len(bytes(sent)) > 0


# ------------------------------------------------------------------ #
#  Amount and timeout validation                                      #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("bad", ["0", "-0.1", "nan", "inf", "-inf", "0.0000000000000000001", "abc", ""])
def test_invalid_amounts(bad):
    with pytest.raises(bridge_service.PreflightRejected):
        bridge_service.parse_amount(bad)


def test_valid_amount():
    assert bridge_service.parse_amount("0.01") == 10**16
    assert bridge_service.parse_amount("1") == 10**18


def test_negative_timeout(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)

    result = runner.invoke(app, bridge_args("--timeout", "-1"))

    assert result.exit_code == 1
    assert "timeout must be non-negative" in result.output


# ------------------------------------------------------------------ #
#  Broadcast safety                                                   #
# ------------------------------------------------------------------ #

def _patch_broadcast(monkeypatch, account, l1_w3, l2_w3, *, sign_result, broadcast_result):
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)
    monkeypatch.setattr("dincli.services.bridge.sign_deposit", sign_result)
    monkeypatch.setattr("dincli.services.bridge.broadcast_and_wait", broadcast_result)


def test_dry_run_no_prompt_no_l2_baseline_no_sign(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)
    monkeypatch.setattr(
        "dincli.services.bridge.sign_deposit",
        fail_if_called("sign_deposit"),
    )

    result = runner.invoke(app, bridge_args("--dry-run"))

    assert result.exit_code == 0
    assert "Traceback" not in result.output
    assert "Unsigned transaction" in result.output
    assert "Send this deposit" not in result.output
    # L2 baseline read must not happen without --wait (and dry-run exits early).
    assert l2_w3.eth.get_balance.call_count == 0


def test_decline_confirmation_signs_and_sends_nothing(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)
    monkeypatch.setattr(
        "dincli.services.bridge.sign_deposit",
        fail_if_called("sign_deposit"),
    )

    result = runner.invoke(app, bridge_args(), input="n\n")

    assert result.exit_code == 0
    assert "Operation cancelled — nothing signed" in result.output
    assert l2_w3.eth.get_balance.call_count == 0


def test_broadcast_error_after_local_hash_surfaces_hash(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)

    def sign_deposit(**kwargs):
        return MagicMock(), "0xLOCALHASH"

    def broadcast_and_wait(**kwargs):
        raise bridge_service.SubmissionUnknown(
            "broadcast transport failure — submission status unknown, "
            "check this hash before retrying: 0xLOCALHASH"
        )

    _patch_broadcast(
        monkeypatch, account, l1_w3, l2_w3,
        sign_result=sign_deposit,
        broadcast_result=broadcast_and_wait,
    )

    result = runner.invoke(app, bridge_args("--yes"))

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "0xLOCALHASH" in result.output
    assert "submission status unknown" in result.output


def test_l1_receipt_timeout_submission_unknown(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)

    def sign_deposit(**kwargs):
        return MagicMock(), "0xLOCALHASH"

    def broadcast_and_wait(**kwargs):
        raise bridge_service.SubmissionUnknown(
            "L1 receipt wait failed — submission status unknown, "
            "check this hash before retrying: 0xLOCALHASH"
        )

    _patch_broadcast(
        monkeypatch, account, l1_w3, l2_w3,
        sign_result=sign_deposit,
        broadcast_result=broadcast_and_wait,
    )

    result = runner.invoke(app, bridge_args("--yes"))

    assert result.exit_code == 1
    assert "0xLOCALHASH" in result.output
    # Rich wraps long lines; assert on the anti-retry stem.
    assert "check this hash before" in result.output


def test_receipt_hash_mismatch(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)

    def sign_deposit(**kwargs):
        return MagicMock(), "0xLOCALHASH"

    def broadcast_and_wait(**kwargs):
        raise bridge_service.SubmissionUnknown(
            "receipt hash mismatch — submission status unknown, "
            "check this hash before retrying: 0xLOCALHASH"
        )

    _patch_broadcast(
        monkeypatch, account, l1_w3, l2_w3,
        sign_result=sign_deposit,
        broadcast_result=broadcast_and_wait,
    )

    result = runner.invoke(app, bridge_args("--yes"))

    assert result.exit_code == 1
    assert "0xLOCALHASH" in result.output


def test_deterministic_node_rejection_still_prints_hash(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)

    def sign_deposit(**kwargs):
        return MagicMock(), "0xLOCALHASH"

    def broadcast_and_wait(**kwargs):
        raise bridge_service.SubmissionRejected("node rejected the transaction — hash: 0xLOCALHASH")

    _patch_broadcast(
        monkeypatch, account, l1_w3, l2_w3,
        sign_result=sign_deposit,
        broadcast_result=broadcast_and_wait,
    )

    result = runner.invoke(app, bridge_args("--yes"))

    assert result.exit_code == 1
    assert "0xLOCALHASH" in result.output
    assert "node rejected" in result.output


def test_reverted_prints_included_in_block(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)

    def sign_deposit(**kwargs):
        return MagicMock(), "0xLOCALHASH"

    def broadcast_and_wait(**kwargs):
        raise bridge_service.Reverted(
            "transaction reverted — included in block 123, hash: 0xLOCALHASH"
        )

    _patch_broadcast(
        monkeypatch, account, l1_w3, l2_w3,
        sign_result=sign_deposit,
        broadcast_result=broadcast_and_wait,
    )

    result = runner.invoke(app, bridge_args("--yes"))

    assert result.exit_code == 1
    assert "included in block 123" in result.output
    assert "0xLOCALHASH" in result.output


# ------------------------------------------------------------------ #
#  Waiting                                                            #
# ------------------------------------------------------------------ #

def test_successful_l2_balance_increase(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)
    monkeypatch.setattr(
        "dincli.services.bridge.sign_deposit",
        lambda **kwargs: (MagicMock(), "0xLOCALHASH"),
    )
    monkeypatch.setattr(
        "dincli.services.bridge.broadcast_and_wait",
        lambda **kwargs: ("0xLOCALHASH", 123),
    )
    monkeypatch.setattr(
        "dincli.services.bridge.poll_l2_balance",
        lambda **kwargs: True,
    )

    result = runner.invoke(app, bridge_args("--yes"))

    assert result.exit_code == 0
    assert "balance increase observed" in result.output


def test_no_wait_prints_submitted_delivery_pending(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)
    monkeypatch.setattr(
        "dincli.services.bridge.sign_deposit",
        lambda **kwargs: (MagicMock(), "0xLOCALHASH"),
    )
    monkeypatch.setattr(
        "dincli.services.bridge.broadcast_and_wait",
        lambda **kwargs: ("0xLOCALHASH", 123),
    )

    result = runner.invoke(app, bridge_args("--no-wait", "--yes"))

    assert result.exit_code == 0
    assert "submitted, delivery pending" in result.output
    assert "0xLOCALHASH" in result.output


def test_polling_tolerates_transient_l2_failure(monkeypatch):
    account = make_account()
    l1_w3 = make_w3(L1)
    l2_w3 = make_w3(L2)
    patch_context(monkeypatch, l1_w3=l1_w3, l2_w3=l2_w3, account=account)
    monkeypatch.setattr(
        "dincli.services.bridge.sign_deposit",
        lambda **kwargs: (MagicMock(), "0xLOCALHASH"),
    )
    monkeypatch.setattr(
        "dincli.services.bridge.broadcast_and_wait",
        lambda **kwargs: ("0xLOCALHASH", 123),
    )

    # Poll returns False on timeout after tolerating a few failures.
    monkeypatch.setattr(
        "dincli.services.bridge.poll_l2_balance",
        lambda **kwargs: False,
    )

    result = runner.invoke(app, bridge_args("--yes"))

    assert result.exit_code == 0
    assert "not visible yet on L2" in result.output
    assert "0xLOCALHASH" in result.output


def test_poll_l2_balance_tolerates_transient_rpc_errors(monkeypatch):
    """Direct unit test: transient L2 RPC failures are swallowed within the timeout."""
    l2_w3 = make_w3(L2)
    calls = {"n": 0}

    def get_balance(address):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("transient")
        return 10**18 + 1  # above baseline

    l2_w3.eth.get_balance.side_effect = get_balance

    arrived = bridge_service.poll_l2_balance(
        l2_w3=l2_w3,
        address="0x" + "11" * 20,
        baseline_wei=10**18,
        timeout=30,
        poll_interval=0,
    )

    assert arrived is True
    assert calls["n"] == 2


# ------------------------------------------------------------------ #
#  Credential safety                                                  #
# ------------------------------------------------------------------ #

def test_sentinel_secret_never_leaks(monkeypatch):
    secret = "SENTINEL_SECRET_9f3a"
    url = f"https://user:{secret}@rpc.example.com/v1/{secret}"

    def connect_l1_rpc(url_arg):
        raise bridge_service.PreflightRejected("could not connect to the L1 RPC endpoint")

    monkeypatch.setattr("dincli.services.bridge.connect_l1_rpc", connect_l1_rpc)

    result = runner.invoke(app, bridge_args("--l1-rpc-url", url))

    assert result.exit_code == 1
    assert secret not in result.output
    assert "rpc.example.com" not in result.output
    assert "could not connect to the L1 RPC endpoint" in result.output


# ------------------------------------------------------------------ #
#  Develop-specific coverage (plan §5) — gaps in main's suite          #
# ------------------------------------------------------------------ #

def _capture_l1_url(monkeypatch):
    captured = {}

    def connect_l1_rpc(url):
        captured["url"] = url
        raise bridge_service.PreflightRejected("could not connect to the L1 RPC endpoint")

    monkeypatch.setattr("dincli.services.bridge.connect_l1_rpc", connect_l1_rpc)
    return captured


def test_explicit_l1_rpc_flag_wins_over_env(monkeypatch):
    """An explicit --l1-rpc-url takes precedence over SEPOLIA_L1_RPC_URL."""
    monkeypatch.setattr(
        "dincli.cli.system.get_env_key",
        lambda key, default=None, verbose=True: "http://env.example/eth-sepolia",
    )
    captured = _capture_l1_url(monkeypatch)

    result = runner.invoke(app, bridge_args())

    assert result.exit_code == 1
    assert captured["url"] == "http://rpc.example/sentinel"


def test_whitespace_l1_rpc_flag_falls_back_to_env(monkeypatch):
    """A whitespace-only --l1-rpc-url defers to SEPOLIA_L1_RPC_URL."""
    monkeypatch.setattr(
        "dincli.cli.system.get_env_key",
        lambda key, default=None, verbose=True: "http://env.example/eth-sepolia",
    )
    captured = _capture_l1_url(monkeypatch)

    result = runner.invoke(
        app,
        [
            "--network", "sepolia_op_devnet",
            "system", "bridge-eth",
            "--amount", "0.01",
            "--l1-rpc-url", "   ",
        ],
    )

    assert result.exit_code == 1
    # The env route was taken (the env value itself is used unstripped).
    assert captured["url"].strip() == "http://env.example/eth-sepolia"
    assert "sentinel" not in captured["url"]


def test_transport_error_classifies_as_submission_unknown():
    """The ambiguous case must never be reported as a clean failure."""
    for exc in (ConnectionError("down"), TimeoutError("slow")):
        classified = bridge_service.classify_broadcast_error(exc, "0xHASH")
        assert isinstance(classified, bridge_service.SubmissionUnknown)
        assert not isinstance(classified, bridge_service.SubmissionRejected)

    # requests-specific transport classes hit the same branch when present.
    if bridge_service.requests is not None:
        for exc in (
            bridge_service.requests.ConnectionError("down"),
            bridge_service.requests.Timeout("slow"),
        ):
            classified = bridge_service.classify_broadcast_error(exc, "0xHASH")
            assert isinstance(classified, bridge_service.SubmissionUnknown)


def test_rpc_rejection_classifies_as_submission_rejected():
    from web3.exceptions import Web3RPCError

    classified = bridge_service.classify_broadcast_error(
        Web3RPCError("nonce too low"), "0xHASH"
    )

    assert isinstance(classified, bridge_service.SubmissionRejected)
    assert not isinstance(classified, bridge_service.SubmissionUnknown)


def test_non_string_amounts():
    """int/float/Decimal inputs work as documented; bool is not a number."""
    assert bridge_service.parse_amount(1) == 10**18
    assert bridge_service.parse_amount(0.01) == 10**16
    assert bridge_service.parse_amount(Decimal("0.000000001")) == 10**9
    assert bridge_service.parse_amount(Decimal("1")) == 10**18

    # bool is a subclass of int — it must not slip through as 1/0.
    with pytest.raises(bridge_service.PreflightRejected):
        bridge_service.parse_amount(True)
    with pytest.raises(bridge_service.PreflightRejected):
        bridge_service.parse_amount(False)


def test_send_eth_still_reaches_own_callback(monkeypatch):
    """Regression (§4.5): send-eth still runs after the new import and the
    skip-list edit. It reaches its own address validation, which proves the
    command executed rather than just being registered."""
    account = make_account()
    l2_w3 = make_w3(11155420)
    l2_w3.provider.endpoint_uri = "http://127.0.0.1:8545"
    l2_w3.to_checksum_address.side_effect = ValueError("not an address")
    monkeypatch.setattr("dincli.cli.context.load_account", lambda name=None: account)
    monkeypatch.setattr("dincli.cli.context.get_w3", lambda network: l2_w3)

    result = runner.invoke(
        app,
        [
            "--network", "local",
            "system", "send-eth",
            "--amount", "0.01",
            "--to", "notanaddress",
        ],
    )

    assert result.exit_code == 1
    assert "Invalid recipient address" in result.output
    assert "Traceback" not in result.output


def test_unfunded_l1_gas_estimate_is_a_preflight_rejection():
    """An unfunded L1 sender must get one actionable line, not a traceback.

    Gas estimation is the first call that touches the sender's balance, so it
    fails before affordability_check — where the readable message lives. Found
    by running --dry-run live against a real Ethereum Sepolia RPC with an
    unfunded key: the node's Web3RPCError propagated uncaught, because the
    command handles only BridgeError and ConnectionError. That is the single
    most likely first run of this command.
    """
    class _Eth:
        def get_block(self, _):
            return {"baseFeePerGas": 10**9}

        @property
        def max_priority_fee(self):
            return 10**8

        def get_transaction_count(self, _sender, _block):
            return 0

        def estimate_gas(self, _tx):
            raise Exception("{'code': -32000, 'message': 'insufficient funds for transfer'}")

        def get_balance(self, _sender):
            return 0

    class _W3:
        eth = _Eth()

    sender = "0x00000000000000000000000000000000000000aB"
    with pytest.raises(bridge_service.PreflightRejected) as excinfo:
        bridge_service.prepare_transaction(
            l1_w3=_W3(), sender=sender, amount_wei=2 * 10**15
        )

    message = str(excinfo.value)
    assert "insufficient L1 funds" in message
    assert sender in message                    # says which address to fund
    assert "0.002" in message                   # and how much was attempted
    assert excinfo.value.__cause__ is None      # no chained node error


def test_other_gas_estimate_failures_also_classify():
    """Any estimation failure becomes a rejection, never a raw traceback."""
    class _Eth:
        def get_block(self, _):
            return {"baseFeePerGas": 10**9}

        @property
        def max_priority_fee(self):
            return 10**8

        def get_transaction_count(self, _sender, _block):
            return 0

        def estimate_gas(self, _tx):
            raise ValueError("execution reverted: something else entirely")

    class _W3:
        eth = _Eth()

    with pytest.raises(bridge_service.PreflightRejected) as excinfo:
        bridge_service.prepare_transaction(
            l1_w3=_W3(), sender="0x00000000000000000000000000000000000000aB",
            amount_wei=10**15,
        )
    assert "could not estimate gas" in str(excinfo.value)
    assert "ValueError" in str(excinfo.value)
