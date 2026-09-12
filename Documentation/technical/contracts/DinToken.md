# DinToken — Technical Documentation

> **File:** `hardhat/contracts/DinToken.sol`
> **SPDX-License-Identifier:** MIT
> **Solidity:** `^0.8.28`
> **Standard:** ERC-20 (OpenZeppelin upgradeable)

---

## 1. Overview

`DinToken` is the native utility token of the DIN Protocol ecosystem. It is a minimal ERC-20 contract deployed **behind an OpenZeppelin Transparent Proxy**, whose minting authority is bound to a single address — the `DinCoordinator` proxy — wired once after deployment via the one-shot `setCoordinator()`. The token carries 18 decimal places (inherited from OpenZeppelin's `ERC20Upgradeable`).

The token serves as the staking and slashing currency: validators acquire DIN tokens through `DinCoordinator.depositAndMint()`, then lock them in `DinValidatorStake` to participate in the network.

---

## 2. Inheritance & Dependencies

| Component | Source | Purpose |
|-----------|--------|---------|
| `Initializable` | OpenZeppelin `@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol` | Initializer guard for the proxy pattern |
| `ERC20Upgradeable` | OpenZeppelin `@openzeppelin/contracts-upgradeable/token/ERC20/ERC20Upgradeable.sol` | Token accounting; name/symbol set in `initialize` |
| `OwnableUpgradeable` | OpenZeppelin `@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol` | Admin role that performs the one-shot coordinator wiring |

> **Note:** `onlyOwner` (the OZ owner, set in `initialize`) and `onlyCoordinator` (the custom minter modifier) are **different roles** held by different parties: the owner is the deployer account, the coordinator is the `DinCoordinator` proxy contract. The owner cannot mint; the coordinator cannot re-wire itself.

---

## 3. State Variables

| Variable | Type | Visibility | Description |
|----------|------|-----------|-------------|
| `coordinator` | `address` | `public` | The sole address allowed to call `mint()`. Zero until `setCoordinator()` is called; can be set exactly once (guarded by `CoordinatorAlreadySet`). Expected to be the `DinCoordinator` proxy. |
| `__gap` | `uint256[50]` | `private` | Reserved storage slots for future state variables, protecting the proxy storage layout across upgrades. |

All token balances, allowances, total supply, name (`"DIN Token"`), and symbol (`"DIN"`) are managed by the inherited `ERC20Upgradeable` base (which stores them at namespaced storage locations, per OZ v5's ERC-7201 pattern).

---

## 4. Custom Errors

| Error | Condition |
|-------|-----------|
| `InvalidAddress()` | `to == address(0)` on a mint call, or `coordinator_ == address(0)` on `setCoordinator` |
| `Unauthorized()` | `mint` caller is not `coordinator` |
| `CoordinatorAlreadySet()` | `setCoordinator` called after the coordinator was already wired |

Custom errors are preferred over `require` strings for gas efficiency.

---

## 5. Events

| Event | Parameters | Emitted When |
|-------|-----------|--------------|
| `TokensMinted` | `address indexed to`, `uint256 amount` | Every successful `mint()` call, in addition to the inherited ERC-20 `Transfer` event. |
| `CoordinatorSet` | `address indexed coordinator` | The one-shot `setCoordinator()` wiring call. |

---

## 6. Access Control

Two contract-level roles, plus the proxy-level admin:

```
owner() — OwnableUpgradeable; set to the account that ran initialize (deployer)
  └── setCoordinator()        ← one-shot wiring, reverts once coordinator != 0

coordinator — the DinCoordinator proxy, wired via setCoordinator()
  └── mint()                  ← guarded by onlyCoordinator

ProxyAdmin (proxy level, owned by deployer)
  └── can upgrade the implementation (see §9)
```

```solidity
modifier onlyCoordinator() {
    if (msg.sender != coordinator) revert Unauthorized();
    _;
}
```

Until `setCoordinator()` is called, `coordinator` is `address(0)` and every `mint()` reverts — the token **fails closed** during deployment.

---

## 7. Functions

### 7.1 Constructor & `initialize`

```solidity
constructor()
```

- Runs only on the raw implementation contract, never through the proxy.
- Calls `_disableInitializers()`, so the implementation itself can never be initialized — a direct `initialize()` on it reverts with `InvalidInitialization` (covered by `hardhat/test/DinToken.upgrade.test.ts`).

```solidity
function initialize() external initializer
```

- Runs exactly once, atomically with proxy deployment.
- `__ERC20_init("DIN Token", "DIN")` — sets token metadata.
- `__Ownable_init(msg.sender)` — the deployer becomes `owner()`.
- No initial supply is minted, and **no minter exists yet**: `coordinator` stays `address(0)` until the wiring step below.

---

### 7.2 `setCoordinator` — One-Shot Minter Wiring

```solidity
function setCoordinator(address coordinator_) external onlyOwner
```

| Parameter | Description |
|-----------|-------------|
| `coordinator_` | Address of the `DinCoordinator` proxy that gains exclusive minting rights. |

**Algorithm:**
1. Guard: `onlyOwner` (OZ owner) — reverts with `OwnableUnauthorizedAccount` otherwise.
2. Guard: reverts with `CoordinatorAlreadySet()` if `coordinator != address(0)` — the wiring is **one-shot**.
3. Guard: reverts with `InvalidAddress()` if `coordinator_ == address(0)`.
4. Stores `coordinator = coordinator_` and emits `CoordinatorSet(coordinator_)`.

**Design rationale:** the coordinator sits behind its own Transparent Proxy, so its address is stable across coordinator upgrades — the minter never needs re-pointing. Replacing the coordinator with a *different proxy* is deliberately impossible at the contract level; it would require either upgrading this token implementation or deploying a new token proxy.

---

### 7.3 `mint`

```solidity
function mint(address to, uint256 amount) external onlyCoordinator
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `to` | `address` | Recipient of newly minted tokens. |
| `amount` | `uint256` | Number of tokens to mint (18-decimal representation). |

**Algorithm:**
1. Guard: `onlyCoordinator` — reverts with `Unauthorized()` if `msg.sender != coordinator`.
2. Guard: reverts with `InvalidAddress()` if `to == address(0)`.
3. Calls OpenZeppelin's internal `_mint(to, amount)`, which:
   - Increments `totalSupply` by `amount`.
   - Increments `balanceOf[to]` by `amount`.
   - Emits `Transfer(address(0), to, amount)`.
4. Emits `TokensMinted(to, amount)` for off-chain indexing.

Called exclusively by `DinCoordinator.depositAndMint()`.

---

## 8. Token Economics

| Property | Value |
|----------|-------|
| Name | `DIN Token` |
| Symbol | `DIN` |
| Decimals | `18` |
| Initial Supply | `0` (no pre-mint) |
| Minting Authority | `DinCoordinator` proxy (one-shot `setCoordinator`) |
| Burning | Not implemented |

**Minting rate:** Defined entirely by `DinCoordinator.dinPerEth`. Default is `1,000,000 DIN per 1 ETH` (i.e., 1 ETH → 1M × 10¹⁸ raw token units).

---

## 9. Ownership & Upgradeability

| Plane | Who | Controls |
|-------|-----|----------|
| Contract owner (`owner()`) | Account that ran `initialize` (deployer) | `setCoordinator` (one-shot); transferable via `transferOwnership` |
| Minter (`coordinator`) | `DinCoordinator` proxy | `mint` only |
| Proxy admin (`ProxyAdmin`) | Deployed by the OZ upgrades plugin, owned by the deployer | Swapping the implementation |

- **Proxy kind:** OpenZeppelin Transparent Proxy; the token address that balances live at is permanent, only code changes on upgrade.
- **Upgrade path:** `CONTRACT=DinToken npx hardhat run scripts/upgrade-platform.ts --network <network>` (reads/writes `hardhat/deployments/<network>.json`).
- **Storage-layout safety:** the `__gap` array reserves 50 slots; ERC-20 balances live in OZ's namespaced (ERC-7201) storage. `hardhat/test/DinToken.upgrade.test.ts` validates a V2 fixture (`hardhat/contracts/upgrade/DinTokenV2.sol`) with `upgrades.validateUpgrade` and asserts balances, `coordinator` wiring, and both access-control paths survive an upgrade.
- **Trust implication:** the "coordinator can never change" guarantee is enforced at the *implementation* level. A ProxyAdmin-authorized upgrade could replace that rule (or the entire token logic), so the guarantee is ultimately bounded by the security of the ProxyAdmin owner key.

---

## 10. Deployment & Post-Deploy Wiring

From `hardhat/scripts/deploy-platform.ts`: the token is the **first** platform contract deployed, because everything else references it.

```
1. Deploy DinToken proxy          → initialize()            (owner = deployer, no minter yet)
2. Deploy DinCoordinator proxy    → initialize(dinToken)
3. dinToken.setCoordinator(dinCoordinator)                  ← minting goes live here
```

Between steps 1 and 3 every `mint()` reverts with `Unauthorized()` — including `DinCoordinator.depositAndMint()` — so a half-wired deployment cannot mint. Because `setCoordinator` is one-shot, an attacker who somehow raced step 3 would permanently brick minting rather than gain it (and the call is `onlyOwner` anyway).

---

## 11. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Unlimited minting | `coordinator` can be set exactly once (`CoordinatorAlreadySet` guard); only the `DinCoordinator` proxy can mint. |
| Minting before wiring | `coordinator` defaults to `address(0)`; `mint` fails closed. |
| Minting to zero address | Explicit `InvalidAddress()` guard before `_mint`. |
| Re-entrancy | N/A — no ETH is transferred; pure ERC-20 state update. |
| Owner abuse | `owner()` cannot mint; its only power is the one-shot `setCoordinator` (spent at deployment) — though it persists as a role via `transferOwnership`. |
| Re-initialization / implementation hijack | `initializer` modifier + `_disableInitializers()` in the constructor. |
| Malicious upgrade | Governed by ProxyAdmin ownership; no timelock — see §9. |

---

## 12. Interactions with Other Contracts

```
Deploy script (hardhat/scripts/deploy-platform.ts)
  ├── deploys DinToken proxy first
  └── wires DinToken.setCoordinator(dinCoordinator) after the coordinator exists

DinCoordinator
  └── calls DinToken.mint(user, amount) on every depositAndMint()

DinValidatorStake
  └── holds DIN tokens on behalf of stakers (via ERC-20 transferFrom)
```

---

## 13. Known Limitations & Future Work

- No `burn` function — slashed tokens stay locked in `DinValidatorStake` with no on-chain destruction (see `TODO` in `DinValidatorStake.sol`).
- No `pause` or emergency stop mechanism.
- Minting authority cannot be re-pointed at the contract level (one-shot `setCoordinator`); moving it would require an implementation upgrade or a new token proxy.
- The OZ owner role persists after its single job (`setCoordinator`) is done; renouncing it post-deployment would remove that surface but also forfeit any future admin hooks an upgrade might add.

---

## 14. Change Log

### 2026-07 — Upgradeable conversion (PR 13)

- Converted to a Transparent Proxy: `ERC20` → `Initializable` + `ERC20Upgradeable` + `OwnableUpgradeable`; pragma bumped `^0.8.19` → `^0.8.28`.
- Constructor no longer takes `owner_` or sets token metadata; it only calls `_disableInitializers()`. New `initialize()` sets name/symbol and `owner()` (the deployer).
- **Minter model changed:** the immutable `OWNER` (set at construction, intended to be the coordinator) is replaced by a `coordinator` storage variable wired once post-deployment via the new one-shot `setCoordinator()` (`onlyOwner`, guarded by the new `CoordinatorAlreadySet` error, emits the new `CoordinatorSet` event).
- The custom `onlyOwner` modifier (backed by `OWNER`) was removed; `mint` is now gated by `onlyCoordinator`. The name `onlyOwner` now refers to the OZ owner — a different role.
- Added `uint256[50] __gap` storage reserve.
- Unchanged: `mint` body (zero-address guard, `_mint`, `TokensMinted`), `InvalidAddress`/`Unauthorized` errors.

---

## 15. Review Notes & Open Caveats

- **No. 1 — Two roles now share the "owner" vocabulary:** the OZ `owner()` (deployer, admin) and the `coordinator` (minter) are different parties; older docs/tools that equated "owner" with "minter" must be updated.
- **No. 2 — Deployment gains a mandatory wiring step:** until `setCoordinator` runs, all minting (and therefore `DinCoordinator.depositAndMint`) reverts. Fails closed, but a skipped step looks like a broken exchange.
- **No. 3 — "Set once, forever" is implementation-level only:** the one-shot guard can be bypassed by a ProxyAdmin-authorized upgrade that resets `coordinator`, so the immutability guarantee is bounded by upgrade-key security (see §9).
- **No. 4 — Owner role outlives its purpose:** after wiring, `owner()` has no remaining function but stays transferable; consider renouncing or transferring to the DAO multisig as a deliberate post-deployment decision.
