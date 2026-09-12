"""Golden CLI output tests for `dincli system din-info` and `read-stake`
(task_110926_15 §3.5).

These pin down the complete stdout of nine command paths — `din-info`'s five
selector flags plus its no-flag default, and `read-stake` under its three
call sites (`dintoken`, `aggregator dintoken`, `auditor dintoken`) — as it
was captured against the pre-refactor implementation, byte for byte. They
must keep passing UNMODIFIED once `din_info()` and `read_dintoken_stake()`
are routed through `dincli.sdk.operations.platform`.

Everything that would otherwise depend on the running machine's real
config/keystore/RPC is mocked at the SDK boundary: the interactive signer
(`InteractiveKeystoreSigner._resolve`), `get_w3`, the user config file (so a
developer's real `~/.config/dincli/config.json` — e.g. a configured
`wallet_name` — can't change the captured output), and (for `read-stake`)
`get_contract_instance`. Everything above that boundary — the root
callback's "Active Network:" line, `get_en_w3_account_console()`'s wallet/w3
lines, the stake contract address line, the command's own output — runs for
real.
"""
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from dincli.cli import context as context_module
from dincli.cli import signer as signer_module
from dincli.main import app as main_app
from dincli.sdk import config as sdk_config
from dincli.sdk import web3 as sdk_web3
from dincli.sdk.operations import platform as platform_ops

ACCOUNT_ADDRESS = "0x" + "11" * 20
RPC_ENDPOINT = "https://rpc.example.com/v1/SECRET"
STAKE_WEI = 15 * 10**18


class _FakeAccount:
    address = ACCOUNT_ADDRESS


class _FakeProvider:
    endpoint_uri = RPC_ENDPOINT


class _FakeEth:
    chain_id = 1337

    def get_balance(self, address):
        return 0


class _FakeW3:
    provider = _FakeProvider()
    eth = _FakeEth()


class _FakeGetStakeCall:
    def __init__(self, value):
        self._value = value

    def call(self):
        return self._value


class _FakeStakeFunctions:
    def getStake(self, address):
        return _FakeGetStakeCall(STAKE_WEI)


class _FakeStakeContract:
    functions = _FakeStakeFunctions()


def _fake_get_contract_instance(artifact_path, network, address=None, w3=None):
    return _FakeStakeContract()


@pytest.fixture(autouse=True)
def _mock_signer_config_and_rpc(monkeypatch):
    """Isolate every command path from the real keystore/RPC/config.json."""
    monkeypatch.setattr(
        signer_module.InteractiveKeystoreSigner, "_resolve",
        lambda self: _FakeAccount(),
    )
    monkeypatch.setattr(sdk_web3, "get_w3", lambda network: _FakeW3())
    # A real ~/.config/dincli/config.json (e.g. a configured wallet_name)
    # must never change what this test captures.
    monkeypatch.setattr(sdk_config, "CONFIG_FILE", Path("/nonexistent/dincli-config.json"))
    # Pre-refactor, `read-stake` builds its contract via
    # DinContext.get_deployed_din_stake_contract() (dincli.cli.context); post-
    # refactor, get_stake() builds it directly via sdk.operations.platform.
    # Both are patched so this file works unmodified across the refactor.
    monkeypatch.setattr(context_module, "get_contract_instance", _fake_get_contract_instance)
    monkeypatch.setattr(platform_ops, "get_contract_instance", _fake_get_contract_instance)


def _invoke(args):
    return CliRunner().invoke(main_app, args)


# ---------------------------------------------------------------------------
# din-info — five selector flags + the no-flag default
# ---------------------------------------------------------------------------

_DIN_INFO_HEADER = (
    "Active Network: local\n"
    "✓ Active Wallet: default (0x1111111111111111111111111111111111111111)\n"
    "✓ Active Web3: https://rpc.example.com/v1/****\n"
)


def test_din_info_default_prints_all_five_addresses():
    result = _invoke(["system", "din-info"])
    assert result.exit_code == 0
    assert result.output == (
        _DIN_INFO_HEADER
        + "Coordinator: 0xa513E6E4b8f2a923D98304ec87F64353C4D5C853\n"
        + "DIN Token: 0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9\n"
        + "Staking Contract: 0xA51c1fc2f0D1a1b8494Ed1FE312d7C3a78Ed91C0\n"
        + "Representative: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266\n"
        + "Registry: 0x959922bE3CAee4b8Cd9a407cc3ac1C251C2007B1\n"
    )


