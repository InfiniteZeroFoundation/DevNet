# Wallet Unit Tests (`tests/test_connect_wallet.py`)

This document describes the unit test suite for the named-wallet system in
`dincli/cli/system.py`: the `dincli system register-wallet` command (stores
key material under a name — this was called `connect-wallet` before the
2026-07 register/connect split), the new `connect-wallet <name>` command
(switches the persistent active wallet; `set-wallet` is its deprecated
alias), the `read-wallet` / `list-accounts` / `todo` routing, and
the wallet helpers in `dincli/cli/utils.py` (`validate_account_name`,
`wallet_path_for_name`, `resolve_wallet_path`, `atomic_write_wallet`,
`load_account`, `list_accounts`, `_extract_keystore`, and the in-memory
password cache `_get_password` / `_cache_password_in_memory` /
`_clear_memory_cache`).

Unlike the integration harness (`tests/dincli/`, see
[dincli-testing-guide.md](dincli-testing-guide.md)), these are pure unit
tests: no chain, no RPC, no IPFS. Real `eth_account` keystore
encryption/decryption **is** exercised (via `Account.encrypt` /
`Account.decrypt` on dummy keys), but every filesystem/config/prompt boundary
is isolated via a temp directory and `monkeypatch`.

---

## Running

```bash
cd /home/azureuser/projects/devnet
pytest tests/test_connect_wallet.py -v

# single test
pytest tests/test_connect_wallet.py -k test_keystore_import_valid
```

No services or environment variables are required. (Note: `Account.encrypt`
runs a real scrypt KDF, so this suite is noticeably slower than a
mock-everything suite.)

Tests that assert substrings against `CliRunner` output first strip ANSI
color codes with the module-level `_plain()` helper, so they are immune to
Rich enabling color in the invoking terminal (Rich styles quoted strings and
option names, splitting plain substrings with escape codes). Reuse `_plain()`
for any new output assertion.

---

## What the suite verifies

### Wallet-name and path helpers (`TestUtilsFunctions`, `TestFixBRegression`)

Named wallets live at `WALLETS_DIR/wallet_<name>.json`; the pre-multi-wallet
layout was a single `CONFIG_DIR/wallet.json` ("legacy"), which is still
honored as a read fallback for the name `default`.

| Test | Behavior pinned down |
|------|----------------------|
| `test_validate_account_name_valid` / `_invalid` | Names of 1–64 chars from `[A-Za-z0-9_-]` pass; empty, spaces, `/`, `..`, over-length, and absolute paths raise `ValueError` |
| `test_wallet_path_for_name` | Name `test` maps to file `wallet_test.json` |
| `test_resolve_wallet_path_named_wins` | If both `wallet_default.json` and legacy `wallet.json` exist, the named file wins |
| `test_resolve_wallet_path_legacy_fallback` | With no named file, `default` resolves to the legacy `wallet.json` |
| `test_resolve_wallet_path_not_found` | Unknown names return `(path, exists=False)` pointing at the would-be named file |
| `test_wallet_path_for_name_rejects_escape` | Review fix B: `../evil` raises `ValueError` (no path traversal out of `WALLETS_DIR`) |
| `test_load_account_rejects_escape` | `load_account(name="../evil")` refuses before touching the filesystem |
| `test_cli_wallet_flag_invalid_name_exits` | Global `--wallet ../evil` exits 1 at the CLI level |
| `test_cli_set_wallet_rejects_invalid_name` | `system set-wallet ../evil` exits 1 |

### Keystore extraction (`TestUtilsFunctions`)

`_extract_keystore` accepts both the dincli wrapper schema
(`{"version": 1, "address", "keystore": {...}, "source", "name"}`) and a bare
standard Ethereum keystore (top-level `crypto` block), returning the inner
standard keystore in both cases.

| Test | Behavior pinned down |
|------|----------------------|
| `test_extract_keystore_wrapper` | Wrapper schema → inner keystore with `crypto` |
| `test_extract_keystore_bare` | Bare keystore passes through |
| `test_extract_keystore_invalid` | Unrecognizable dict raises `ValueError` |

