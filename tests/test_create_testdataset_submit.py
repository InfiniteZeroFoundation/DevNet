import secrets
from types import SimpleNamespace

import pytest
import typer
from nacl.public import PrivateKey
from typer.testing import CliRunner
from web3 import Web3

from dincli.cli.context import DinContext
from dincli.cli.modelownerd import auditor_batches as atb
from dincli.cli.utils import GIstatestrToIndex
from dincli.main import app as main_app

# Resolved dynamically (not hardcoded) so these tests stay correct whether or
# not the richer GI-states lifecycle (task_061026_21) is merged on whatever
# develop snapshot this runs against -- the ordinal for this state name shifts
# depending on that.
_AUDITOR_BATCHES_CREATED_ORDINAL = GIstatestrToIndex("AuditorsBatchesCreated")

runner = CliRunner()


_TA_FLAG_ALREADY_SET_SELECTOR = Web3.keccak(text="TA_FlagAlreadySet()").hex()[:8]

_AUDITOR_PRIVKEY = PrivateKey.generate()
_AUDITOR_PUBKEY_BYTES = bytes(_AUDITOR_PRIVKEY.public_key)
_AUDITOR_ADDRESS = "0xAuditorOne"


def _fake_get_bytes32_from_cid(cid_str: str) -> str:
    import hashlib

    return hashlib.sha256(cid_str.encode()).hexdigest()


class FakeRevert(Exception):
    def __init__(self, data):
        super().__init__("execution reverted")
        self.data = data


def flag_already_set_revert():
    return FakeRevert(data="0x" + _TA_FLAG_ALREADY_SET_SELECTOR)


def other_revert():
    return FakeRevert(data="0xdeadbeef")


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(" ".join(str(a) for a in args))


class DummyCall:
    def __init__(self, value):
        self.value = value

    def call(self, *args, **kwargs):
        return self.value


class DummyTaskAuditorFunctions:
    def __init__(self, contract):
        self.contract = contract

    def AuditorsBatchCount(self, gi):
        return DummyCall(self.contract.batch_count)

    def getAuditorsBatch(self, gi, batch_id):
        return DummyCall((batch_id, [_AUDITOR_ADDRESS], [], b""))

    def assignAuditTestDataset(self, gi, batch_id, encrypted_cid, encrypted_keys, commitment):
        return ("assignAuditTestDataset", batch_id)


class DummyTaskAuditorContract:
    def __init__(self, batch_count):
        self.batch_count = batch_count
        self.functions = DummyTaskAuditorFunctions(self)


class _SetFlagCall:
    def __init__(self, contract):
        self.contract = contract

    def call(self, tx_params=None):
        if self.contract.flag_call_raises is not None:
            raise self.contract.flag_call_raises
        return None


class DummyTaskCoordinatorFunctions:
    def __init__(self, contract):
        self.contract = contract

    def setTestDataAssignedFlag(self, gi, value):
        return _SetFlagCall(self.contract)


class DummyTaskCoordinatorContract:
    def __init__(self, gi=0, gi_state=_AUDITOR_BATCHES_CREATED_ORDINAL, flag_call_raises=None):
        self.gi = gi
        self.gi_state = gi_state
        self.flag_call_raises = flag_call_raises
        self.functions = DummyTaskCoordinatorFunctions(self)


class DummyStakeFunctions:
    def getEncryptionKey(self, address):
        return DummyCall(_AUDITOR_PUBKEY_BYTES)


class DummyStakeContract:
    def __init__(self):
        self.functions = DummyStakeFunctions()


class DummyAccount:
    address = "0xOwner"

    def sign_message(self, message):
        return SimpleNamespace(signature=secrets.token_bytes(65))


