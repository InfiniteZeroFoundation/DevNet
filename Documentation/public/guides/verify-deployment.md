# Verifying a Platform Deployment

`dincli system verify-deployment` is a read-only drift check that compares
`foundry/deployments/<network>.json` against the live chain and reports
`[OK]` / `[DRIFT]` / `[ERROR]` per item.

Run it after every `DeployPlatform.s.sol` or `UpgradePlatform.s.sol` invocation,
and before each Global Iteration if you want to rule out a stale deployment file.

## Prerequisites

- `dincli` installed and a network configured (`dincli system configure-network`).
- `foundry/deployments/<network>.json` present (written by the deploy scripts).
- An RPC endpoint reachable for the active network.

No wallet or signing key is required — the command never sends transactions.

## Quick start

```bash
# Check the active network (default: local → foundry/deployments/localhost.json)
dincli system verify-deployment

# Explicit file
dincli system verify-deployment --file foundry/deployments/sepolia_op_devnet.json

# CI / no color
dincli system verify-deployment --no-color

# Also verify expected task-coordinator slashers
dincli system verify-deployment --slashers 0xTaskCoord1,0xTaskCoord2
```

## What is checked

| # | Check | DRIFT condition |
|---|-------|-----------------|
| 1 | EIP-1967 implementation slot | Slot value ≠ `dinXxxImpl` in the JSON |
| 2 | EIP-1967 admin slot | Slot value ≠ `proxyAdminXxx` in the JSON |
| 3 | Implementation extcodehash | `keccak256(eth_getCode(impl))` ≠ `dinXxxImplCodehash` in the JSON |
| 4 | ProxyAdmin `owner()` | On-chain owner ≠ `owner` in the JSON |
| 5 | `DinCoordinator` wiring | `dinToken` / `dinValidatorStakeContract` / `feeRouter` addresses mismatch |
| 5b | `DinFeeRouter.treasury()` wiring | Return value ≠ `dinTreasury` in the JSON (checked independently of `dinCoordinator`) |
| 5c | `DINModelRegistry.dinValidatorStake()` wiring | Return value ≠ `dinValidatorStake` in the JSON |
| 6 | Slasher authorizations | Expected slasher not authorized (only when `--slashers` is given) |

Checks 1–4 require that `DeployPlatform.s.sol` / `UpgradePlatform.s.sol` was run
at the correct version (issue #244 or later), which writes `dinXxxImpl`,
`dinXxxImplCodehash`, and `owner` into the JSON.  Files written by an older
deploy script are missing these keys — affected items are reported as `[INFO]`
rather than `[DRIFT]`, and the command still exits 0.

## Recording metadata at deploy time

The deploy scripts record the implementation address and its extcodehash
automatically.  To also record the deploying git commit, set `GIT_COMMIT_HASH`
before running the script:

```bash
GIT_COMMIT_HASH=$(git rev-parse HEAD) \
  forge script foundry/script/DeployPlatform.s.sol \
    --rpc-url "$RPC_URL" --broadcast ...
```

The same variable works for `UpgradePlatform.s.sol`.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed (or reported as `[INFO]` due to missing recorded values) |
| 1 | At least one `[DRIFT]` or `[ERROR]` item |

## Limitations

A clean run does not prove that nothing else was deployed or authorized outside
the deployments file.  Only the contracts recorded in the file are checked.
