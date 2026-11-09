# Code Standards

Code style and quality expectations for contributions to DevNet. This is the
detail behind the one-line summary in [CONTRIBUTING.md](CONTRIBUTING.md#code-standards);
see that file first for the general contribution flow.

## Python (`dincli/`, `tests/`, service files)

- Plain **PEP 8**. There is no `[tool.ruff]` config committed in
  `pyproject.toml` — `.ruff_cache` is a local artifact, not enforced CI
  config — so use judgment and keep style consistent with the surrounding
  file rather than relying on a linter to catch it.
- Python **>= 3.12** (see [DEVELOPMENT_SETUP.md](DEVELOPMENT_SETUP.md)).
- Tests mock chain/IPFS state via `monkeypatch` and `typer.testing.CliRunner`
  rather than hitting a live network — follow the existing patterns in
  `tests/test_dintoken.py` and `tests/test_ipfs_config.py` for new tests.
- New CLI behavior should have a test that invokes the actual registered
  Typer command (via `CliRunner`), not just the underlying function —
  otherwise a wiring bug (wrong command path, wrong option name) can pass
  review undetected.

## Solidity (`foundry/src/`)

- `solc 0.8.28`, `via_ir = true` (see `foundry/foundry.toml`). Build and test
  with `forge build` / `forge test` before opening a PR.
- NatSpec (`///`, `@notice`, `@dev`, `@param`, `@return`) throughout —
  existing contracts are heavily annotated; match that density for new
  public/external functions.
- Prefer **custom errors** over `require(condition, "string")`. Revert
  strings are the larger contributor to contract size, and several
  contracts (`DINTaskCoordinator`, `DINTaskAuditor`) are close enough to
  the EIP-170 runtime-size limit that this isn't a style preference — see
  the **Contract size budget** section in
  [CONTRIBUTING.md](CONTRIBUTING.md#submitting-prs) for the enforced
  margins and the gate script that checks them.
- Every deployable contract's bundled ABI under `dincli/abis/` must be
  regenerated in the same PR that changes its interface — see
  **Submitting PRs** in [CONTRIBUTING.md](CONTRIBUTING.md#submitting-prs)
  for the exact command.

## General

- Keep commits focused and PRs scoped to one change; unrelated cleanup
  belongs in its own PR.
- Don't add abstractions, fallbacks, or validation for cases the current
  code can't hit — see what's actually enforced by the type/contract
  boundary before adding a guard for it.