class DummyContextObj:
    def __init__(self, tmp_path, task_coordinator_contract, task_auditor_contract):
        self.console = DummyConsole()
        self.account = DummyAccount()
        self.w3 = object()
        self.tmp_path = tmp_path
        self.task_coordinator_contract = task_coordinator_contract
        self.task_auditor_contract = task_auditor_contract
        self.stake_contract = DummyStakeContract()

    def get_en_w3_account_console(self, *args, **kwargs):
        return "local", self.w3, self.account, self.console

    def get_deployed_din_task_coordinator_contract(self, *args, **kwargs):
        return self.task_coordinator_contract

    def get_deployed_din_task_auditor_contract(self, *args, **kwargs):
        return self.task_auditor_contract

    def get_current_gi_and_state(self, contract, *args, **kwargs):
        return contract.gi, contract.gi_state

    def validate_gi_ET_curr_GI(self, gi, curr_gi):
        return curr_gi

    def validate_GIstate_ET_given_GIstate(self, *args, **kwargs):
        return None

    def get_model_base_dir(self, model_id):
        return self.tmp_path

    def ensure_file_exists(self, *args, **kwargs):
        return None

    def load_custom_fn(self, *args, **kwargs):
        def fake_fn(batch_count, gi, model_base_path, test_data_path):
            return [
                {
                    "raw_cid": f"cid-{i}",
                    "K": secrets.token_bytes(32),
                    "plaintext_keccak": b"\x00" * 32,
                }
                for i in range(batch_count)
            ]

        return fake_fn

    def get_deployed_din_stake_contract(self, *args, **kwargs):
        return self.stake_contract


def make_ctx(tmp_path, batch_count=3, flag_call_raises=None):
    task_coordinator_contract = DummyTaskCoordinatorContract(flag_call_raises=flag_call_raises)
    task_auditor_contract = DummyTaskAuditorContract(batch_count)
    ctx_obj = DummyContextObj(tmp_path, task_coordinator_contract, task_auditor_contract)
    return SimpleNamespace(obj=ctx_obj), task_coordinator_contract, task_auditor_contract


@pytest.fixture(autouse=True)
def patch_module(monkeypatch, tmp_path):
    monkeypatch.setattr(atb, "get_bytes32_from_cid", _fake_get_bytes32_from_cid)
    monkeypatch.setattr(atb, "get_manifest_key", lambda *a, **kw: {
        "type": "custom", "path": "create_audit_testDataCIDs.py", "ipfs": "cid-service",
    })
    monkeypatch.setattr(atb, "CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "dincli.cli.utils.get_manifest_path", lambda *a, **kw: tmp_path / "no_manifest.json"
    )
    monkeypatch.setattr(atb.time, "sleep", lambda seconds: None)


def _invoke(tmp_path, ctx, model_id=1, gi=None, submit=True, test_data_path=None, batch=None):
    test_data_file = tmp_path / "test_dataset.pt"
    test_data_file.write_bytes(b"dummy")
    atb.create_testdataset(
        ctx,
        model_id=model_id,
        gi=gi,
        submit=submit,
        test_data_path=test_data_path or str(test_data_file),
        batch=batch or [],
    )


def test_all_batches_succeed_sends_flag(monkeypatch, tmp_path):
    ctx, coordinator, auditor = make_ctx(tmp_path, batch_count=3)

    sent = []

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        sent.append(contract_function)
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    _invoke(tmp_path, ctx)

    assign_calls = [c for c in sent if isinstance(c, tuple) and c[0] == "assignAuditTestDataset"]
    assert sorted(c[1] for c in assign_calls) == [0, 1, 2]
    # last sent call is the flag tx (a _SetFlagCall instance, not our assign tuple)
    assert any(not isinstance(c, tuple) for c in sent)


def test_one_batch_fails_skips_flag_and_exits(monkeypatch, tmp_path):
    ctx, coordinator, auditor = make_ctx(tmp_path, batch_count=3)

    sent = []

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        sent.append(contract_function)
        if isinstance(contract_function, tuple) and contract_function[1] == 1:
            return None
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    with pytest.raises(typer.Exit):
        _invoke(tmp_path, ctx)

    assign_calls = [c for c in sent if isinstance(c, tuple) and c[0] == "assignAuditTestDataset"]
    assert sorted(c[1] for c in assign_calls) == [0, 1, 2]
    # flag must never be sent (would be a non-tuple contract_function)
    assert all(isinstance(c, tuple) for c in sent)
    assert any("1" in msg for msg in ctx.obj.console.messages)


def test_batch_retry_only_sends_listed_batches_then_flag(monkeypatch, tmp_path):
    ctx, coordinator, auditor = make_ctx(tmp_path, batch_count=3)

    sent = []

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        sent.append(contract_function)
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    _invoke(tmp_path, ctx, batch=[1])

    assign_calls = [c for c in sent if isinstance(c, tuple) and c[0] == "assignAuditTestDataset"]
    assert [c[1] for c in assign_calls] == [1]
    assert any(not isinstance(c, tuple) for c in sent)


def test_flag_already_set_is_informational_not_error(monkeypatch, tmp_path):
    ctx, coordinator, auditor = make_ctx(tmp_path, batch_count=2, flag_call_raises=flag_already_set_revert())

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    _invoke(tmp_path, ctx)

    assert any("already set" in msg.lower() for msg in ctx.obj.console.messages)


