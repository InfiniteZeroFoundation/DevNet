import secrets
from types import SimpleNamespace

import pytest
import typer
from nacl.public import PrivateKey
from web3 import Web3

from dincli.cli.modelownerd import auditor_batches as atb


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
    def __init__(self, gi=0, gi_state=0, flag_call_raises=None):
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
