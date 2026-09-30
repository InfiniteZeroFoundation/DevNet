# dincli Native Proxy Deployment (Option C of the proxy-deployment decision record)

## Summary

Implement the chosen architecture of
[proxy-deployment-architecture.md](../../Documentation/technical/upgradable-contracts/proxy-deployment-architecture.md):
`dincli dinrep deploy ...` performs Transparent-Proxy deployment **natively in
web3.py** — no `npx hardhat run` / `forge script` at runtime.

## Interim state

The dincli integration harness (Phase 1, `tests/dincli/test_01_platform.py`)
uses the **interim script flow**, which is the record's *rejected* Option A
kept as scaffolding until the native deploy lands:

1. `cd foundry && forge script script/DeployPlatform.s.sol --rpc-url <rpc> --broadcast ...`
   deploys and wires the seven platform proxies
2. `dincli system import-deployments` (`--foundry` is the default) maps
   `foundry/deployments/<net>.json` → `din_info.json`

The Hardhat script is the secondary path: `npx hardhat run
scripts/deploy-platform.ts --network <net>`, then `dincli system
import-deployments --hardhat`.

This works and keeps the harness green, but has the known drawbacks: a
toolchain (forge, plus Node for the upgrade-safety validation) as a runtime
dependency, the toolchain's signing setup instead of the dincli wallet, and
coupling to the deployments file.

## Work

Per contract (DinToken, DinCoordinator, DinValidatorStake, DINModelRegistry),
in the canonical 6-step order (token → coordinator → `setCoordinator` → stake
→ `updateValidatorStakeContract` → registry):

- Tx 1: deploy the implementation (constructors are `_disableInitializers()` only, no args)
- Tx 2: deploy `TransparentUpgradeableProxy(impl, initialOwner, abi.encodeCall(initialize, args))`
  (OZ v5 proxy auto-creates its ProxyAdmin; admin readable from the ERC-1967 slot)
- wiring calls signed by the connected dincli wallet via `build_and_send_tx`

Supporting pieces (from the record §6):

- artifact-format shim: accept hardhat `bytecode: "0x…"` and foundry
  `bytecode: {object: "0x…"}` in `get_contract_instance` / deploy path
- ship/pin the OZ `TransparentUpgradeableProxy` artifact (v5.x) with dincli —
  do not recompile it ad hoc
- a `dinrep deploy` sub-app with one proxy-aware command per platform contract
  (the old constructor-based `dinrep deploy din-coordinator/din-validator-stake/din-model-registry`
  commands were removed because they could not deploy the proxied contracts); write resulting addresses (incl. `proxy_admin`) to `din_info.json`
- scope: **V1 bootstrap only** — upgrades stay behind the toolchain scripts

## Acceptance

- Harness Phase 1 replaces the script+import scaffolding with per-contract
  `dincli dinrep deploy ...` tests (restore the original test structure)
- `system import-deployments` remains as a secondary sync utility (adopting
  script/upgrade-driven deployments), no longer the canonical bootstrap path
- No Node/toolchain invocation anywhere in the dincli deploy path