def test_flag_other_revert_exits_nonzero(monkeypatch, tmp_path):
    ctx, coordinator, auditor = make_ctx(tmp_path, batch_count=2, flag_call_raises=other_revert())

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    with pytest.raises(typer.Exit):
        _invoke(tmp_path, ctx)


# ---------------------------------------------------------------------------
# CLI-level coverage (issue #252 approval amendment 5): exercise the
# registered `dincli model-owner auditor-batches create-testdataset` command
# through CliRunner/typer's real argument parsing, not by calling the Python
# function directly. This is what catches a wrong command path in printed
# output (e.g. the retry hint) that a direct-call test can't see.
# ---------------------------------------------------------------------------

def _patch_context_methods(monkeypatch, tmp_path, coordinator, auditor, stake=None):
    stake_contract = stake or DummyStakeContract()
    account = DummyAccount()

    monkeypatch.setattr(
        DinContext, "get_en_w3_account_console",
        lambda self, *a, **kw: ("local", object(), account, self.console),
    )
    monkeypatch.setattr(
        DinContext, "get_deployed_din_task_coordinator_contract",
        lambda self, *a, **kw: coordinator,
    )
    monkeypatch.setattr(
        DinContext, "get_deployed_din_task_auditor_contract",
        lambda self, *a, **kw: auditor,
    )
    monkeypatch.setattr(
        DinContext, "get_current_gi_and_state",
        lambda self, contract, *a, **kw: (contract.gi, contract.gi_state),
    )
    monkeypatch.setattr(DinContext, "validate_gi_ET_curr_GI", lambda self, gi, curr_gi: curr_gi)
    monkeypatch.setattr(DinContext, "validate_GIstate_ET_given_GIstate", lambda self, *a, **kw: None)
    monkeypatch.setattr(DinContext, "get_model_base_dir", lambda self, model_id: tmp_path)
    monkeypatch.setattr(DinContext, "ensure_file_exists", lambda self, *a, **kw: None)
    monkeypatch.setattr(DinContext, "get_deployed_din_stake_contract", lambda self, *a, **kw: stake_contract)

    def fake_fn(batch_count, gi, model_base_path, test_data_path):
        return [
            {
                "raw_cid": f"cid-{i}",
                "K": secrets.token_bytes(32),
                "plaintext_keccak": b"\x00" * 32,
            }
            for i in range(batch_count)
        ]

    monkeypatch.setattr(DinContext, "load_custom_fn", lambda self, *a, **kw: fake_fn)


def _make_test_data_file(tmp_path):
    test_data_file = tmp_path / "test_dataset.pt"
    test_data_file.write_bytes(b"dummy")
    return test_data_file


def _cli_args(model_id, test_data_file, batch=None, submit=True):
    args = ["model-owner", "auditor-batches", "create-testdataset", str(model_id)]
    if submit:
        args.append("--submit")
    args += ["--test-data-path", str(test_data_file)]
    for b in batch or []:
        args += ["--batch", str(b)]
    return args


def test_cli_all_batches_succeed_sends_flag(monkeypatch, tmp_path):
    coordinator = DummyTaskCoordinatorContract()
    auditor = DummyTaskAuditorContract(batch_count=3)
    _patch_context_methods(monkeypatch, tmp_path, coordinator, auditor)

    sent = []

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        sent.append(contract_function)
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    result = runner.invoke(main_app, _cli_args(1, _make_test_data_file(tmp_path)))

    assert result.exit_code == 0, result.output
    assign_calls = [c for c in sent if isinstance(c, tuple) and c[0] == "assignAuditTestDataset"]
    assert sorted(c[1] for c in assign_calls) == [0, 1, 2]
    assert any(not isinstance(c, tuple) for c in sent)


def test_cli_one_batch_fails_exits_1_and_prints_correct_retry_command(monkeypatch, tmp_path):
    coordinator = DummyTaskCoordinatorContract()
    auditor = DummyTaskAuditorContract(batch_count=3)
    _patch_context_methods(monkeypatch, tmp_path, coordinator, auditor)

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        if isinstance(contract_function, tuple) and contract_function[1] == 1:
            return None
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    result = runner.invoke(main_app, _cli_args(1, _make_test_data_file(tmp_path)))

    assert result.exit_code == 1, result.output
    assert "dincli model-owner auditor-batches create-testdataset 1 --submit --batch 1" in result.output
    assert "model-owner task auditor-batches" not in result.output


