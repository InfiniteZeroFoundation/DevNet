import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from web3 import Web3

from dincli.cli.modelownerd import model
from dincli.cli.utils import GIstatestrToIndex


CID_A = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"
CID_B = "bafybeiarceirceirceirceirceirceirceirceirceirceirceirceirce"


def _fake_get_bytes32_from_cid(cid_str: str) -> str:
    """Deterministic stand-in for the real CID->digest conversion (no 'cid' package dependency)."""
    return hashlib.sha256(cid_str.encode()).hexdigest()


def hash_bytes32(cid_str: str) -> bytes:
    return Web3.to_bytes(hexstr=_fake_get_bytes32_from_cid(cid_str))


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(args)

    def input(self, *args, **kwargs):
        raise AssertionError("console.input should never be reached; _confirm_or_exit is bypassed in tests")


class DummyCall:
    def __init__(self, value):
        self.value = value

    def call(self):
        return self.value


class DummyTaskCoordinatorFunctions:
    def __init__(self, contract):
        self.contract = contract

    def GI(self):
        return DummyCall(self.contract.gi)

    def GIstate(self):
        return DummyCall(self.contract.gi_state)

    def genesisModelIpfsHash(self):
        return DummyCall(self.contract.onchain_hash)

    def setGenesisModelIpfsHash(self, genesis_hash_bytes32):
        self.contract.set_genesis_calls.append(genesis_hash_bytes32)
        return ("setGenesisModelIpfsHash", genesis_hash_bytes32)

    def setTier2Score(self, gi, score):
        self.contract.set_score_calls.append((gi, score))
        return ("setTier2Score", gi, score)


class DummyTaskCoordinatorContract:
    def __init__(self, gi, gi_state, onchain_hash=b"\x00" * 32):
        self.gi = gi
        self.gi_state = gi_state
        self.onchain_hash = onchain_hash
        self.set_genesis_calls = []
        self.set_score_calls = []
        self.functions = DummyTaskCoordinatorFunctions(self)


class DummyContextObj:
    def __init__(self, contract):
        self.console = DummyConsole()
        self.account = SimpleNamespace(address="0xAccount")
        self.w3 = object()
        self.contract = contract

    def get_en_w3_account_console(self, *args, **kwargs):
        return "local", self.w3, self.account, self.console

    def get_deployed_din_task_coordinator_contract(self, verbose=True, model_id=None, taskCoordinator_address=None):
        return self.contract

    def get_current_gi_and_state(self, contract, verbose_gi=True, verbose_state=False, verbose_state_name=False):
        return contract.gi, contract.gi_state

    def get_task_dir(self, taskCoordinator_address):
        return Path("/nonexistent-task-dir")


def make_ctx(contract):
    return SimpleNamespace(obj=DummyContextObj(contract))


def _fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *args, **kwargs):
    return SimpleNamespace(transactionHash=bytes.fromhex("ab" * 32))


@pytest.fixture(autouse=True)
def bypass_confirmations_sleep_and_cid(monkeypatch):
    monkeypatch.setattr(model, "_confirm_or_exit", lambda *args, **kwargs: None)
    monkeypatch.setattr(model.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(model, "get_bytes32_from_cid", _fake_get_bytes32_from_cid)
    monkeypatch.setattr(model, "build_and_send_tx", _fake_build_and_send_tx)


def test_fresh_submission_sends_both_transactions():
    contract = DummyTaskCoordinatorContract(gi=0, gi_state=GIstatestrToIndex("AwaitingGenesisModel"))
    ctx = make_ctx(contract)

    model.submit_genesis_model(
        ctx,
        ipfs_hash=CID_A,
        task_coordinator_address="0xTaskCoordinator",
        score=90,
        help=False,
    )

    assert contract.set_genesis_calls == [hash_bytes32(CID_A)]
    assert contract.set_score_calls == [(0, 90)]


def test_rerun_in_genesis_model_created_submits_score_only():
    contract = DummyTaskCoordinatorContract(
        gi=0,
        gi_state=GIstatestrToIndex("GenesisModelCreated"),
        onchain_hash=hash_bytes32(CID_A),
    )
    ctx = make_ctx(contract)

    model.submit_genesis_model(
        ctx,
        ipfs_hash=CID_A,
        task_coordinator_address="0xTaskCoordinator",
        score=77,
        help=False,
    )

    assert contract.set_genesis_calls == []
    assert contract.set_score_calls == [(0, 77)]


def test_rerun_with_mismatched_cid_exits_without_sending_any_tx():
    contract = DummyTaskCoordinatorContract(
        gi=0,
        gi_state=GIstatestrToIndex("GenesisModelCreated"),
        onchain_hash=hash_bytes32(CID_A),
    )
    ctx = make_ctx(contract)

    with pytest.raises(typer.Exit):
        model.submit_genesis_model(
            ctx,
            ipfs_hash=CID_B,
            task_coordinator_address="0xTaskCoordinator",
            score=77,
            help=False,
        )

    assert contract.set_genesis_calls == []
    assert contract.set_score_calls == []


def test_gi_greater_than_zero_exits_without_sending_any_tx():
    contract = DummyTaskCoordinatorContract(gi=1, gi_state=GIstatestrToIndex("GIstarted"))
    ctx = make_ctx(contract)

    with pytest.raises(typer.Exit):
        model.submit_genesis_model(
            ctx,
            ipfs_hash=CID_A,
            task_coordinator_address="0xTaskCoordinator",
            score=90,
            help=False,
        )

    assert contract.set_genesis_calls == []
    assert contract.set_score_calls == []


def test_unrelated_gi_zero_state_exits_without_sending_any_tx():
    """E.g. still waiting on slasher authorization -- neither the fresh path nor the re-run path applies."""
    contract = DummyTaskCoordinatorContract(
        gi=0, gi_state=GIstatestrToIndex("AwaitingDINTaskAuditorAsSlasher")
    )
    ctx = make_ctx(contract)

    with pytest.raises(typer.Exit):
        model.submit_genesis_model(
            ctx,
            ipfs_hash=CID_A,
            task_coordinator_address="0xTaskCoordinator",
            score=90,
            help=False,
        )

    assert contract.set_genesis_calls == []
    assert contract.set_score_calls == []


def test_rerun_without_score_exits_cleanly_without_sending_any_tx(monkeypatch):
    """Score-only re-run where the manifest doesn't require test-dataset scoring and no --score is given: nothing to submit."""
    monkeypatch.setattr(model, "get_manifest", lambda *args, **kwargs: {})
    contract = DummyTaskCoordinatorContract(
        gi=0,
        gi_state=GIstatestrToIndex("GenesisModelCreated"),
        onchain_hash=hash_bytes32(CID_A),
    )
    ctx = make_ctx(contract)

    with pytest.raises(typer.Exit) as exc_info:
        model.submit_genesis_model(
            ctx,
            ipfs_hash=CID_A,
            task_coordinator_address="0xTaskCoordinator",
            score=None,
            help=False,
        )

    assert exc_info.value.exit_code == 0
    assert contract.set_genesis_calls == []
    assert contract.set_score_calls == []
