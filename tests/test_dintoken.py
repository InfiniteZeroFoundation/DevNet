from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner
from rich.console import Console
from dincli.cli import dintoken
from dincli.main import app as main_app


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(args)


class DummyEth:
    def get_balance(self, address):
        return 3 * 10**18


class DummyWeb3:
    eth = DummyEth()

    def to_wei(self, amount, unit):
        assert unit == "ether"
        return int(amount * 10**18)


class DummyCall:
    def __init__(self, value):
        self.value = value

    def call(self):
        return self.value


class DummyTokenFunctions:
    def __init__(self, token):
        self.token = token

    def balanceOf(self, address):
        self.token.balance_of_calls.append(address)
        return DummyCall(self.token.balance)

    def approve(self, address, amount):
        self.token.approvals.append((address, amount))
        return ("approve", address, amount)


class DummyStakeFunctions:
    def __init__(self, stake):
        self._stake = stake

    def stake(self, amount):
        self._stake.stakes.append(amount)
        return ("stake", amount)

    def getStake(self, address):
        self._stake.get_stake_calls.append(address)
        return DummyCall(self._stake.current_stake)


class DummyCoordinatorFunctions:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def depositAndMint(self):
        self.coordinator.deposit_calls += 1
        return "depositAndMint"


class DummyToken:
    def __init__(self, balance):
        self.balance = balance
        self.approvals = []
        self.balance_of_calls = []
        self.functions = DummyTokenFunctions(self)


class DummyStake:
    address = "0xStake"

    def __init__(self, current_stake=0):
        self.current_stake = current_stake
        self.stakes = []
        self.get_stake_calls = []
        self.functions = DummyStakeFunctions(self)


class DummyCoordinator:
    def __init__(self):
        self.deposit_calls = 0
        self.functions = DummyCoordinatorFunctions(self)


class DummyContextObj:
    def __init__(self, token_balance=100 * 10**18, current_stake=12 * 10**18):
        self.console = Console()
        self.w3 = DummyWeb3()
        self.account = SimpleNamespace(address="0xAccount")
        self.token = DummyToken(token_balance)
        self.stake = DummyStake(current_stake)
        self.coordinator = DummyCoordinator()

    def get_en_w3_account_console(self):
        self.console.print(f"[bold green]✓ Active Wallet:[/bold green] {self.account.address}")
        return "local", self.w3, self.account, self.console

    def get_deployed_din_token_contract(self):
        return self.token

    def get_deployed_din_stake_contract(self):
        return self.stake

    def get_deployed_din_coordinator_contract(self):
        return self.coordinator


def make_ctx(**kwargs):
    return SimpleNamespace(obj=DummyContextObj(**kwargs))


def test_buy_sends_eth_value(monkeypatch):
    ctx = make_ctx()
    sent_transactions = []

    def fake_build_and_send_tx(*args, **kwargs):
        sent_transactions.append((args, kwargs))
        return SimpleNamespace(transactionHash=bytes.fromhex("12" * 32))

    monkeypatch.setattr(dintoken, "build_and_send_tx", fake_build_and_send_tx)

    dintoken.buy_dintokens(ctx, 1.5)

    assert ctx.obj.coordinator.deposit_calls == 1
    assert sent_transactions[0][0][1] == "depositAndMint"
    assert sent_transactions[0][1]["tx_params"] == {"value": 1500000000000000000}


def test_stake_uses_requested_amount(monkeypatch):
    ctx = make_ctx()
    sent_transactions = []

    def fake_build_and_send_tx(*args, **kwargs):
        sent_transactions.append((args, kwargs))
        return SimpleNamespace(transactionHash=bytes.fromhex("34" * 32))

    monkeypatch.setattr(dintoken, "build_and_send_tx", fake_build_and_send_tx)
    monkeypatch.setattr(dintoken.time, "sleep", lambda seconds: None)

    dintoken.stake_dintokens(ctx, 12)

    stake_amount = 12 * 10**18
    assert ctx.obj.token.approvals == [("0xStake", stake_amount)]
    assert ctx.obj.stake.stakes == [stake_amount]
    assert sent_transactions[0][0][1] == ("approve", "0xStake", stake_amount)
    assert sent_transactions[1][0][1] == ("stake", stake_amount)


def test_stake_exits_when_balance_is_insufficient(monkeypatch):
    ctx = make_ctx(token_balance=11 * 10**18)
    monkeypatch.setattr(dintoken.time, "sleep", lambda seconds: None)

    with pytest.raises(typer.Exit):
        dintoken.stake_dintokens(ctx, 12)

    assert ctx.obj.token.approvals == []
    assert ctx.obj.stake.stakes == []


def test_stake_exits_when_amount_is_below_minimum(monkeypatch):
    ctx = make_ctx(token_balance=100 * 10**18)
    monkeypatch.setattr(dintoken.time, "sleep", lambda seconds: None)

    with pytest.raises(typer.Exit):
        dintoken.stake_dintokens(ctx, 9)

    assert ctx.obj.token.approvals == []
    assert ctx.obj.stake.stakes == []


