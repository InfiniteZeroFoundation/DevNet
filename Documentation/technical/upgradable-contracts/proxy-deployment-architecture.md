# Proxy Deployment Architecture — Who Deploys the Proxies, and Does the Toolchain Matter?

**Date:** 2026-07-06
**Status:** Decision record + explainer
**Decides:** How `dincli` deploys the four upgradeable platform contracts (`DinToken`, `DinCoordinator`, `DinValidatorStake`, `DINModelRegistry`), and why the Hardhat-vs-Foundry question is almost entirely irrelevant to that decision.
**Related:** [`hardhat/README.md`](./hardhat/README.md) (contract design), [`storage_layout.md`](../storage_layout.md), `Developer/discussion/migrate_to_foundy.md`

---

## 1. The decision in one paragraph

`dincli`'s deploy commands will perform proxy deployment **natively in web3.py**: deploy the implementation contract, then deploy OpenZeppelin's `TransparentUpgradeableProxy` pointing at it with encoded `initialize()` calldata — as raw signed transactions, with no toolchain plugin in the loop. `dincli` will **not** shell out to `npx hardhat run scripts/deploy-platform.ts`, and will not shell out to a future `forge script` either. The Hardhat and Foundry plugins remain what they already are: **development-time validators and test tooling**, not runtime dependencies.

The rest of this document explains what that actually means, what the plugins really do, and answers the two recurring questions: *does Hardhat vs Foundry matter here?* and *how can the two contract trees be "the same" when they import different plugins?*

---

## 2. What "deploying an upgradeable contract" actually is

Strip away the plugin magic and a Transparent Proxy deployment is exactly **two transactions**:

```
Tx 1: deploy the implementation
      DinToken implementation — constructor runs _disableInitializers(), nothing else.
      Constructor takes no args for any of our 4 contracts.

Tx 2: deploy the proxy
      TransparentUpgradeableProxy(
          implementationAddress,   // where delegatecalls go
          initialOwner,            // who will own the auto-created ProxyAdmin
          initCalldata             // abi.encodeCall(Impl.initialize, (...args))
      )
```

Three facts that make this simple enough to do from any web3 client:

1. **The proxy runs `initialize()` atomically.** The `initCalldata` passed to the proxy constructor is `delegatecall`ed into the implementation during proxy construction. There is no window where the proxy exists uninitialized — no front-running risk on `initialize()`.
2. **OZ v5's `TransparentUpgradeableProxy` deploys its own `ProxyAdmin`.** You don't deploy or manage a ProxyAdmin yourself; the proxy constructor creates one internally and makes `initialOwner` its owner. (Its address is readable from the ERC-1967 admin slot afterwards.)
3. **The implementation address, admin address, and init state all live in well-known ERC-1967 storage slots** — any client can read them back for verification; no plugin bookkeeping is required to *use* the contract.

So the entire "platform bootstrap" is: 4 × (Tx1 + Tx2) plus the three wiring calls (`setCoordinator`, `updateValidatorStakeContract`), in the canonical 6-step order documented in [`hardhat/README.md §5`](./hardhat/README.md). Every one of those is an ordinary transaction that `dincli`'s existing `build_and_send_tx` machinery already knows how to sign and send.

What `dincli` needs as *input*: the ABI + creation bytecode of each implementation, and of `TransparentUpgradeableProxy` itself — all available as compiler artifacts (JSON files). Which compiler produced them is invisible at this layer.

---

## 3. The three candidate architectures (and why two were rejected)

### Option A — dincli shells out to Hardhat: `npx hardhat run scripts/deploy-platform.ts` ❌

- **Runtime dependency on the entire Node toolchain.** Every operator machine that runs `dincli dindao deploy ...` would need Node, npm, the repo's `node_modules` (~hundreds of MB), and a compiled Hardhat project. `dincli` is a pip-installable Python CLI; its deploy commands must work on a machine that has never run `npm install`.
- **Split-brain signing.** The Hardhat script signs with accounts from `hardhat.config.ts`/env, not with the wallet `dincli system connect-wallet` loaded. Two key-management paths for one action is exactly the kind of security seam the keystore work (task_300626_3) is trying to eliminate.
- **Dies with the migration.** The team decision of 2026-07-03 is Foundry-only; `hardhat/` is scheduled for deletion. Building dincli on top of it now means rebuilding dincli when it goes.
- **Output parsing.** dincli would learn deployed addresses by scraping stdout or reading `deployments/<network>.json` — brittle coupling to script log format.

