# IPFS Config Unit Tests (`tests/test_ipfs_config.py`)

This document describes the unit test suite for the IPFS provider
configuration layer: `resolve_ipfs_config()` in `dincli/cli/utils.py` and the
provider dispatch in `dincli/services/ipfs.py` (`upload_to_ipfs` /
`retrieve_from_ipfs`). Background on the three providers is in
`Documentation/public/guides/ipfs.md`.

Unlike the integration harness (`tests/dincli/`, see
[dincli-testing-guide.md](dincli-testing-guide.md)), these are pure unit
tests: no Hardhat node, no IPFS daemon, no Docker. Every external boundary is
replaced via `monkeypatch` and `tmp_path`.

---

## Running

```bash
cd /path/to/devnet
pytest tests/test_ipfs_config.py -v

# single test
pytest tests/test_ipfs_config.py -k test_config_provider_wins_over_env_var
```

No services or environment variables are required.

---

## What the suite verifies

### Provider resolution precedence

`resolve_ipfs_config()` picks the provider from, in order:

1. `ipfs_provider` in the dincli config file (`config.json` under
   `CONFIG_DIR`) — highest precedence.
2. The `IPFS_PROVIDER` environment key (resolved via `get_env_key`, which
   also reads the current directory's `.env`).
3. Fallback: `env` (a plain IPFS node addressed by
   `IPFS_API_URL_ADD` / `IPFS_API_URL_RETRIEVE`).

| Test | Behavior pinned down |
|------|----------------------|
| `test_resolve_ipfs_config_defaults_to_env_provider` | Legacy alias `"ipfs node"` normalizes to provider `env`; `IPFS_API_URL_ADD`/`IPFS_API_URL_RETRIEVE` are read from `.env` |
| `test_resolve_ipfs_config_returns_filebase_provider` | `ipfs_provider: filebase` + `ipfs_api_key_filebase` resolve as expected |
| `test_resolve_ipfs_config_uses_ipfs_provider_env_var` | With no config entry, `IPFS_PROVIDER` from `.env` selects the provider |
| `test_config_provider_wins_over_env_var` | The config file's `ipfs_provider` beats a conflicting `IPFS_PROVIDER` env value |

### API key scoping

Provider API keys are stored per-provider (`ipfs_api_key_<provider>`); the
flat `ipfs_api_key` key is a legacy Filebase-only fallback.

| Test | Behavior pinned down |
|------|----------------------|
| `test_filebase_legacy_flat_api_key_still_resolves` | Legacy flat `ipfs_api_key` still works when provider is `filebase` |
| `test_cross_provider_isolation_filebase_key_not_reused_for_other_provider` | `ipfs_api_key_filebase` is **not** leaked into `resolved.api_key` when the active provider is `custom` |
| `test_env_provider_unaffected_by_provider_key_config` | With provider `env`, neither flat nor Filebase keys populate `api_key`; URL config still resolves |

### Provider dispatch in `services/ipfs.py`

| Test | Behavior pinned down |
|------|----------------------|
| `test_upload_to_ipfs_uses_env_provider_by_default` | With an empty config, `upload_to_ipfs` posts to `<IPFS_API_URL_ADD>/add` and returns the CID from the response's `Hash` field, normalized via `get_cidv1base32_from_cid` |
| `test_custom_provider_delegates_upload_and_retrieve` | Provider `custom` dynamically loads the Python file at `ipfs_service_path` and delegates to its `upload_to_ipfs`/`retrieve_from_ipfs`; the returned CID is still CIDv1-normalized, and the custom retrieve's status code and file contents pass through untouched |

---

## Isolation patterns

These are the conventions to reuse when adding tests to this suite:

- **Config isolation** — every test repoints the module-level path constants
  at a `tmp_path`:

  ```python
  monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
  monkeypatch.setattr(utils, "CONFIG_FILE", config_file)
  ```

  The config file itself is written with the `_write_config` helper. The real
  `~/.config/dincli` is never touched.

- **`.env` isolation** — `get_env_key` falls back to `./.env`, so tests
  `monkeypatch.chdir(tmp_path)` and write a `.env` there. This is how the
  env-provider URLs and `IPFS_PROVIDER` are injected without polluting
  `os.environ`.

- **No network** — HTTP is faked by patching `ipfs.requests.post` with a
  local `DummyResponse` (status 200, canned `{"Hash": ...}` JSON). CID
  normalization is stubbed
  (`get_cidv1base32_from_cid → f"normalized-{cid}"`) so assertions can prove
  the normalization step ran without depending on real multiformat logic.

- **Custom providers as real files** — the custom-provider test writes an
  actual `custom_ipfs.py` to `tmp_path` and points `ipfs_service_path` at it,
  exercising the real dynamic-load path (`_load_custom_fn`) rather than
  mocking it.

---

## Coverage gaps

Behavior of the config layer that this suite does not yet exercise:

- **Filebase upload/retrieve dispatch** — `_upload_via_filebase` /
  `_retrieve_via_filebase` (auth header construction, Filebase RPC URLs) are
  untested; only Filebase *resolution* is covered.
- **Error paths** — missing `IPFS_API_URL_ADD`/`IPFS_API_URL_RETRIEVE` for
  the env provider, missing `ipfs_api_key` for Filebase, missing
  `ipfs_service_path` for custom, and non-2xx HTTP responses
  (`_raise_for_http_error`) all raise deliberate errors that have no tests.
- **`ipfs_api_secret`** — resolved by `resolve_ipfs_config()` but never
  asserted.
- **Other legacy aliases** — only `"ipfs node"` is tested; `"default"`,
  `"ipfs-node"`, `"node"`, and the empty string also normalize to `env`
  (see `LEGACY_IPFS_PROVIDER_ALIASES` in `dincli/cli/utils.py`).
- **`os.environ` precedence** — `get_env_key` prefers a real environment
  variable over `.env`; the tests only exercise the `.env` path.
