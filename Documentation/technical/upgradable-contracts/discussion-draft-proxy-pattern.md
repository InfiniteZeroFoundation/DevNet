# Proxy pattern for the platform contracts: keep Transparent, or move to UUPS as we add DAO governance?

> **Draft for github.com/InfiniteZeroFoundation/DevNet › Discussions**
> Category: Ideas / Architecture · Author: @umeradl
> References: [`hardhat/README.md §2`](./hardhat/README.md) · PR #13 (branch `feature/platform-upgradeable`) @ `7817ca1e022b7f8f324e3a813667d56865051051`

## TL;DR

PR #13 shipped the four platform contracts (`DinToken`, `DinCoordinator`, `DinValidatorStake`, `DINModelRegistry`) behind **OpenZeppelin Transparent Proxies** (`PROXY_KIND = "transparent"`), with upgrade authority held by a single DIN-Representative EOA via a `ProxyAdmin`.

As we move toward **DAO governance**, I want to reopen the proxy-pattern choice. My recommendation: **UUPS with a timelock-gated `_authorizeUpgrade` and CI-enforced upgrade validation is the better default for DIN** — *provided* we keep a small, disciplined set of implementation authors. If implementation authorship ever opens up to independent contributors, Transparent's structural safety starts earning its gas premium. This thread is to pressure-test that before we commit.

---

## 1. Where we are today

From `hardhat/README.md §2` and the contracts in PR #13:

- **Pattern:** Transparent Proxy, one shared `PROXY_KIND` constant so scripts and tests can't diverge (`hardhat/deploy/constants.ts`).
- **Upgrade key:** `ProxyAdmin` ownership, currently the DIN-Representative EOA (README §7, invariant 5).
- **Conversion recipe (already done):** `Ownable`→`OwnableUpgradeable`, constructor→`initialize()` with `_disableInitializers()`, immutables→storage, `uint256[50] private __gap`, transient reentrancy guard on the cancun EVM.
- **Upgrade safety:** `upgrades.validateUpgrade()` in every upgrade suite; four `*V2.sol` contracts exercise the path. Expected `32 passing`.

The README's stated rationale for Transparent (§2) was: **a bad V2 cannot brick the proxy** (upgrade logic lives in `ProxyAdmin`, not the implementation), it **fits a single-EOA governance model today**, and the **per-call gas overhead is an accepted trade-off** for that safety.

That reasoning is sound for *today's* single-owner setup. The question is whether it still holds once "the owner" becomes a DAO pipeline.

## 2. The actual decision variable

For governance specifically, the calculus shifts from the solo-developer case. The real question isn't "which pattern is safer in the abstract" — it's:

> **How much do we trust our own upgrade process once a vote, not a person, authorizes upgrades?**

Both patterns support DAO governance. The difference is *where the upgrade authority physically lives* and *what failure class that exposes.*

## 3. The case for UUPS under DAO governance

- **Governance plugs in natively.** UUPS leaves access control entirely to `_authorizeUpgrade`. That's the hook governance attaches to — instead of `onlyOwner` on an EOA, you write `onlyRole(UPGRADER_ROLE)` held by a **timelock**, not a wallet:

  ```solidity
  function _authorizeUpgrade(address newImpl)
      internal
      override
      onlyRole(UPGRADER_ROLE)   // held by the timelock
  {}
  ```

- **Cheaper where it matters to a DAO:** lower proxy-deployment cost (relevant if DIN spawns many proxied contracts) and lower per-call runtime gas (paid by every user, forever; compounds on L1).
- **The DAO can evolve its own upgrade policy.** Because upgrade logic ships *inside* each implementation, a future V3 can add a longer delay, an extra guard, or **renounce upgradeability entirely** (ship an implementation with no upgrade path → permanent ossification) as a one-proposal decision. Many DAOs explicitly want that endgame.

## 4. The case Transparent still has for a DAO

- **Upgrade authority is structurally separate from application code.** The `ProxyAdmin` is owned by the timelock once, at deployment; after that **no implementation — however buggy or malicious — can alter the upgrade machinery**, because it doesn't live in the implementation.
- **The UUPS bricking risk is not hypothetical for a DAO.** An upgrade proposal is code written by one contributor, reviewed by token holders who mostly don't read Solidity, and executed automatically after a vote. If that implementation's `_authorizeUpgrade` is broken or the `UUPSUpgradeable` inheritance is mangled, the proxy is **frozen forever and no vote can fix it.** Transparent makes that entire failure class impossible.
- **Small permission surface.** One `ProxyAdmin` can govern a whole fleet of proxies.
- Price: ~2–3k extra gas per call and a heavier deploy. Note OZ v5's Transparent redesign (immutable admin, built-in `ProxyAdmin`) shrank the old gas gap — **don't let 2021-era comparisons over-weight the decision.**

## 5. How governance composes (mostly pattern-independent)

The governance stack is the same shape either way; the pattern only changes *what* sits at the bottom:

```
Safe (multisig)  ──PROPOSER_ROLE──▶  Timelock  ──upgrade authority──▶  Proxy
   emergency                          (24–48h)                         admin (Transparent)
   CANCELLER                                                           or _authorizeUpgrade (UUPS)
```

