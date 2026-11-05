"""Minimal web3/DinContext stand-ins for unit-testing dincli commands.

A FakeContract answers `contract.functions.<name>(*args).call()` from a
`views` dict (a value, or a callable taking the call's args), and the
bound function itself doubles as the "tx" handed to build_and_send_tx, so
tests can assert which calls were sent, with which args, in which order.
"""
from types import SimpleNamespace

from dincli.cli.context import DinContext


class FakeFn:
    def __init__(self, contract, name, args):
        self.contract = contract
        self.name = name
        self.args = args

    def call(self, *_, **__):
        value = self.contract.views[self.name]
        return value(*self.args) if callable(value) else value

    def __eq__(self, other):
        return (self.name, self.args) == other

    def __repr__(self):
        return f"{self.name}{self.args}"


class _Functions:
    def __init__(self, contract):
        self._contract = contract

    def __getattr__(self, name):
        return lambda *args: FakeFn(self._contract, name, args)


class FakeContract:
    def __init__(self, address, **views):
        self.address = address
        self.views = views
        self.functions = _Functions(self)


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(" ".join(str(a) for a in args))

    def text(self):
        return "\n".join(self.messages)


class FakeCtxObj:
    """Duck-types the DinContext methods the commands use. The GI
    validators are the real DinContext ones, bound to this object."""

    validate_gi_ET_curr_GI = DinContext.validate_gi_ET_curr_GI
    validate_gi_LTE_curr_GI = DinContext.validate_gi_LTE_curr_GI

    def __init__(self, *, account="0x000000000000000000000000000000000000A11c", block_number=100,
                 coordinator=None, auditor=None, token=None, stake=None, registry=None,
                 emission=None, din_coordinator=None, model_base_dir=None):
        self.console = DummyConsole()
        self.account = SimpleNamespace(address=account)
        self.w3 = SimpleNamespace(eth=SimpleNamespace(block_number=block_number))
        self.coordinator = coordinator
        self.auditor = auditor
        self.token = token
        self.stake = stake
        self.registry = registry
        self.emission = emission
        self.din_coordinator = din_coordinator
        self.model_base_dir = model_base_dir

    def get_en_w3_account_console(self, model_id=None):
        return "local", self.w3, self.account, self.console

    def get_deployed_din_task_coordinator_contract(self, *args, **kwargs):
        return self.coordinator

    def get_deployed_din_task_auditor_contract(self, *args, **kwargs):
        return self.auditor

    def get_deployed_din_token_contract(self, *args, **kwargs):
        return self.token

    def get_deployed_din_stake_contract(self, *args, **kwargs):
        return self.stake

    def get_deployed_din_registry_contract(self, *args, **kwargs):
        return self.registry

    def get_deployed_din_emission_contract(self, *args, **kwargs):
        return self.emission

    def get_current_gi_and_state(self, task_coordinator_contract, *args, **kwargs):
        return (
            task_coordinator_contract.functions.GI().call(),
            task_coordinator_contract.functions.GIstate().call(),
        )

    def get_model_base_dir(self, model_id):
        return self.model_base_dir


def record_txs(monkeypatch, *modules):
    """Patch build_and_send_tx (and time.sleep) in each module; returns the
    ordered list of sent FakeFn calls."""
    sent = []

    def fake_build_and_send_tx(ctx, fn, *args, **kwargs):
        sent.append(fn)
        return SimpleNamespace(status=1)

    for module in modules:
        monkeypatch.setattr(module, "build_and_send_tx", fake_build_and_send_tx)
        if hasattr(module, "time"):
            monkeypatch.setattr(module.time, "sleep", lambda s: None)
    return sent
