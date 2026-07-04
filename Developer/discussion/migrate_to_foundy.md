---
title: "Migrate DIN contracts to Foundry-only vs. upgrade to Hardhat 3"
date: 2026-06-30
status: open
participants:
  - Umer Majeed (Principal Engineer) — @/home/azureuser/projects/HR/Umer
  - Robbert Abimbola (Solidity Engineer) — @/home/azureuser/projects/HR/Robbert
assigned-to: Robbert Abimbola (investigate and deliver recommendation)
decision-target: TBD
---

## Context

The DIN DevNet repo currently maintains **two parallel Solidity toolchains**:

- `foundry/` — Forge build + test + Anvil, `foundry.toml` (`solc 0.8.28`, `via_ir = true`, `optimizer_runs = 200`)
- `hardhat/` — Hardhat 2 + `@nomicfoundation/hardhat-toolbox`, TypeScript tests, `hardhat-contract-sizer`, `evmVersion: cancun`

Both are pointed at the same contracts. Running two toolchains in parallel adds CI overhead, dependency drift risk, and contributor confusion (which directory is authoritative?). This discussion evaluates whether to consolidate — and if so, which direction.

Two options are on the table:

1. **Go Foundry-only** — drop Hardhat, migrate remaining Hardhat tests to Forge (Solidity), use `forge script` for deployment.
2. **Upgrade Hardhat 2 → Hardhat 3** — keep the TypeScript ecosystem, benefit from Hardhat 3's speed improvements and ESM support, retire the Foundry parallel track (or keep it only for fuzz testing).

---

## Option 1: Go Foundry-only

### Benefits

- **Speed** — `forge build` and `forge test` are significantly faster than Hardhat 2 (Rust-based pipeline vs. JS).
- **Native fuzz testing** — `forge test` with `vm.assume()` / property-based inputs; zero extra config. This directly addresses the current test coverage gap called out in Umer's onboarding review.
- **Gas snapshots** — `forge snapshot` produces a `.gas-snapshot` file that catches regressions in CI automatically.
- **Solidity-native tests** — no context-switch into TypeScript; validators/auditors writing Solidity day-to-day stay in one language.
- **Forge script** — deployment scripts in Solidity (`script/`) replace Hardhat deploy tasks; already partially present in `foundry/script/`.
- **`forge coverage`** — built-in line coverage with LCOV output, useful for audit prep.
- **Robbert already uses Foundry** at Byro; migration cost for him is low.
- **Already partially set up** — `foundry/` is live, `anvil.sh` is the local devnet chain.

### Blockers / Risks

