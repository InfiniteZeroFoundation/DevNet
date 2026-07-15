# DIN Token CLI Unit Tests (`tests/test_dintoken.py`)

This document describes the unit test suite for the DIN token commands in
`dincli/cli/dintoken.py`: `buy_dintokens` (ETH → DIN via
`DinCoordinator.depositAndMint`), `stake_dintokens` (ERC20 `approve` +
`DinValidatorStake.stake`), and `read_dintoken_stake`, plus the Typer wiring
that exposes them as `dincli dintoken buy|stake|read-stake` and as the
legacy role-scoped copies under `dincli aggregator dintoken ...` /
`dincli auditor dintoken ...`.

Unlike the integration harness (`tests/dincli/`, see
[dincli-testing-guide.md](dincli-testing-guide.md)), these are pure unit
tests: no chain, no RPC. The entire web3/contract surface is replaced by
hand-rolled dummy objects, and `build_and_send_tx` is monkeypatched so no
transaction is ever built or signed.

---

## Running

```bash
cd /home/azureuser/projects/devnet
pytest tests/test_dintoken.py -v

# single test
pytest tests/test_dintoken.py -k test_buy_sends_eth_value
```

No services or environment variables are required.

---

## What the suite verifies

### `buy` — ETH deposit and mint

| Test | Behavior pinned down |
|------|----------------------|
| `test_buy_sends_eth_value` | `buy_dintokens(ctx, 1.5)` calls `DinCoordinator.functions.depositAndMint()` exactly once and passes it to `build_and_send_tx` with `tx_params={"value": 1.5 ETH in wei}` — i.e. the ETH amount rides along as transaction value, not as a function argument |

### `stake` — approve-then-stake flow

`MIN_STAKE` is 10 DIN (`10 * 10**18` wei, defined in
`dincli/cli/utils.py`). Validation order in the command is: minimum-stake
check first, then token-balance check, then the two transactions.

| Test | Behavior pinned down |
|------|----------------------|
| `test_stake_uses_requested_amount` | `stake_dintokens(ctx, 12)` converts 12 DIN to wei once and uses the same amount for both legs: first `DinToken.approve(stake_contract.address, amount)`, then `DinValidatorStake.stake(amount)` — two `build_and_send_tx` calls in that order |
| `test_stake_exits_when_balance_is_insufficient` | With a balance of 11 DIN, staking 12 exits (`typer.Exit`) before any approve/stake call is made |
| `test_stake_exits_when_amount_is_below_minimum` | Staking 9 (< `MIN_STAKE` = 10) exits with no contract interaction, regardless of balance |

### `read-stake`

| Test | Behavior pinned down |
|------|----------------------|
| `test_read_stake_reads_active_account_stake` | `read_dintoken_stake` queries `DinValidatorStake.getStake(...)` with the active wallet's address |

### Typer wiring

| Test | Behavior pinned down |
|------|----------------------|
| `test_top_level_dintoken_help_exposes_commands` | `dincli dintoken --help` lists `buy`, `stake`, `read-stake` |
| `test_legacy_role_dintoken_help_exposes_commands[...]` | The role-scoped duplicates `aggregator dintoken --help` and `auditor dintoken --help` (separate Typer sub-apps in `aggregator.py`/`auditor.py` that wrap the same functions with a role label) expose the same three commands |

---

## Isolation patterns

Conventions to reuse when adding tests to this suite:

- **Dummy contract graph** — `DummyContextObj` fakes the `DinContext`
  surface the commands touch (`get_en_w3_account_console`,
  `get_deployed_din_token_contract` / `_stake_` / `_coordinator_`).
  Each dummy contract (`DummyToken`, `DummyStake`, `DummyCoordinator`)
  **records** invocations (`approvals`, `stakes`, `deposit_calls`,
  `balance_of_calls`, `get_stake_calls`) and **returns sentinel values**
  (e.g. `("approve", address, amount)`) from its `functions.*` methods.
  Tests then assert both sides: the contract mock saw the call, *and* the
  sentinel arrived as `build_and_send_tx`'s second positional argument —
  proving the command sent exactly the contract call it constructed.
  View calls return a `DummyCall` whose `.call()` yields a canned value
  (token balance, current stake).

- **`build_and_send_tx` capture** — patched via
  `monkeypatch.setattr(dintoken, "build_and_send_tx", ...)` (on the
  *consuming* module, since it's imported by name) with a closure appending
  `(args, kwargs)` to a list and returning a fake receipt
  (`SimpleNamespace(transactionHash=...)`). Nothing web3-shaped is needed.

- **No real sleeping** — `stake_dintokens` sleeps 5 s between approve and
  stake; every stake test patches `dintoken.time.sleep` to a no-op.

- **Constructor-injected scenario state** — `make_ctx(token_balance=...,
  current_stake=...)` parameterizes the dummy state per test instead of
  mutating shared fixtures.

- **`CliRunner` only for wiring** — command bodies are called directly with
  the fake ctx; `CliRunner().invoke(main_app, ...)` is used only for the
  `--help` wiring tests, which don't need a wallet or network.

---

## Coverage gaps

Behavior of the dintoken commands this suite does not yet exercise:

- **Failure paths swallow errors** — both `buy_dintokens` and
  `stake_dintokens` wrap their transaction calls in `try/except Exception`
  and only *print* the error (no `typer.Exit`, exit code stays 0). There is
  no test pinning this down — nor one deciding whether it's even the
  desired behavior (a failed approve leaves the command "successful").
- **`MIN_STAKE` boundary** — only 9 (below) and 12 (above) are tested;
  staking exactly 10 (== `MIN_STAKE`, should pass) is unasserted.
- **Check ordering** — minimum-stake is checked before balance; no test
  distinguishes the order (e.g. amount both below minimum *and* above
  balance).
- **Fractional amounts** — the `stake` CLI command accepts a `float`, but
  `stake_dintokens` is typed `amount: int` and `Web3.to_wei` is trusted to
  convert; fractional stakes (e.g. `10.5`) are untested.
- **`buy` output/balance display** — the before/after `balanceOf` reads are
  recorded by the dummy but never asserted; console output (balances,
  tx hash) is unchecked throughout.
- **Command bodies via the CLI layer** — `buy`/`stake`/`read-stake` are only
  invoked as plain functions; no `CliRunner` test drives them end-to-end
  through the Typer layer (argument parsing/conversion included).
- **Role-scoped behavior beyond help** — the aggregator/auditor wrappers
  pass `name="Aggregator"`/`"Auditor"` labels; nothing asserts the label
  actually appears in output. (The client role has no dintoken sub-app, so
  aggregator/auditor is the complete set.)
