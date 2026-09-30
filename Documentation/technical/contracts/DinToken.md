# DinToken — Technical Documentation

> **File:** [`foundry/src/DinToken.sol`](../../../foundry/src/DinToken.sol)
> **SPDX-License-Identifier:** MIT
> **Solidity:** `^0.8.28`
> **Standard:** ERC-20 (OpenZeppelin upgradeable)

---

## 1. Overview

`DinToken` is the native utility token of the DIN Protocol ecosystem. It is a minimal ERC-20 contract deployed **behind an OpenZeppelin Transparent Proxy**, whose minting authority is bound to a single address — the `DinCoordinator` proxy — wired once after deployment via the one-shot `setCoordinator()`. Any holder can burn their own tokens via `burn()`. The token carries 18 decimal places (inherited from OpenZeppelin's `ERC20Upgradeable`).

The token serves as the staking, slashing and reward currency: validators acquire DIN tokens through `DinCoordinator.depositAndMint()` (the ETH faucet) and lock them in `DinValidatorStake`; new DIN also enters circulation as the per-GI emission subsidy via `DinCoordinator.mintEmission()`, called by `DinEmission`.

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
| `TokensBurned` | `address indexed from`, `uint256 amount` | Every successful `burn()` call, in addition to the inherited ERC-20 `Transfer(from, address(0), amount)` event. |
| `CoordinatorSet` | `address indexed coordinator` | The one-shot `setCoordinator()` wiring call. |

---

## 6. Access Control

Two contract-level roles, plus the proxy-level admin:

```
owner() — OwnableUpgradeable; set to the account that ran initialize (deployer)
  └── setCoordinator()        ← one-shot wiring, reverts once coordinator != 0

coordinator — the DinCoordinator proxy, wired via setCoordinator()
  └── mint()                  ← guarded by onlyCoordinator

any holder
  └── burn()                  ← burns msg.sender's own balance; no extra access control

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
- Calls `_disableInitializers()`, so the implementation itself can never be initialized — a direct `initialize()` on it reverts with `InvalidInitialization` (covered by `ReInitializerProtectionTest` in `foundry/test/DeployPlatform.t.sol`).

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

Called only by `DinCoordinator`, from two paths:
- `depositAndMint()` — the ETH→DIN faucet.
- `mintEmission()` — the per-GI emission subsidy, callable only by the wired `DinEmission` contract.

Both paths go through the coordinator's `faucetRetired` / `mintCap` / `totalMinted` checks before calling `mint` (see [DinCoordinator.md](DinCoordinator.md)).

---

### 7.4 `burn`

```solidity
function burn(uint256 amount) external
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `amount` | `uint256` | Number of the caller's own tokens to destroy. |

**Algorithm:**
1. Calls OpenZeppelin's internal `_burn(msg.sender, amount)`, which reverts with `ERC20InsufficientBalance` if the caller holds less than `amount`, decrements `balanceOf[msg.sender]` and `totalSupply`, and emits `Transfer(msg.sender, address(0), amount)`.
2. Emits `TokensBurned(msg.sender, amount)`.

No extra access control — the same trust model as `transfer`: a holder can only destroy their own balance. In the protocol it is called by `DinFeeRouter` on its own balance, after pulling DIN fees via `transferFrom`, for the burn share of its DIN split (`burnBps`, 0% by default). ETH is never burned.

---

## 8. Token Economics

| Property | Value |
|----------|-------|
| Name | `DIN Token` |
| Symbol | `DIN` |
| Decimals | `18` |
| Initial Supply | `0` (no pre-mint) |
| Minting Authority | `DinCoordinator` proxy (one-shot `setCoordinator`) |
| Burning | Holder-initiated `burn()` (used by `DinFeeRouter` for its DIN burn share) |
| Supply cap | None in the token; enforced upstream by `DinCoordinator.mintCap` (0 = uncapped) |

**Minting rate:** Faucet mints are defined by `DinCoordinator.dinPerEth` (default `1,000,000 DIN per 1 ETH`, i.e. 1 ETH → 1M × 10¹⁸ raw token units). Emission mints follow the `DinEmission` schedule.

---

## 9. Ownership & Upgradeability

| Plane | Who | Controls |
|-------|-----|----------|
| Contract owner (`owner()`) | Account that ran `initialize` (deployer) | `setCoordinator` (one-shot); transferable via `transferOwnership` |
| Minter (`coordinator`) | `DinCoordinator` proxy | `mint` only |
| Proxy admin (`ProxyAdmin`) | Deployed by the OZ upgrades plugin, owned by the deployer | Swapping the implementation |

- **Proxy kind:** OpenZeppelin Transparent Proxy; the token address that balances live at is permanent, only code changes on upgrade.
- **Upgrade path:** `cd foundry && CONTRACT=DinToken forge script script/UpgradePlatform.s.sol --rpc-url <rpc> --broadcast ...` (reads the proxy address from `foundry/deployments/<network>.json`; see [UpgradePlatform](foundry/script/UpgradePlatform.md)).
- **Storage-layout safety:** the `__gap` array reserves 50 slots; ERC-20 balances live in OZ's namespaced (ERC-7201) storage. `foundry/test/UpgradeValidation.t.sol` runs `Upgrades.validateImplementation`, and `DinTokenUpgradeTest` in `foundry/test/DeployPlatform.t.sol` upgrades to `foundry/src/upgrade/DinTokenV2.sol` (`Upgrades.upgradeProxy` validates first) and checks that balances, coordinator wiring and access control survive.
- **Trust implication:** the "coordinator can never change" guarantee is enforced at the *implementation* level. A ProxyAdmin-authorized upgrade could replace that rule (or the entire token logic), so the guarantee is ultimately bounded by the security of the ProxyAdmin owner key.

---

## 10. Deployment & Post-Deploy Wiring

From `foundry/script/DeployPlatform.s.sol` (see [DeployPlatform](foundry/script/DeployPlatform.md)): the token is deployed right after `DinTreasury`, before everything that references it.

```
1. Deploy DinTreasury proxy
2. Deploy DinToken proxy          → initialize()            (owner = deployer, no minter yet)
3. Deploy DinFeeRouter proxy      → initialize(dinToken, dinTreasury)
4. Deploy DinCoordinator proxy    → initialize(dinToken)
5. dinToken.setCoordinator(dinCoordinator)                  ← minting goes live here
```

Between steps 2 and 5 every `mint()` reverts with `Unauthorized()` — including `DinCoordinator.depositAndMint()` — so a half-wired deployment cannot mint. Because `setCoordinator` is one-shot, an attacker who somehow raced step 5 would permanently brick minting rather than gain it (and the call is `onlyOwner` anyway).

---

## 11. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Unlimited minting | `coordinator` can be set exactly once (`CoordinatorAlreadySet` guard); only the `DinCoordinator` proxy can mint. |
| Minting before wiring | `coordinator` defaults to `address(0)`; `mint` fails closed. |
| Minting to zero address | Explicit `InvalidAddress()` guard before `_mint`. |
| Re-entrancy | N/A — no ETH is transferred; pure ERC-20 state update. |
| Burning others' tokens | `burn` only destroys `msg.sender`'s balance; no `burnFrom`. |
| Owner abuse | `owner()` cannot mint; its only power is the one-shot `setCoordinator` (spent at deployment) — though it persists as a role via `transferOwnership`. |
| Re-initialization / implementation hijack | `initializer` modifier + `_disableInitializers()` in the constructor. |
| Malicious upgrade | Governed by ProxyAdmin ownership; no timelock — see §9. |

---

## 12. Interactions with Other Contracts

```
Deploy script (foundry/script/DeployPlatform.s.sol)
  ├── deploys DinToken proxy (after DinTreasury)
  └── wires DinToken.setCoordinator(dinCoordinator) after the coordinator exists

DinCoordinator
  ├── calls DinToken.mint(user, amount) on every depositAndMint()
  └── calls DinToken.mint(to, amount) on every mintEmission() (from DinEmission)

DinFeeRouter
  └── calls DinToken.burn(amount) on its own balance for the DIN burn share

DinValidatorStake / DINTaskAuditor / DINTaskCoordinator / DinTreasury
  └── hold and move DIN (stakes, reward pools, slashed stake) via ERC-20 transfer/transferFrom
```

---

## 13. Known Limitations & Future Work

- No `pause` or emergency stop mechanism.
- No supply cap in the token itself; the cap lives in `DinCoordinator.mintCap` (0 = uncapped on DevNet).
- Minting authority cannot be re-pointed at the contract level (one-shot `setCoordinator`); moving it would require an implementation upgrade or a new token proxy.
- The OZ owner role persists after its single job (`setCoordinator`) is done; renouncing it post-deployment would remove that surface but also forfeit any future admin hooks an upgrade might add.

---

## 14. Change Log

### P3 — burn support (foundry)

- Added holder-initiated `burn(uint256)` and the `TokensBurned` event, used by `DinFeeRouter` for the DIN burn share.
- Mint callers grew a second path: `DinCoordinator.mintEmission()` (from `DinEmission`), in addition to `depositAndMint()`.

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
- **No. 4 — Owner role outlives its purpose:** after wiring, `owner()` has no remaining function but stays transferable; consider renouncing or transferring it as a deliberate post-deployment decision (on-chain DIN-DAO governance is deferred to post-mainnet).