### In-memory password cache (`TestUtilsFunctions`)

`_get_password` resolution order is: `DIN_WALLET_PASSWORD` env key →
in-memory `_PASSWORD_CACHE` (per wallet name, TTL default 900 s) →
interactive `getpass`.

| Test | Behavior pinned down |
|------|----------------------|
| `test_in_memory_password_cache` | After `_cache_password_in_memory`, a second `_get_password` returns the cached value without prompting |
| `test_in_memory_password_cache_expires` | With `utils.time.time` faked past the TTL, the cache entry is discarded and the user is re-prompted |
| `test_clear_memory_cache` | `_clear_memory_cache(name)` removes exactly that entry and reports whether one existed |
| `test_cleanup_stale_session_removes_file` / `_no_file` | `_cleanup_stale_session` deletes a leftover `CONFIG_DIR/.session` file (legacy plaintext session store) and is a no-op when absent |

### `list_accounts` (`TestUtilsFunctions`)

| Test | Behavior pinned down |
|------|----------------------|
| `test_list_accounts_named` | Named wallets are enumerated with `name`/`address`/`source`, and `active` is flagged from `active_name` |
| `test_list_accounts_legacy_only` | With only a legacy `wallet.json`, a single synthetic entry `default (legacy)` is returned and is active for `active_name="default"` |
| `test_list_accounts_named_default_no_legacy_duplicate` | When `wallet_default.json` exists, the legacy file is **not** also listed (no `default (legacy)` duplicate) |

### Atomic writes and permissions (`TestAtomicWrite`)

| Test | Behavior pinned down |
|------|----------------------|
| `test_atomic_write_creates_file` | `atomic_write_wallet` round-trips JSON |
| `test_atomic_write_permissions_0600` | New wallet files are mode `0600` |
| `test_atomic_write_overwrites_loose_permissions` | Rewriting a pre-existing `0644` file tightens it to `0600` |
| `test_ensure_wallets_dir_permissions` | `WALLETS_DIR` is created with mode `0700` |

### `register-wallet` command (`TestRegisterWalletKeystore`, `...MutualExclusivity`, `...NamedAccounts`, `TestCLICommands`)

The command body is called directly (`system_mod.register_wallet(ctx=..., ...)`)
with a `DummyCtxObj` standing in for `DinContext`, so option plumbing is
bypassed and the business logic is hit head-on.

| Test | Behavior pinned down |
|------|----------------------|
| `test_keystore_import_valid` | `--keystore` + correct passphrase saves `wallet_<name>.json` in wrapper schema with `source: "imported"` and an inner `crypto` block |
| `test_keystore_import_wrong_password` | Wrong passphrase exits without writing any wallet file |
| `test_keystore_import_missing_file` / `_malformed_json` | Missing or unparseable keystore fails fast with `typer.Exit` |
| `test_two_methods_exits` | Supplying two auth methods (e.g. private key **and** `--keystore`) is rejected |
| `test_save_named_wrapper_schema` | Private-key connect with `--name prod` writes the wrapper schema with `source: "created"` |
| `test_name_validation_rejects_bad` | Bad `--name` values are rejected before any secret is requested |
| `test_help_exposes_new_commands` | `register-wallet --help` documents `--keystore`, `--name`, and `--connect` |
| `test_list_accounts_command_empty` | `system list-accounts` succeeds (or prints "No wallets found") with no wallets on disk |

### `connect-wallet` switching (`TestFixERegression`, `TestCLICommands`)

`connect-wallet <name>` is a pure pointer flip: it persists `wallet_name` in
`config.json` via the shared `_connect_registered_wallet` helper and never
reads, writes, or decrypts key material. Active-wallet resolution priority:
global `--wallet` flag → `DIN_WALLET_NAME` env var → config `wallet_name` →
`'default'`.

