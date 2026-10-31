"""`task model-owner register-request --manifestCID` must work on the CID route
(issue #295).

The registry-contract lookup used to sit inside the `if not manifestCID:`
branch, so a caller who passed `--manifestCID` reached the fee lookup
(`openSourceFee()` / `proprietaryFee()`) with `dinregistry_contract` unbound
and died with an UnboundLocalError before any transaction was sent.
`update-manifest-request` already resolved the contract before the branch;
`register-request` now does the same.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from web3 import Web3

from dincli.cli import task as task_mod
from dincli.cli.task import register_request

ACCOUNT = "0x" + "11" * 20
TASK_COORDINATOR = "0x" + "22" * 20
TASK_AUDITOR = "0x" + "33" * 20
CID = "bafybeib3nshqhlrzqxyjfnyiarww7y7rwjprestcdtvukzgevv5g2mdlvm"
CID_BYTES32 = "0x" + "ab" * 32
FEE_WEI = 10 ** 17


class _Console:
    def __init__(self):
        self.lines = []

    def print(self, *args, **kwargs):
        self.lines.append(" ".join(str(a) for a in args))

    def input(self, *args, **kwargs):
        return "y"  # answer the on-chain submission confirm


def _ctx(contract):
    w3 = SimpleNamespace(
        eth=SimpleNamespace(get_balance=lambda _addr: 10 ** 18),
        from_wei=lambda value, unit: Web3.from_wei(value, unit),
    )
    obj = SimpleNamespace(
        get_en_w3_account_console=lambda *a, **k: (
            "sepolia_devnet", w3, SimpleNamespace(address=ACCOUNT), _Console(),
        ),
        get_deployed_din_registry_contract=MagicMock(return_value=contract),
    )
    return SimpleNamespace(obj=obj)


def test_register_request_with_manifest_cid_sends_the_request_tx():
    contract = MagicMock()
    contract.functions.proprietaryFee().call.return_value = FEE_WEI
    contract.events.ModelRegistrationRequested().process_receipt.return_value = []
    ctx = _ctx(contract)

    with patch.object(task_mod, "get_bytes32_from_cid", return_value=CID_BYTES32), \
         patch.object(task_mod, "build_and_send_tx", return_value=MagicMock()) as send:
        register_request(ctx, TASK_COORDINATOR, TASK_AUDITOR, None, CID, False)

    # The CID route must initialise the registry contract itself (issue #295).
    ctx.obj.get_deployed_din_registry_contract.assert_called_once()
    send.assert_called_once()
    assert send.call_args.kwargs["tx_params"]["value"] == FEE_WEI