def test_cli_batch_retry_only_sends_listed_batches_then_flag(monkeypatch, tmp_path):
    coordinator = DummyTaskCoordinatorContract()
    auditor = DummyTaskAuditorContract(batch_count=3)
    _patch_context_methods(monkeypatch, tmp_path, coordinator, auditor)

    sent = []

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        sent.append(contract_function)
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    result = runner.invoke(main_app, _cli_args(1, _make_test_data_file(tmp_path), batch=[1]))

    assert result.exit_code == 0, result.output
    assign_calls = [c for c in sent if isinstance(c, tuple) and c[0] == "assignAuditTestDataset"]
    assert [c[1] for c in assign_calls] == [1]
    assert any(not isinstance(c, tuple) for c in sent)


def test_cli_batch_retry_with_two_distinct_batches_then_flag(monkeypatch, tmp_path):
    coordinator = DummyTaskCoordinatorContract()
    auditor = DummyTaskAuditorContract(batch_count=3)
    _patch_context_methods(monkeypatch, tmp_path, coordinator, auditor)

    sent = []

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        sent.append(contract_function)
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    result = runner.invoke(main_app, _cli_args(1, _make_test_data_file(tmp_path), batch=[0, 2]))

    assert result.exit_code == 0, result.output
    assign_calls = [c for c in sent if isinstance(c, tuple) and c[0] == "assignAuditTestDataset"]
    assert [c[1] for c in assign_calls] == [0, 2]
    assert any(not isinstance(c, tuple) for c in sent)


def test_cli_rerun_after_state_advanced_to_audit_test_data_assigned(monkeypatch, tmp_path):
    """Once the richer GI-states lifecycle (task_061026_21) is live,
    setTestDataAssignedFlag succeeding advances GIstate to
    AuditTestDataAssigned. A safe re-run must recognise that state directly
    and report "already done" without touching the exact-match state gate
    (which would otherwise reject it with a generic wrong-state error,
    contradicting the documented re-run safety) -- and without any batch
    creation/assignment/flag work being attempted. This drives
    create_testdataset's own dual-state check directly -- that check no
    longer calls the generic validate_GIstate_ET_given_GIstate at all for
    this command, so it can't be masked by that helper being mocked
    elsewhere. Only GIstateToStr itself is substituted, so the scenario is
    exercisable regardless of whether this develop snapshot currently has
    the richer states merged.
    """
    coordinator = DummyTaskCoordinatorContract(gi_state=999)
    auditor = DummyTaskAuditorContract(batch_count=3)
    _patch_context_methods(monkeypatch, tmp_path, coordinator, auditor)

    monkeypatch.setattr(
        atb, "GIstateToStr",
        lambda gi_state: "AuditTestDataAssigned" if gi_state == 999 else "AuditorsBatchesCreated",
    )

    def fail_if_called(*a, **kw):
        raise AssertionError("must not send any transaction once already past this state")

    monkeypatch.setattr(atb, "build_and_send_tx", fail_if_called)

    result = runner.invoke(main_app, _cli_args(1, _make_test_data_file(tmp_path)))

    assert result.exit_code == 0, result.output
    assert "already set" in result.output.lower() or "nothing further to do" in result.output.lower()


def test_cli_flag_already_set_is_informational_exit_0(monkeypatch, tmp_path):
    coordinator = DummyTaskCoordinatorContract(flag_call_raises=flag_already_set_revert())
    auditor = DummyTaskAuditorContract(batch_count=2)
    _patch_context_methods(monkeypatch, tmp_path, coordinator, auditor)

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    result = runner.invoke(main_app, _cli_args(1, _make_test_data_file(tmp_path)))

    assert result.exit_code == 0, result.output
    assert "already set" in result.output.lower()


def test_cli_flag_other_revert_exits_1(monkeypatch, tmp_path):
    coordinator = DummyTaskCoordinatorContract(flag_call_raises=other_revert())
    auditor = DummyTaskAuditorContract(batch_count=2)
    _patch_context_methods(monkeypatch, tmp_path, coordinator, auditor)

    def fake_build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg, *a, **kw):
        return SimpleNamespace(transactionHash=b"\xab" * 32)

    monkeypatch.setattr(atb, "build_and_send_tx", fake_build_and_send_tx)

    result = runner.invoke(main_app, _cli_args(1, _make_test_data_file(tmp_path)))

    assert result.exit_code == 1, result.output