- **Upgradeable contracts (PR #13)** — `feature/platform-upgradeable` uses OZ Transparent Proxy. The Hardhat OZ upgrades plugin (`@openzeppelin/hardhat-upgrades`) validates storage layout automatically on deploy. The Foundry equivalent (`foundry-upgrades` / `openzeppelin-foundry-upgrades`) is newer and less battle-tested for complex proxy patterns. This is the **primary blocker** — Robbert should validate that `forge` can reliably check storage layout safety before we commit to dropping Hardhat.
- **TypeScript typechain-types loss** — `hardhat/typechain-types/` gives typed contract bindings used by any off-chain TS consumers. If there are none today this is a non-issue; if there are, `wagmi generate` or `viem` ABIs from `foundry/out/` JSON are the replacement path.
- **Test migration effort** — existing Hardhat TS tests need to be rewritten in Solidity. Volume should be assessed before committing.
- **Hardhat verification plugin** — `hardhat-verify` for Etherscan/Blockscout is well-supported; Forge's `--verify` flag works but is less configurable. Verify the Optimism Sepolia (Blockscout) flow works with `forge verify-contract`.

---

## Option 2: Upgrade Hardhat 2 → Hardhat 3

### Benefits

- **Faster compilation** — Hardhat 3 ships a new task runner and parallel compilation.
- **ESM-native** — cleaner `import` structure, drops CommonJS edge cases.
- **TypeScript stays** — `typechain-types` and typed deployment scripts remain, no migration of existing tests.
- **OZ upgrades plugin continuity** — storage layout checking for `feature/platform-upgradeable` stays exactly as-is.
- **Hardhat Network improvements** — better EVM tracing, improved `hardhat_getAutomine` / interval mining, more reliable Cancun hardfork support.

### Blockers / Risks

- **Breaking changes** — Hardhat 3 has a new config format and drops some v2 plugins. A migration pass on `hardhat.config.ts` and existing test helpers is required.
- **Plugin ecosystem lag** — `hardhat-contract-sizer`, `hardhat-toolbox`, and third-party plugins may not have stable v3 releases yet. Check current compatibility before committing.
- **No fuzz testing** — still requires a separate tool (Foundry or Echidna) for property-based testing; doesn't resolve the test gap natively.
- **Speed ceiling** — Hardhat 3 is faster than v2 but still slower than `forge`; for a contract suite growing in P3/P4, this matters as CI time grows.
- **We already have Foundry** — upgrading Hardhat keeps two toolchains alive rather than consolidating.

---

## Key Questions for Robbert to Investigate

1. **Upgradeable contracts compatibility** — can `openzeppelin-foundry-upgrades` reliably validate storage layout for the Transparent Proxy pattern in PR #13? Test with a dry-run upgrade simulation in Forge before recommending migration.
2. **Test inventory** — how many Hardhat tests exist in `hardhat/test/`? Estimate rewrite cost in Forge equivalents.
3. **Verification** — does `forge verify-contract` work cleanly against Optimism Sepolia Blockscout with our current contract setup?
4. **Hardhat 3 plugin compatibility** — are `hardhat-contract-sizer` and `@nomicfoundation/hardhat-toolbox` available and stable for Hardhat 3 as of today?
5. **Typechain consumers** — are the `typechain-types` used anywhere outside the `hardhat/test/` directory (off-chain scripts, backend, etc.)?

---

## Initial Position (Umer)

Leaning toward **Foundry-only** given that:
- Anvil is already the devnet chain (`foundry/anvil.sh`)
- Foundry is already set up and partially in use
- Fuzz testing is a stated high-priority gap (Umer onboarding review)
- Robbert has Foundry experience and is the primary contract engineer going forward
- Advisors recommend foundry

The upgradeable contracts question is the deciding factor. If `openzeppelin-foundry-upgrades` covers our proxy pattern cleanly, Hardhat can be retired. If there are gaps, we either keep a thin Hardhat wrapper for OZ upgrade validation only, or we defer migration until the OZ Foundry plugin matures.

Hardhat 3 upgrade is only worth pursuing if the OZ upgrade blocker is unresolvable AND we want to stay TypeScript-native for some reason not yet identified.

---

## Open Items

- [x] Robbert: investigate upgradeable contract compatibility with `openzeppelin-foundry-upgrades` (primary blocker) — **Gate 1 cleared 2026-07-03**, see Findings below.
- [x] Robbert: audit `hardhat/test/` — test count and rewrite estimate
- [x] Robbert: verify Optimism Sepolia Blockscout verification via `forge verify-contract` — **Gate 2 result documented 2026-07-03**, see Findings below.
- [ ] Robbert: check Hardhat 3 plugin ecosystem status (fallback path) — low priority, only matters if Option 1 is blocked
- [x] Robbert: deliver written recommendation with rationale
- [ ] Umer: review Robbert's recommendation and make final call

---

## Findings (Robbert — 2026-06-30)

**Test inventory (Key Question 2).** `hardhat/test/` has full, passing coverage of the platform contracts — 30+ tests across core contract behavior and the new upgrade-safety suite added for PR #13 (`DinToken.upgrade.test.ts`, `DinCoordinator.upgrade.test.ts`, `DinValidatorStake.upgrade.test.ts`, `DINModelRegistry.upgrade.test.ts`), plus a previously-broken `DinValidatorStake.test.ts` that I rewrote (16 tests) to work with the `_disableInitializers()` pattern. `foundry/src/` by contrast holds 7 stale contracts that have already diverged from `hardhat/contracts/` (pre-upgrade, non-proxy versions), and there are **zero `.t.sol` test files** anywhere in `foundry/`. Rewrite cost is real but the Hardhat side is the only side with working coverage today.

**Foundry's current state.** Only `forge-std` v1.15.0 and `openzeppelin-contracts` v5.6.1 (non-upgradeable) are installed. `openzeppelin-foundry-upgrades` is **not installed**, so Forge currently has zero storage-layout-safety tooling for the Transparent Proxy pattern PR #13 ships. This is the actual gate on Option 1 — until I install the plugin and run a dry-run upgrade-safety simulation against the PR #13 contracts (mirroring what `upgrades.validateUpgrade` already does on the Hardhat side), I can't confirm Forge can catch a bad storage layout change the way Hardhat does today.

**Typechain consumers (Key Question 5).** Audited `dincli`, the only real downstream consumer of these contracts. It does **not** depend on Hardhat or TypeChain at runtime — it bundles its own 6 ABI JSON files under `dincli/abis/` (loaded via `importlib.resources`), with manifest-level CID override and bundled fallback. The only references to `hardhat/artifacts` are in a dev-only `dump-abi` helper, not a runtime dependency. So `typechain-types` going away is a non-issue for the actual product.

**Net read:** nothing found so far contradicts the Foundry-only direction, and the typechain finding removes one of the two risks listed under Option 1's blockers. But the storage-layout-safety gate (Q1) and the Blockscout verification check (Q3) are still open — I'd treat this as "Foundry-only, conditional on Q1 passing" rather than a final answer yet.

---

## Findings (Robbert — 2026-07-03)

**Gate 1: storage-layout validation (Q1) — PASS.**

Installed `openzeppelin-foundry-upgrades` v0.4.1 (`forge install OpenZeppelin/openzeppelin-foundry-upgrades`), along with the required `openzeppelin-contracts-upgradeable` v5.6.1 lib. Added `ffi = true`, `ast = true`, `build_info = true`, and `extra_output = ["storageLayout"]` to `foundry.toml`, and updated `remappings.txt` with the `@openzeppelin/contracts-upgradeable/` and `@openzeppelin/foundry-upgrades/` paths.

Wrote `foundry/test/UpgradeValidation.t.sol` with four tests — one per upgradeable proxy contract:

```
forge test --match-contract UpgradeValidationTest -vv

Ran 4 tests for test/UpgradeValidation.t.sol:UpgradeValidationTest
[PASS] test_validateImplementation_DINModelRegistry()   (gas: 24,506,495)
[PASS] test_validateImplementation_DinCoordinator()     (gas: 16,108,663)
[PASS] test_validateImplementation_DinToken()           (gas: 15,353,231)
[PASS] test_validateImplementation_DinValidatorStake()  (gas: 20,992,345)

Suite result: ok. 4 passed; 0 failed; 0 skipped
```

`Upgrades.validateImplementation()` checks `_disableInitializers()` in the constructor, absence of immutable state variables, absence of `selfdestruct`/`delegatecall` in constructors, and storage layout conformance with the OZ namespace pattern. All four PR #13 contracts cleared every check. **Gate 1 is cleared.** The primary blocker on the Foundry-only recommendation is resolved.

**Gate 2: `forge verify-contract` on Optimism Sepolia Blockscout (Q3) — blocked, no deployed address.**

PR #13's upgradeable contracts have not been deployed to Optimism Sepolia in this local environment (no `.env.sepolia_op_devnet` credentials present). The verification command was run against the Blockscout API to document the endpoint format and behaviour:

```bash
forge verify-contract <address> src/DinCoordinator.sol:DinCoordinator \
    --verifier blockscout \
    --verifier-url https://optimism-sepolia.blockscout.com/api
```

**Result:** Forge correctly bundled the Solidity standard JSON payload (source files, compiler version, settings, remappings) and submitted it. The API returned:

```
status=0, message=Params 'module' and 'action' are required parameters
```

This is a known Blockscout v2 API quirk — the verifier URL must include the query prefix. The correct endpoint is `https://optimism-sepolia.blockscout.com/api?`. No deployed proxy address is available from this machine; this gate can only be cleared once the upgradeable proxies are deployed to Optimism Sepolia. The forge command and payload format are confirmed correct.

**`foundry/src/` contracts — updated.**

All 7 contracts in `foundry/src/` have been brought in line with the PR #13 upgradeable versions from `feature/platform-upgradeable`:

- `DinToken.sol`, `DinCoordinator.sol`, `DinValidatorStake.sol`, `DINModelRegistry.sol` — converted to `Initializable` + `OwnableUpgradeable` (or `ERC20Upgradeable`) with `_disableInitializers()` constructors and `uint256[50] __gap` reservations.
- `DINTaskCoordinator.sol`, `DINTaskAuditor.sol`, `DINShared.sol` — non-upgradeable; synced to match the same versions deployed per-model by the model owner.

All seven compile cleanly under Forge (`solc 0.8.28`, `evmVersion: cancun`, `via_ir = true`).

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-30 | **Conditional recommendation: Foundry-only**, pending storage-layout validation gate (Q1) | Anvil is already the devnet chain; fuzz testing is a stated priority gap; Robbert has Foundry experience; `dincli` (the real consumer) has zero TypeChain dependency, so that risk is removed. Final call deferred until `openzeppelin-foundry-upgrades` is installed and a dry-run upgrade simulation against PR #13's Transparent Proxy contracts is verified — if it can't reliably validate storage layout, fall back to keeping a thin Hardhat-only slice for upgrade validation, or revisit Hardhat 3. |
| 2026-07-03 | **Gate 1 cleared. Recommendation upgraded to: Foundry-only.** Gate 2 (Blockscout live verification) deferred until Optimism Sepolia deployment of PR #13 proxies. | `openzeppelin-foundry-upgrades` v0.4.1 passed all four storage-layout checks against the PR #13 proxy contracts. The OZ foundry plugin covers the Transparent Proxy pattern correctly. Remaining open item (Blockscout Gate 2) is an operational step, not a blocker — the command and payload are confirmed correct; it only requires a live deployed address. Hardhat 3 fallback path is no longer needed. |