| Test | Behavior pinned down |
|------|----------------------|
| `test_connect_wallet_persists_config` | `system connect-wallet validator` persists `wallet_name` and prints the address read from the wallet file (no decrypt) |
| `test_connect_wallet_unregistered_name_exits` | Unknown name exits 1 and points at `register-wallet` |
| `test_connect_wallet_rejects_wallet_flag_trap` | `connect-wallet --wallet X` (the hoisted per-invocation override, not the positional argument) exits 1 with a "Did you mean" hint |
| `test_connect_wallet_help_documents_priority` | `connect-wallet --help` documents the resolution priority (mentions `DIN_WALLET_NAME`) |
| `test_set_wallet_persists_config` | `set-wallet` (deprecated alias) still persists `wallet_name` and prints the deprecation notice |

### Loading accounts (`TestLoadAccount`, `TestReadWallet`, `TestTodoWalletAwareness`)

| Test | Behavior pinned down |
|------|----------------------|
| `test_load_account_named_wallet` | `load_account(name="prod")` decrypts `wallet_prod.json` and derives the right address |
| `test_load_account_legacy_fallback` | A bare legacy `wallet.json` keystore still loads for `default` |
| `test_load_account_demo_mode` | A `{"demo_mode": true, "private_key": ...}` wallet loads its plaintext key without any password prompt |
| `test_read_wallet_named_wallet` | `system read-wallet` runs against a named encrypted wallet (smoke test — no output assertions) |
| `test_todo_shows_named_wallet` | `system todo` runs with a named wallet + config present (smoke test) |

### Command routing / skip list (`TestSkipListRouting`)

The `system` Typer callback skips its wallet/network setup for a hard-coded
list of subcommands (`dincli/cli/system.py`, `system()` callback); these tests
prove the listed commands reach their own bodies instead of dying in the
callback when no wallet is configured.

| Test | Behavior pinned down |
|------|----------------------|
| `test_read_wallet_no_wallet_reaches_command_body` | `read-wallet` prints its own "No wallet found" |
| `test_show_index_no_wallet_reaches_command_body` | `show-index` reaches its body and exits 1 on its own terms |
| `test_set_wallet_no_wallet_reaches_command_body` | `set-wallet` reaches its body and exits 1 with "not found" for a nonexistent wallet |

### Review-fix regression tests

Each class pins a specific fix from the multi-wallet code review:

| Class / test | Regression pinned down |
|------|----------------------|
| `TestFixARegression.test_demo_mode_creates_wallets_dir` | Fix A: demo-mode connect creates `WALLETS_DIR` if missing instead of crashing |
| `TestFixBRegression` (see path-helper table above) | Fix B: wallet-name path traversal is rejected at every entry point |
| `TestFixCRegression.test_import_single_level_keystore` | Fix C: importing a bare keystore stores exactly one wrapper level (`data["keystore"]["crypto"]`, no nested `keystore.keystore`) |
| `TestFixCRegression.test_reimport_wrapped_keystore_not_double_wrapped` | Re-importing an already-wrapped dincli wallet file does not double-wrap; the result stays loadable via `load_account` |
| `TestFixERegression.test_set_wallet_persists_config` | Fix E: `system set-wallet <name>` (now a deprecated alias of `connect-wallet`) persists `wallet_name` into `config.json` |
| `TestRegisterWalletOverwriteGuard` | Review fix No. 2: overwriting an existing named wallet requires `typer.confirm` unless `--yes`; declining leaves the file byte-identical; validation failures (e.g. missing keystore) abort *before* the prompt; a direct call omitting `yes` (Typer `OptionInfo` default) is normalized so the guard still fires |
| `TestNewWalletPasswordNotCached.test_create_ignores_cached_password` | Review fix No. 3: creating/overwriting a wallet never encrypts with a stale in-memory cached password — the new keystore decrypts only with the freshly-entered one (`is_new_wallet=True` path) |
| `TestSingleEnvParseOnUnlock.test_load_account_fetches_env_password_once` | Review fix No. 5: one `load_account` unlock fetches `DIN_WALLET_PASSWORD` (and hence parses `.env`) exactly once |

---

## Isolation patterns

Conventions to reuse when adding tests to this suite:

