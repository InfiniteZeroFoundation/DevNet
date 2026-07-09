# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

InfiniteZero / DIN Protocol DevNet: a federated-learning network coordinated by Solidity contracts on Optimism Sepolia, operated through `dincli`, a Python/Typer CLI. Raw training data never leaves a client's device — only model artifacts (pinned to IPFS) and on-chain coordination state are shared.

The Solidity tree at `hardhat/contracts/` (Hardhat workflow) is used for deployment/verification tooling. 

## Commands

### Python / dincli

```bash
pip install -e .              # editable install (repo root, requires Python >=3.9)
dincli --help                 # CLI entrypoint (dincli.main:app)
pytest                        # run all tests
pytest tests/test_dintoken.py -k test_name   # run a single test
```

There is no `[tool.pytest]`/`[tool.ruff]` config committed in `pyproject.toml` — `.pytest_cache`/`.ruff_cache` are local artifacts, not enforced CI config. Code standard is plain PEP 8 (per `Developer/CONTRIBUTING.md`).

Tests mock chain/IPFS state via `monkeypatch` and `typer.testing.CliRunner` rather than hitting a live network (see `tests/test_dintoken.py`, `tests/test_ipfs_config.py`).

### Solidity

```bash
cd foundry && forge build && forge test
cd hardhat && npx hardhat compile && npx hardhat test
```

Foundry config: `solc 0.8.28`, `via_ir = true`. Hardhat config: `solc 0.8.28`, `evmVersion: cancun`, local hardhat network forced to `hardfork: cancun` (required for TSTORE/TLOAD support used by the contracts). `hardhat/hardhat.config.ts` loads `../.env` then `../.env.<NETWORK>` (defaults to `local`).

### Local devnet

```bash
./foundry/anvil.sh                                   # local anvil chain
dincli system configure-network --network local      # or sepolia_op_devnet / mainnet
dincli system connect-wallet --account <account_id>
```

## Architecture

### Two layers: protocol contracts vs. per-model task contracts

- **Platform-level contracts** (deployed once by the DIN-Representative): `DinCoordinator` (ETH<->DIN exchange, slasher registry admin), `DinToken` (ERC20, minted on ETH deposit), `DinValidatorStake` (validator staking/slashing), `DinModelRegistry` (model registration, open-source vs proprietary fee). See `Documentation/DIN-workflow.md`.
- **Task-level contracts** (deployed per model by the model owner): `DINTaskCoordinator` and `DINTaskAuditor`. These must be authorized as "slashers" on `DinValidatorStake` (via `DinCoordinator`, only callable by the DIN-Representative) *before* the model owner can register the model in `DinModelRegistry`. See `Documentation/Model-workflow.md` for the full step-by-step (deploy → slasher auth request → genesis model → register → global iterations).

A model's lifecycle runs in **Global Iterations (GI)**: aggregator/auditor registration → Local Model Submission (LMS) by clients → auditor evaluation/scoring → two-tier aggregation (T1 sub-batches, T2 combines T1 into the new global model) → slashing of misbehaving validators → GI end. Each phase is opened/closed explicitly by the model owner via `dincli model-owner ...` subcommands, and other roles act only within an open phase.

### CLI structure (`dincli/`)

- `main.py` registers one Typer sub-app per role/concern: `system`, `dindao` (DIN-Representative actions), `model-owner`, `aggregator`, `auditor`, `client`, `dintoken`, `task`, `ipfs`. Role-specific submodules for the model-owner workflow live under `cli/modelownerd/` (deploy, gi, lms, lms_evaluation, aggregation, auditor_batches, slash, model, task, setup).
- `cli/context.py` (`DinContext`) is the shared runtime object injected into commands: lazily resolves network/web3/account, fetches deployed platform contracts, resolves *task* contract artifacts (custom ABIs can be supplied via the manifest's `task_contracts` block, falling back to bundled ABIs in `dincli/abis/`), and tracks per-directory IPFS CID caches (`local.json.cid`) so files are only re-fetched when their CID changes.
- `cli/utils.py` holds config/cache paths (via `platformdirs`: `CONFIG_DIR`/`CACHE_DIR` under `dincli`), account loading/keystore handling, manifest load/cache/key lookup, GI state enum helpers, and tx building.
- `services/runtime.py` builds a `ServiceRuntimeContext` (network, manifest, manifest_path, model_id/role) that is auto-injected into model-owner-supplied service functions when they declare a `runtime` parameter.

### Manifest-driven, pluggable model services

Each model owner supplies their own Python service files (not part of this repo) implementing model-specific logic: `model.py` (architecture), `modelowner.py` (genesis model, scoring, audit test data), `client.py` (local training/DP), `auditor.py` (scoring), `aggregator.py` (T1/T2 aggregation). These are uploaded to IPFS and referenced by CID in a per-model `manifest.json` at `<root_dir>/tasks/<network>/task_<coordinator_address>/manifest.json`. `dincli` dynamically loads and calls these functions at runtime (`DinContext.load_custom_fn`), fetching them from IPFS on demand and caching by CID. `cache_model_0/` and `cid_services/` in this repo are example/reference service implementations (MNIST-style), not framework code.

Differential privacy is opt-in per model via a nested `dp` block in the manifest; when enabled, `client.py`'s training function applies the configured DP mechanism.

### IPFS abstraction

`dincli/services/ipfs.py` supports three interchangeable upload/retrieve backends (env-var-configured IPFS node, Filebase, or a fully custom Python provider) selected via `resolve_ipfs_config()`/`ipfs_provider` config — see `Documentation/guides/ipfs.md`. All CID-bearing artifacts (services, manifests, model weights, ABIs) flow through this layer rather than direct HTTP calls scattered through the CLI.

### Networks

Network selection (`local` / `sepolia_op_devnet` / `mainnet`) is resolved per-command (`--network` flag, falling back to configured default) and drives which `.env.<network>` file, RPC endpoint, and deployed contract addresses (`load_din_info()`) are used. The live DevNet runs on Optimism Sepolia (`sepolia_op_devnet`, chainId 11155420).