def test_read_stake_reads_active_account_stake():
    ctx = make_ctx(current_stake=15 * 10**18)

    dintoken.read_dintoken_stake(ctx)

    assert ctx.obj.stake.get_stake_calls == ["0xAccount"]


def test_top_level_dintoken_help_exposes_commands():
    result = CliRunner().invoke(main_app, ["dintoken", "--help"])

    assert result.exit_code == 0
    assert "buy" in result.output
    assert "stake" in result.output
    assert "read-stake" in result.output



# ── read_after_write tests ──────────────────────────────────────────────────


class TestReadAfterWrite:

    def test_settled_first_read_above_baseline(self, monkeypatch):
        """First read above baseline returns settled=True and stops early."""
        from dincli.cli.utils import read_after_write
        sleeps = []
        monkeypatch.setattr("dincli.cli.utils.time.sleep", lambda s: sleeps.append(s))
        calls = []

        def read_fn():
            calls.append(1)
            return 200

        result = read_after_write(read_fn, baseline=100)
        assert result.value == 200
        assert result.settled is True
        assert result.observed is True
        assert len(calls) == 1
        assert len(sleeps) == 0  # no sleep on first try when settled

    def test_lagging_at_baseline_exhausts_attempts(self, monkeypatch):
        """Reads equal to baseline exhaust attempts; settled=False."""
        from dincli.cli.utils import read_after_write
        sleeps = []
        monkeypatch.setattr("dincli.cli.utils.time.sleep", lambda s: sleeps.append(s))
        calls = []

        def read_fn():
            calls.append(1)
            return 100

        result = read_after_write(read_fn, baseline=100, attempts=3, delay=0.1)
        assert result.value == 100
        assert result.settled is False
        assert result.observed is True
        assert len(calls) == 3
        assert len(sleeps) == 2  # slept after attempt 1 and 2

    def test_below_baseline_stays_unsettled(self, monkeypatch):
        """Values below baseline must never count as settled (> not !=)."""
        from dincli.cli.utils import read_after_write
        sleeps = []
        monkeypatch.setattr("dincli.cli.utils.time.sleep", lambda s: sleeps.append(s))
        values = iter([90, 80, 100])

        def read_fn():
            return next(values)

        result = read_after_write(read_fn, baseline=100, attempts=3, delay=0.1)
        assert result.settled is False
        assert result.observed is True
        # Last observed value was 100 — not above baseline, just equal
        assert result.value == 100

    def test_all_raising_returns_observed_false(self, monkeypatch):
        """Every attempt raising returns observed=False, value==baseline."""
        from dincli.cli.utils import read_after_write
        sleeps = []
        monkeypatch.setattr("dincli.cli.utils.time.sleep", lambda s: sleeps.append(s))
        calls = []

        def read_fn():
            calls.append(1)
            raise ConnectionError("RPC down")

        result = read_after_write(read_fn, baseline=100, attempts=4, delay=0.1)
        assert result.value == 100
        assert result.settled is False
        assert result.observed is False
        assert len(calls) == 4
        assert len(sleeps) == 3

    def test_mixed_raise_then_above_settles(self, monkeypatch):
        """Raise, then a value above baseline → settled=True."""
        from dincli.cli.utils import read_after_write
        sleeps = []
        monkeypatch.setattr("dincli.cli.utils.time.sleep", lambda s: sleeps.append(s))
        values = iter([None, None, 200])

        def read_fn():
            v = next(values)
            if v is None:
                raise TimeoutError("timeout")
            return v

        result = read_after_write(read_fn, baseline=100, attempts=5, delay=0.1)
        assert result.value == 200
        assert result.settled is True
        assert result.observed is True

    def test_attempts_below_one_raises(self):
        """attempts < 1 raises ValueError."""
        from dincli.cli.utils import read_after_write
        with pytest.raises(ValueError):
            read_after_write(lambda: 0, baseline=0, attempts=0)

    def test_no_sleep_after_final_attempt(self, monkeypatch):
        """No sleep after the final attempt."""
        from dincli.cli.utils import read_after_write
        sleeps = []
        monkeypatch.setattr("dincli.cli.utils.time.sleep", lambda s: sleeps.append(s))
        calls = []

        def read_fn():
            calls.append(1)
            return 100

        read_after_write(read_fn, baseline=100, attempts=5, delay=2.0)
        assert len(sleeps) == 4
        assert len(calls) == 5


# ── buy_dintokens tests ─────────────────────────────────────────────────────