- **`temp_config` fixture** — repoints `CONFIG_DIR`, `CACHE_DIR`,
  `WALLETS_DIR`, `WALLET_FILE`, `LEGACY_WALLET_FILE` at a `tmp_path` and
  restores them in a `finally` block. Crucially it rebinds the constants on
  **both** `dincli.cli.utils` and `dincli.cli.system`, because `system.py`
  imports them by value (`from dincli.cli.utils import CACHE_DIR,
  CONFIG_DIR, ...`, plus its own module-level `WALLET_FILE`) — patching
  only `utils` would leave `system.py` writing to the real
  `~/.config/dincli`. Direct assignment (not `monkeypatch.setattr`) is used
  so the same fixture can also derive `CONFIG_FILE`/`WORKER_CACHE_DIR`
  conditionally.

- **Direct command invocation** — most command tests call
  `system_mod.register_wallet(ctx=make_ctx(), ...)` with explicit kwargs
  rather than going through `CliRunner`. `DummyCtxObj` fakes the
  `DinContext` surface the command touches (`console`,
  `resolved_wallet_name`, `account`, `get_en_w3_account_console`).
  `CliRunner().invoke(main_app, [...])` is reserved for tests where the
  Typer layer itself is under test (help text, global `--wallet` flag,
  callback skip list, `connect-wallet`/`set-wallet`).

- **No interactive prompts** — `getpass` is patched *on the consuming
  module* (`system_mod.getpass` for the command's passphrase prompts,
  `utils_mod.getpass` for `_get_password`), and `typer.confirm` is patched
  for the overwrite guard. Which module holds the prompt matters — patching
  the wrong one hangs the test.

- **Deterministic password source** — `utils_mod.get_env_key` is stubbed to
  return `None` so an ambient `DIN_WALLET_PASSWORD` in `.env` can't leak in;
  `_PASSWORD_CACHE.clear()` at test start prevents cross-test bleed
  (the cache is module-level state). Time-based expiry is tested by faking
  `utils_mod.time.time`, never by sleeping.

- **Real crypto, dummy keys** — keystores are produced with the real
  `Account.encrypt` on the well-known dummy keys `DUMMY_KEY_0/1`, so decrypt
  round-trips (and wrong-password failures) are genuine. The
  `_write_encrypted_wallet` helper writes a wrapper-schema wallet file
  directly for tests that need a pre-existing wallet.

---

## Coverage gaps

Behavior of the wallet layer this suite does not yet exercise:

- **`register-wallet` input paths** — only the private-key argument,
  `--keystore`, and demo-mode `--account` paths are tested. Untested:
  `--key-file` (including missing file), `--account` without demo mode
  (`ETH_PRIVATE_KEY_<n>` env lookup), and the fully interactive path
  (hidden private-key prompt).
- **Private-key format validation** — the `0x` + 64-hex-chars check
  (`register_wallet`) has no test for malformed keys.
- **Create-password flow** — the `Create wallet password:` / confirm-mismatch
  branch (mismatch → exit) is never driven; tests always satisfy
  `_get_password` via patched `getpass`.
- **`DIN_WALLET_PASSWORD` positive path** — `get_env_key` is always stubbed
  to `None`; the env var actually supplying the password (both on unlock and
  as the `register-wallet` automation path) is unasserted.
- **`load_account` wrong-password retry** — the branch that clears a failed
  cached password, re-prompts once, and finally raises
  `ValueError("Invalid password or corrupted keystore.")` is untested.
- **`DIN_PASSWORD_TTL` override** — cache expiry is only tested with the
  default TTL constant (mirrored locally as `_PASSWORD_TTL_DEFAULT` at the
  bottom of the test file, not imported from `utils`).
- **`get_active_account_name` resolution** — precedence of ctx
  `wallet_name` → `DIN_WALLET_NAME` env → configured `wallet_name` is
  untested.
- **Smoke tests without assertions** — `test_read_wallet_named_wallet` and
  `test_todo_shows_named_wallet` only prove the commands don't raise; their
  output (address shown, wallet name surfaced in `todo`) is unchecked.
- **Legacy migration on write** — the overwrite guard deliberately does not
  guard the legacy `wallet.json` → named-wallet migration for `default`;
  that unguarded migration path itself has no test.