### Option B — dincli shells out to Foundry: `forge script Deploy...` ❌ (same disease, different toolchain)

Identical structural problems: a Rust toolchain + git-submodule libs as a runtime dependency of a Python CLI, a second signing path (`forge`'s wallet handling), stdout/broadcast-file parsing, plus one extra: `openzeppelin-foundry-upgrades`'s deploy helpers require **`ffi = true`** and Node at runtime anyway (see §5), so Option B secretly contains Option A.

### Option C — pure web3.py: dincli builds the two transactions itself ✅ chosen

- **Zero toolchain at runtime.** Operators need Python + the artifact JSONs that already ship with/alongside dincli (`dincli/abis/`, `--artifact` flag). Nothing else.
- **One signing path.** The same connected wallet, nonce management, and `build_and_send_tx` flow used by every other dincli command.
- **Toolchain-agnostic by construction.** The only input is artifact JSON. Whether it came from `hardhat compile` or `forge build` is a file-path/format detail (§6). This is what makes the fix survive the Foundry migration untouched.
- **Explicit, auditable wiring.** The 6-step order lives in reviewable Python, matching the documented deployment order, instead of being buried in a script another toolchain executes.

**Cost of Option C (and why it's acceptable):** we forgo the OZ plugin's *deploy-time* safety validation and its upgrade manifest. That is a real feature — but it's a **development-time concern, and it's already covered twice in CI**: `upgrades.validateUpgrade()` runs in every Hardhat upgrade test, and `Upgrades.validateImplementation()` runs against all four contracts in `foundry/test/UpgradeValidation.t.sol`. A contract that reaches `develop` has passed both. dincli deploying validated bytecode does not need to re-validate it on the operator's machine.

**Scope boundary:** dincli deploys **V1 proxies** (bootstrap). Performing *upgrades* (swapping implementations on a live proxy) stays a toolchain-script operation (`upgrade-platform.ts` today, `forge script` post-migration) run by the DIN-Representative with the full plugin safety net. If dincli ever grows an `upgrade` command, that's a separate decision with a separate risk profile — do not fold it into this one.

---

## 4. So: does it matter whether we use Hardhat or Foundry?

**At runtime (deployment, dincli, operators): no — provably.** The EVM sees bytecode and transactions. Both toolchains here compile the same source with the same compiler and settings:

| Setting | `hardhat/hardhat.config.ts` | `foundry/foundry.toml` |
|---|---|---|
| solc | 0.8.28 | 0.8.28 |
| EVM version | `cancun` (required for `ReentrancyGuardTransient`'s TSTORE/TLOAD) | `cancun` |
| Optimizer | enabled, runs=200 | enabled, runs=200 |
| via-IR | `viaIR: true` | `via_ir = true` |

With matching source and matching settings, the ABI, storage layout, and runtime behavior are identical; the bytecode is identical up to the metadata hash solc appends. And only *one* build's bytecode ever gets deployed anyway — the artifact dincli is pointed at.

**At development time: yes, but only for developer workflow.** Test language (TypeScript/chai vs Solidity/forge-std), test speed, fuzzing, gas reports, verification tooling — that's the entire substance of the Foundry migration discussion (`migrate_to_foundy.md`), and none of it leaks into what gets deployed or how dincli talks to it.

The two places toolchain choice physically touches dincli/harness, and their cost to change:

| Touchpoint | Today | After migration | Cost |
|---|---|---|---|
| Artifact JSON | `hardhat/artifacts/.../X.json` — `{abi, bytecode: "0x.."}` | `foundry/out/X.sol/X.json` — `{abi, bytecode: {object: "0x.."}}` | ~5-line format shim in `get_contract_instance` (read `bytecode.object` when `bytecode` is a dict) |
| Harness local node | `npx hardhat compile` + `npx hardhat node` in `tests/dincli/conftest.py` | `forge build` + `anvil` | conftest-only diff; anvil is a drop-in JSON-RPC replacement |

That's it. This is why the coordination doc's design rule is: *the word "hardhat" appears nowhere in the Python except a default artifact path.*

---

## 5. "Aren't they importing different plugins?" — the three-layer answer

The confusion dissolves once you separate three layers that the word "imports" conflates.

### Layer 1 — Contract source: identical files, same library, different *path resolution*

The production contracts import the **OpenZeppelin library**, not any plugin:

```solidity
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";
```

That import string is resolved differently per toolchain — and that's the *only* difference:

- **Hardhat:** Node module resolution → `hardhat/node_modules/@openzeppelin/contracts-upgradeable/...` (installed by npm from the same published package).
- **Foundry:** `foundry/remappings.txt` →
  ```
  @openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/
  @openzeppelin/contracts-upgradeable/=lib/openzeppelin-contracts-upgradeable/contracts/
  ```
  pointing at git submodules of the same upstream repos.

Same import statements, same library source, two package managers. **Verified concretely (2026-07-06):** all 7 `.sol` files are byte-identical between the PR #13 branch's `hardhat/contracts/` and `develop`'s `foundry/src/` — including NatSpec. The contracts don't just behave the same; they are the same files.

### Layer 2 — What is *never* imported by production contracts: the plugins

Neither `@openzeppelin/hardhat-upgrades` nor `openzeppelin-foundry-upgrades` appears in any `import` in `hardhat/contracts/` or `foundry/src/`. Zero plugin code is compiled into the implementations, the proxy, or anything on-chain. The plugins are imported only by **tooling code**:

| Who imports plugin code | File | Plugin |
|---|---|---|
| Hardhat deploy/upgrade scripts | `hardhat/scripts/*.ts`, `hardhat/deploy/helpers.ts` | `upgrades.deployProxy / upgradeProxy / validateUpgrade` from `@openzeppelin/hardhat-upgrades` |
| Hardhat upgrade tests | `hardhat/test/*.upgrade.test.ts` | same |
| Foundry validation test | `foundry/test/UpgradeValidation.t.sol` | `Upgrades.validateImplementation` from `@openzeppelin/foundry-upgrades/Upgrades.sol` |

The one shared on-chain artifact both plugins deploy is OZ's `TransparentUpgradeableProxy` — which comes from the *library* (Layer 1), not from either plugin. dincli deploying that same artifact via web3.py produces a proxy indistinguishable from one the Hardhat plugin deployed.

### Layer 3 — What the plugins actually do (and the punchline: they're the same engine)

Both plugins perform the same three services at development time:

1. **Safety validation** — parse compiler output and reject upgrade-unsafe patterns: constructors with logic, `immutable`/`selfdestruct`/`delegatecall` misuse, missing initializer wiring, and storage-layout incompatibility between versions (using the `storageLayout` compiler output and annotations like `@custom:oz-upgrades-from`).
2. **Orchestrated deploy** — the two transactions from §2, wrapped.
3. **Bookkeeping** — tracking proxy/implementation addresses.

The punchline: **both plugins delegate validation to the same engine**, OpenZeppelin's `@openzeppelin/upgrades-core` (a Node package). The Hardhat plugin calls it in-process; the Foundry plugin shells out to it — via Foundry's FFI, which is exactly why `foundry.toml` sets `ffi = true` and why the Foundry plugin's docs require Node installed even in a "pure Foundry" project. Gate 1 of the migration (all four contracts passing `validateImplementation` under Foundry) was never really in doubt for *rule-compatibility* reasons — it's the same rules — it verified that the plugin's build-info plumbing works against our via-IR/cancun build.

So "different plugins" ≠ "different validation" ≠ "different deployed contracts." It's one validation engine with two front-ends, over one contract source tree that exists in two package-manager layouts.

---

## 6. Practical invariants to keep this true

1. **Keep the two trees byte-identical** until `hardhat/` is deleted. Any contract change on the PR #13 lineage must be mirrored into `foundry/src/` in the same PR (or the Hardhat copy dropped, post-migration).
2. **Keep compiler settings in lockstep** (solc version, `cancun`, via-IR, optimizer runs). A drift here doesn't change behavior/ABI/storage, but it forfeits bytecode-level comparability and can perturb contract-size/gas margins under via-IR.
3. **dincli reads artifacts, never runs toolchains.** The artifact-format shim (accept both `bytecode` and `bytecode.object`) is the entire extent of dincli's toolchain awareness.
4. **Proxy upgrades stay behind the plugin safety net** (toolchain scripts + CI validation), regardless of which toolchain survives. dincli's native deployment is for V1 bootstrap only.
5. **Pin the `TransparentUpgradeableProxy` artifact source.** dincli should ship/reference the proxy artifact from a known OZ contracts version (currently v5.x, per `foundry/package.json` → `@openzeppelin/contracts ^5.6.1`), not recompile it ad hoc — the proxy is the one piece of third-party bytecode dincli deploys.