class TestBuyDintokens:

    def test_settled_prints_balance_no_warning(self, monkeypatch):
        """Settled read prints the new balance with no lag warning."""
        ctx = make_ctx(token_balance=100 * 10**18)

        def fake_build_and_send_tx(*args, **kwargs):
            return SimpleNamespace(transactionHash=bytes.fromhex("12" * 32))

        def fake_read_after_write(read_fn, *, baseline, **kwargs):
            from dincli.cli.utils import ReadResult
            return ReadResult(value=baseline + 10 * 10**18, settled=True, observed=True)

        monkeypatch.setattr(dintoken, "build_and_send_tx", fake_build_and_send_tx)
        monkeypatch.setattr(dintoken, "read_after_write", fake_read_after_write)

        import io
        from rich.console import Console as RichConsole
        out = io.StringIO()
        ctx.obj.console = RichConsole(file=out, force_terminal=False)

        dintoken.buy_dintokens(ctx, 1.5)

        output = out.getvalue()
        assert "DINToken balance" in output
        assert "lagging" not in output.lower()

    def test_lagging_prints_balance_and_warning(self, monkeypatch):
        """Observed but not settled prints balance plus lag warning."""
        ctx = make_ctx(token_balance=100 * 10**18)

        def fake_build_and_send_tx(*args, **kwargs):
            return SimpleNamespace(transactionHash=bytes.fromhex("12" * 32))

        def fake_read_after_write(read_fn, *, baseline, **kwargs):
            from dincli.cli.utils import ReadResult
            return ReadResult(value=baseline, settled=False, observed=True)

        monkeypatch.setattr(dintoken, "build_and_send_tx", fake_build_and_send_tx)
        monkeypatch.setattr(dintoken, "read_after_write", fake_read_after_write)

        import io
        from rich.console import Console as RichConsole
        out = io.StringIO()
        ctx.obj.console = RichConsole(file=out, force_terminal=False)

        dintoken.buy_dintokens(ctx, 1.5)
        output = out.getvalue()
        assert "RPC may be lagging" in output

    def test_read_failed_shows_pre_purchase(self, monkeypatch):
        """When every read fails, names the pre-purchase balance as pre-purchase."""
        ctx = make_ctx(token_balance=100 * 10**18)

        def fake_build_and_send_tx(*args, **kwargs):
            return SimpleNamespace(transactionHash=bytes.fromhex("12" * 32))

        def fake_read_after_write(read_fn, *, baseline, **kwargs):
            from dincli.cli.utils import ReadResult
            return ReadResult(value=baseline, settled=False, observed=False)

        monkeypatch.setattr(dintoken, "build_and_send_tx", fake_build_and_send_tx)
        monkeypatch.setattr(dintoken, "read_after_write", fake_read_after_write)

        import io
        from rich.console import Console as RichConsole
        out = io.StringIO()
        ctx.obj.console = RichConsole(file=out, force_terminal=False)

        dintoken.buy_dintokens(ctx, 1.5)
        output = out.getvalue()
        assert "Pre-purchase balance" in output

    def test_tx_receipt_none_returns_early(self, monkeypatch):
        """None receipt: pre-purchase balance printed, no post-purchase output."""
        ctx = make_ctx(token_balance=100 * 10**18)
        called_read_after_write = []

        def fake_build_and_send_tx(*args, **kwargs):
            return None

        monkeypatch.setattr(dintoken, "build_and_send_tx", fake_build_and_send_tx)
        monkeypatch.setattr(dintoken, "read_after_write", lambda **kw: called_read_after_write.append(True))

        import io
        from rich.console import Console as RichConsole
        out = io.StringIO()
        ctx.obj.console = RichConsole(file=out, force_terminal=False)

        dintoken.buy_dintokens(ctx, 1.5)
        output = out.getvalue()
        # Pre-purchase balance is printed
        assert "DINToken balance" in output
        # No purchase success message
        assert "DINTokens bought" not in output
        # No post-purchase output
        assert "lagging" not in output.lower()
        assert "Pre-purchase balance" not in output
        # No NoneType crash text
        assert "NoneType" not in output
        assert "transactionHash" not in output
        # read_after_write never called
        assert called_read_after_write == []

    def test_baseline_reuse_single_pre_purchase_call(self, monkeypatch):
        """balanceOf called exactly once before submission (pre-purchase)."""
        ctx = make_ctx(token_balance=100 * 10**18)
        balance_of_calls = []

        orig_balanceOf = ctx.obj.token.functions.balanceOf

        def tracking_balanceOf(address):
            balance_of_calls.append(address)
            return orig_balanceOf(address)

        ctx.obj.token.functions = DummyTokenFunctions(ctx.obj.token)
        ctx.obj.token.functions.balanceOf = tracking_balanceOf

        def fake_build_and_send_tx(*args, **kwargs):
            return SimpleNamespace(transactionHash=bytes.fromhex("12" * 32))

        def fake_read_after_write(read_fn, *, baseline, **kwargs):
            from dincli.cli.utils import ReadResult
            return ReadResult(value=baseline + 10, settled=True, observed=True)

        monkeypatch.setattr(dintoken, "build_and_send_tx", fake_build_and_send_tx)
        monkeypatch.setattr(dintoken, "read_after_write", fake_read_after_write)

        dintoken.buy_dintokens(ctx, 1.5)
        # Exactly one call to balanceOf before the submission path
        assert len(balance_of_calls) == 1
        assert balance_of_calls[0] == "0xAccount"