def test_din_info_coordinator_flag():
    result = _invoke(["system", "din-info", "--coordinator"])
    assert result.exit_code == 0
    assert result.output == (
        _DIN_INFO_HEADER + "Coordinator: 0xa513E6E4b8f2a923D98304ec87F64353C4D5C853\n"
    )


def test_din_info_token_flag():
    result = _invoke(["system", "din-info", "--token"])
    assert result.exit_code == 0
    assert result.output == (
        _DIN_INFO_HEADER + "DIN Token: 0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9\n"
    )


def test_din_info_stake_flag():
    result = _invoke(["system", "din-info", "--stake"])
    assert result.exit_code == 0
    assert result.output == (
        _DIN_INFO_HEADER + "Staking Contract: 0xA51c1fc2f0D1a1b8494Ed1FE312d7C3a78Ed91C0\n"
    )


def test_din_info_representative_flag():
    result = _invoke(["system", "din-info", "--representative"])
    assert result.exit_code == 0
    assert result.output == (
        _DIN_INFO_HEADER + "Representative: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266\n"
    )


def test_din_info_registry_flag():
    result = _invoke(["system", "din-info", "--registry"])
    assert result.exit_code == 0
    assert result.output == (
        _DIN_INFO_HEADER + "Registry: 0x959922bE3CAee4b8Cd9a407cc3ac1C251C2007B1\n"
    )


# ---------------------------------------------------------------------------
# read-stake — three call sites sharing read_dintoken_stake(ctx, name=...)
# ---------------------------------------------------------------------------

_READ_STAKE_HEADER = (
    _DIN_INFO_HEADER
    + "✓ DIN Stake contract address:  0xA51c1fc2f0D1a1b8494Ed1FE312d7C3a78Ed91C0\n"
)


def test_dintoken_read_stake_labels_account():
    result = _invoke(["dintoken", "read-stake"])
    assert result.exit_code == 0
    assert result.output == _READ_STAKE_HEADER + " Account's DIN token stake:  15 DinTokens\n"


def test_aggregator_dintoken_read_stake_labels_aggregator():
    result = _invoke(["aggregator", "dintoken", "read-stake"])
    assert result.exit_code == 0
    assert result.output == _READ_STAKE_HEADER + " Aggregator's DIN token stake:  15 DinTokens\n"


def test_auditor_dintoken_read_stake_labels_auditor():
    result = _invoke(["auditor", "dintoken", "read-stake"])
    assert result.exit_code == 0
    assert result.output == _READ_STAKE_HEADER + " Auditor's DIN token stake:  15 DinTokens\n"


# ---------------------------------------------------------------------------
# Independent review, task_110926_14/15, finding 3: CLI output on the error
# path (and with a lowercase-configured address) differed from pre-refactor.
# Both probes below were also run, unmodified in substance, against the
# pre-refactor commit 66d9860 in a throwaway worktree to confirm the
# properties they assert (address-as-configured; address-before-failure)
# already held there.
# ---------------------------------------------------------------------------


def test_dintoken_read_stake_prints_address_as_configured_lowercase(monkeypatch):
    """A lowercase-configured stake address must render lowercase, not
    checksummed — get_stake() checksums it for its own on-chain use, but the
    CLI's address line must match config byte for byte, exactly as
    get_deployed_din_stake_contract() printed it pre-refactor."""
    import dincli.sdk.manifest as manifest_module

    real = manifest_module.load_din_info()
    lowered_local = dict(real["local"])
    lowered_local["stake"] = real["local"]["stake"].lower()
    lowered = dict(real)
    lowered["local"] = lowered_local
    # Both patched — matching this file's own convention for
    # get_contract_instance above — so this probe exercises the same
    # property whether the CLI resolves the address via
    # dincli.cli.context (pre-refactor) or dincli.sdk.operations.platform
    # (post-refactor); `from X import Y` binds a local name in each module,
    # so patching only one leaves the other module reading the real file.
    monkeypatch.setattr(context_module, "load_din_info", lambda: lowered)
    monkeypatch.setattr(platform_ops, "load_din_info", lambda: lowered)

    result = _invoke(["dintoken", "read-stake"])
    assert result.exit_code == 0
    lower_addr = real["local"]["stake"].lower()
    assert result.output == (
        _DIN_INFO_HEADER
        + f"✓ DIN Stake contract address:  {lower_addr}\n"
        + " Account's DIN token stake:  15 DinTokens\n"
    )


