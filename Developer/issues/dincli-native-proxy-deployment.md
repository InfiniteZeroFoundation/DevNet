# dincli Native Proxy Deployment (Option C of the proxy-deployment decision record)

## Summary

Implement the chosen architecture of
[proxy-deployment-architecture.md](../../Documentation/technical/upgradable-contracts/proxy-deployment-architecture.md):
`dincli dindao deploy ...` performs Transparent-Proxy deployment **natively in
web3.py** — no `npx hardhat run` / `forge script` at runtime.

## Interim state (2026-07-15)

The dincli integration harness (Phase 1, `tests/dincli/test_01_platform.py` on
the PR 13 lineage) currently uses the **interim script flow**, which is the
record's *rejected* Option A kept only as test scaffolding:

1. `npx hardhat run scripts/deploy-platform.ts --network localhost` (OZ upgrades plugin)
2. `dincli system import-deployments` maps `hardhat/deployments/<net>.json` → `din_info.json`

This works and keeps the harness green, but has the known drawbacks (Node as a
runtime dependency, hardhat env keys instead of the dincli wallet, coupling to
the deployments file) and dies when `hardhat/` is deleted (Foundry-only
decision, 2026-07-03).

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
- new `dindao deploy din-token` command; existing deploy commands become
  proxy-aware; write resulting addresses (incl. `proxy_admin`) to `din_info.json`
- scope: **V1 bootstrap only** — upgrades stay behind the toolchain scripts

## Acceptance

- Harness Phase 1 replaces the script+import scaffolding with per-contract
  `dincli dindao deploy ...` tests (restore the original test structure)
- `system import-deployments` remains as a secondary sync utility (adopting
  script/upgrade-driven deployments), no longer the canonical bootstrap path
- No Node/toolchain invocation anywhere in the dincli deploy path
