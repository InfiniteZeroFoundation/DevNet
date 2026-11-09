# Code Standards

Code style and quality expectations for contributions to DevNet. This is the
detail behind the one-line summary in [CONTRIBUTING.md](CONTRIBUTING.md#code-standards);
see that file first for the general contribution flow.

## Python (`dincli/`, `tests/`, service files)

- Plain **PEP 8**. Ruff **0.16.4** uses the explicit Python 3.12 policy in
  `pyproject.toml`: `E4`, `E7`, `E9`, `F`, and `I`. CI prints every finding
  and uploads `ruff-report`; findings are **advisory**. Installation,
  configuration, execution, unreadable inputs, and invalid reports fail CI.
- Run `python -m pip install ruff==0.16.4`, then `python -m ruff check .`
  from the repository root. Exit 1 means findings; fix these in separately
  scoped cleanup changes. No formatter, automatic fixes, count budget, or
  no-new-findings gate is introduced by this policy.
- CI installs Ruff through `.github/constraints-ci.txt`; keep that pin and
  `required-version` in `pyproject.toml` aligned when upgrading. The snapshot
  recorder keeps its historical version pin for baseline reproduction.
- Configure editor integrations to use the installed Ruff 0.16.4 executable.
  A bundled version that differs will fail the exact-version check.
- Discovery covers maintained Python (`*.py`, `*.pyi`), tests, examples
  (`cache_model_0`, `cache_model_1`, `cid_services`), and maintained scripts
  in `.github`, `.claude`, and `scripts`, plus Ruff configuration validation.
  Generated, vendored, build and runtime trees are excluded with
  `extend-exclude`, preserving Ruff defaults. Markdown/notebook linting is
  outside this policy. Normal Git ignore discovery still applies.
- The [migration baseline](issues/320-python-lint/README.md) preserves both
  the agreed policy and broader old-default debt; narrower discovery/rules
  do not represent source cleanup. Review existing suppressions before
  changing them, and keep any new suppression narrow and justified.
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