def test_dintoken_read_stake_prints_address_before_getstake_fails(monkeypatch):
    """When getStake() fails, the address line must already be on stdout —
    pre-refactor, get_deployed_din_stake_contract() printed it as a side
    effect strictly before the contract call could fail; the refactor must
    preserve that ordering even though it now fails through
    sdk.operations.platform.get_stake() instead of a direct contract call.

    Full-behavior version of task_110926_14/15 review finding 5: the earlier
    version of this test only asserted an output prefix, exit code, and the
    absence of "DinTokens" — which passed even though a real difference
    existed (an extra "✗ getStake call failed..." line, and SystemExit
    instead of the original RuntimeError reaching CliRunner). The CLI's
    compatibility adapter (`dincli.cli.utils.reraise_din_error_cause`, wired
    into `read_dintoken_stake()`) re-raises `ContractError.__cause__` — the
    original `RuntimeError` — for exactly this case, so complete output,
    exit code, AND exception type are now identical to pre-refactor
    `66d9860` (verified against it directly; see
    `Plans/task-14-15-review-evidence/cli-before.json` and this file's
    module docstring)."""

    class _FailingGetStakeCall:
        def call(self):
            raise RuntimeError("boom")

    class _FailingStakeFunctions:
        def getStake(self, address):
            return _FailingGetStakeCall()

    class _FailingStakeContract:
        functions = _FailingStakeFunctions()

    monkeypatch.setattr(
        context_module, "get_contract_instance",
        lambda *a, **kw: _FailingStakeContract(),
    )
    monkeypatch.setattr(
        platform_ops, "get_contract_instance",
        lambda *a, **kw: _FailingStakeContract(),
    )

    result = _invoke(["dintoken", "read-stake"])
    # Complete parity with pre-refactor 66d9860: nothing printed past the
    # address line (no "✗ ..." message), exit code 1, and the original
    # RuntimeError itself — not a SystemExit wrapping a DinError — is what
    # CliRunner observes.
    assert result.output == _READ_STAKE_HEADER
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert not isinstance(result.exception, SystemExit)
    assert str(result.exception) == "boom"


# ---------------------------------------------------------------------------
# The one declared behavior change (§3.5): a network missing from
# din_info.json used to raise a bare KeyError and dump a traceback. It now
# raises ConfigError, and the wrapper prints a clean message and exits 1.
# `sepolia_devnet` is a real gap: ALLOWED_NETWORKS accepts it, but it has no
# entry in the shipped din_info.json.
# ---------------------------------------------------------------------------


def test_din_info_missing_network_fails_clean_not_with_a_traceback():
    """Full-behavior version of task_110926_14/15 review finding 5. Unlike
    the getStake case above, there is no real pre-refactor exception object
    to restore here: this used to be a bare KeyError/TypeError from
    unchecked `din_info[network]` dict indexing, never an `Exception`
    instance the old code constructed — so
    `dincli.cli.utils.reraise_din_error_cause()` cannot and does not
    re-raise anything for it (`ConfigError` has no `__cause__` on this
    path; see that function's docstring). This asserts the CURRENT stable
    behavior completely instead of only "not a KeyError" + a substring, so
    a future change to this message/exit path is caught here rather than
    silently passing this loosened check."""
    result = _invoke(["--network", "sepolia_devnet", "system", "din-info"])
    assert result.output == (
        "Active Network: sepolia_devnet\n"
        "✓ Active Wallet: default (0x1111111111111111111111111111111111111111)\n"
        "✓ Active Web3: https://rpc.example.com/v1/****\n"
        "Network 'sepolia_devnet' is not configured in din_info.json.\n"
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert not isinstance(result.exception, KeyError)