- **Why a timelock in the middle:** it gives DIN participants (clients, aggregators, auditors) a guaranteed window to see a pending upgrade and exit if they disagree, and it means a compromised multisig can't instantly swap in malicious logic — there's a 24–48h window to notice the scheduled tx and cancel.
- **Start simple, graduate later.** Begin with `Safe → Timelock → Proxy` (honestly what most "DAOs" are in practice). Later insert an OZ `Governor` with token voting *in front*: the Governor becomes the timelock's proposer, the multisig is demoted to emergency `CANCELLER_ROLE`. This is all **role re-wiring on the timelock — the business contracts don't change.**
- **Keep an emergency pause separate** (`Pausable`, gated by the multisig **directly, no timelock**) — stop bleeding fast, change code slowly.
- **Governance contracts themselves (Governor, Timelock, Safe) should be non-upgradeable** — the thing guarding upgrades shouldn't itself be upgradeable, or the trust problem just moves up a level.

## 6. L1/L2 gas — same source, two cost models

DIN's devnet is an OP-stack chain, so this is worth stating explicitly:

- **On L1:** execution + storage dominate. Pack structs into single slots (e.g. role accounts packing `role + status + index` into one word — cf. `ValidatorInfo`'s `uint64` timestamps + status enum already doing this), minimize `SSTORE`s, cache storage reads in loops, `immutable`/`constant` for deploy-fixed values, custom errors over revert strings (already done across the platform contracts).
- **On OP-stack L2:** execution gas is nearly free; the dominant cost is the **L1 data fee** for publishing calldata. Highest-leverage move is **shrinking calldata**: tighter ABI encoding (`uint64` timestamps in calldata structs), batching many ops into one call, zero-heavy calldata, and compact custom encodings for the extreme cases. Post-Ecotone blobs made this cheaper but size still scales cost.
- **These don't conflict** — struct packing, custom errors, immutables help both layers. Measure with `forge test --gas-report`, and simulate L1 data fees against OP's `GasPriceOracle` predeploy at `0x420000000000000000000000000000000000000F`. Relevant target: the high-frequency aggregator/client calls.

## 7. The genuinely hard part — cross-chain governance (only if we go multi-layer)

If we ever deploy the same governed contracts on **both** L1 and L2, we must decide where governance lives. Clean pattern: governance on one layer (usually L1) sends upgrade instructions to the other through the canonical bridge (`CrossDomainMessenger` on OP stack). The L2 timelock's proposer becomes the L1 governance contract's **aliased** address (L1 address + `0x1111…1111`), and upgrades flow L1 → bridge → L2 timelock → L2 proxy. It works, but **bridge message failures during an upgrade are painful to recover from — rehearse exhaustively on devnet.** This is out of scope for v1 but flagged so we don't design ourselves into a corner.

## 8. Process discipline (the part that actually decides UUPS's safety)

The complexity isn't in any one layer — it's in the failure modes at the seams:

1. **Wire `openzeppelin-foundry-upgrades` / OZ storage-layout + UUPS-compliance validation into CI** so an incompatible layout or broken `_authorizeUpgrade` can't even reach a proposal. (We already run `validateUpgrade()` in tests — this makes it a gate.)
2. **Never let the timelock be the only holder of `CANCELLER_ROLE`.**
3. **Rehearse the full path** (propose → delay → execute → verify the ERC-1967 impl slot) on Sepolia Optimism devnet before mainnet — ideally as a scripted, repeatable `dincli` command.
4. Keep the emergency pause off the upgrade path (§5).

Under that discipline the UUPS bricking risk is nearly eliminated, and we keep the gas + flexibility wins.

## 9. Recommendation

**Adopt UUPS with a timelock-gated `_authorizeUpgrade` and CI-enforced upgrade validation**, on the condition that a small technical group authors all implementations and every upgrade is rehearsed on devnet. A natural v1 wiring given DIN's role structure:

- **3-of-5 Safe** (DIN-Representative + auditors)
- **24–48h Timelock** (Safe = proposer, Safe also = emergency canceller)
- **UUPS proxies** on the four platform contracts
- **calldata-lean encoding** on the hot aggregator/client paths

Stay Transparent (or go hybrid — Transparent for the crown-jewel registry/stake contracts, UUPS for high-traffic peripherals) **if** we expect upgrade proposals from many independent authors the core team doesn't control, or if the DAO's social contract is "the upgrade path itself must be untouchable."

## 10. Open questions for the thread

1. Do we expect implementation authorship to stay within a small core team for the foreseeable future, or open up? (This is *the* deciding question.)
2. Is anyone uncomfortable with the "a broken V2 bricks the proxy forever" failure mode even with CI validation gating it?
3. Timelock delay: 24h or 48h for v1? Trade-off is participant exit window vs. upgrade responsiveness.
4. Do we want the ossification endgame (ability to renounce upgradeability) on the table? That's a point *for* UUPS.
5. Are we ever going multi-layer (L1 + L2)? If yes, §7 changes how we structure governance from day one.
6. Hybrid (Transparent for registry/stake, UUPS for the rest) — worth the mental overhead of two patterns, or premature?

Please react / comment. I'd like to converge before we touch the `feature/platform-upgradeable` contracts again.
