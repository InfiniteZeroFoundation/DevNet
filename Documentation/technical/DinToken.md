# DinToken — Technical Documentation

> **File:** `hardhat/contracts/DinToken.sol`
> **SPDX-License-Identifier:** MIT
> **Solidity:** `^0.8.19`
> **Standard:** ERC-20 (OpenZeppelin)

---

## 1. Overview

`DinToken` is the native utility token of the DIN Protocol ecosystem. It is a minimal ERC-20 contract whose minting authority is permanently bound to a single, immutable address (the `DinCoordinator`) set at deployment. The token carries 18 decimal places (inherited from OpenZeppelin's `ERC20`).

The token serves as the staking and slashing currency: validators acquire DIN tokens through `DinCoordinator.depositAndMint()`, then lock them in `DinValidatorStake` to participate in the network.

---

## 2. Inheritance & Dependencies

| Component | Source |
|-----------|--------|
| `ERC20` | OpenZeppelin `@openzeppelin/contracts/token/ERC20/ERC20.sol` |
| `Ownable` | OpenZeppelin `@openzeppelin/contracts/access/Ownable.sol` *(imported but not used in inheritance — the contract uses a custom immutable `OWNER` pattern instead)* |

> **Note:** The contract inherits from `ERC20` only. It does **not** inherit `Ownable`; instead it defines its own `onlyOwner` modifier backed by the `OWNER` immutable.

---

## 3. State Variables

| Variable | Type | Visibility | Description |
|----------|------|-----------|-------------|
| `OWNER` | `address` | `public immutable` | Permanently set to the deploying address (expected to be `DinCoordinator`). Cannot be changed after deployment. |

All token balances, allowances, total supply, name (`"DIN Token"`), and symbol (`"DIN"`) are managed by the inherited `ERC20` base.

---

## 4. Custom Errors

| Error | Condition |
|-------|-----------|
| `InvalidAddress()` | `to == address(0)` on a mint call |
| `Unauthorized()` | Caller is not `OWNER` |

Custom errors are preferred over `require` strings for gas efficiency.

---

## 5. Events

| Event | Parameters | Emitted When |
|-------|-----------|--------------|
| `TokensMinted` | `address indexed to`, `uint256 amount` | Every successful `mint()` call, in addition to the inherited ERC-20 `Transfer` event. |

---

## 6. Access Control

The contract uses a single-role, immutable-owner pattern:

```
OWNER (immutable, set once at constructor)
  └── can call mint()
```

The `onlyOwner` modifier reads directly from the `OWNER` immutable slot (no `SLOAD` of a mutable owner variable), making it maximally gas-efficient.

```solidity
modifier onlyOwner() {
    if (msg.sender != OWNER) revert Unauthorized();
    _;
}
```

---

## 7. Functions

### 7.1 Constructor

```solidity
constructor(address owner_) ERC20("DIN Token", "DIN")
```

| Parameter | Description |
|-----------|-------------|
| `owner_` | The address that will have exclusive minting rights. In production this must be the `DinCoordinator` contract address. |

- Sets `OWNER = owner_`.
- Calls `ERC20("DIN Token", "DIN")` to initialize token metadata.
- No initial supply is minted.

---

### 7.2 `mint`

```solidity
function mint(address to, uint256 amount) external onlyOwner
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `to` | `address` | Recipient of newly minted tokens. |
| `amount` | `uint256` | Number of tokens to mint (18-decimal representation). |

**Algorithm:**
1. Guard: `onlyOwner` — reverts with `Unauthorized()` if `msg.sender != OWNER`.
2. Guard: reverts with `InvalidAddress()` if `to == address(0)`.
3. Calls OpenZeppelin's internal `_mint(to, amount)`, which:
   - Increments `totalSupply` by `amount`.
   - Increments `balanceOf[to]` by `amount`.
   - Emits `Transfer(address(0), to, amount)`.
4. Emits `TokensMinted(to, amount)` for off-chain indexing.

**Gas considerations:** No storage reads for ownership check (immutable slot). SafeERC20 is not required here since the token is the issuing contract itself.

---

## 8. Token Economics

| Property | Value |
|----------|-------|
| Name | `DIN Token` |
| Symbol | `DIN` |
| Decimals | `18` |
| Initial Supply | `0` (no pre-mint) |
| Minting Authority | `DinCoordinator` contract (immutable) |
| Burning | Not implemented |

**Minting rate:** Defined entirely by `DinCoordinator.dinPerEth`. Default is `1,000,000 DIN per 1 ETH` (i.e., 1 ETH → 1M × 10¹⁸ raw token units).

---

## 9. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Unlimited minting | `OWNER` is immutable and set once; only `DinCoordinator` can mint. |
| Minting to zero address | Explicit `InvalidAddress()` guard before `_mint`. |
| Re-entrancy | N/A — no ETH is transferred; pure ERC-20 state update. |
| Ownership transfer | Not possible — `OWNER` is immutable. |

---

## 10. Interactions with Other Contracts

```
DinCoordinator
  ├── deploys DinToken (passing its own address as owner_)
  └── calls DinToken.mint(user, amount) on every depositAndMint()

DinValidatorStake
  └── holds DIN tokens on behalf of stakers (via ERC-20 transferFrom)
```

---

## 11. Known Limitations & Future Work

- No `burn` function — slashed tokens stay locked in `DinValidatorStake` with no on-chain destruction (see `TODO` in `DinValidatorStake.sol`).
- No `pause` or emergency stop mechanism.
- Minting authority cannot be transferred without redeploying the token.
