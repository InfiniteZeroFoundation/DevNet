# DinCoordinator — Technical Documentation

> **File:** `hardhat/contracts/DinCoordinator.sol`
> **SPDX-License-Identifier:** UNLICENSED
> **Solidity:** `^0.8.28`

---

## 1. Overview

`DinCoordinator` is the **entry-point and treasury contract** for the DIN Protocol. Its two core responsibilities are:

1. **Token issuance** — Accept ETH deposits from users and mint an equivalent amount of DIN tokens into their wallets.
2. **Slasher management** — Act as the privileged caller that can register or de-register slasher contracts on `DinValidatorStake` on behalf of the DAO representative.

At deployment, `DinCoordinator` itself deploys `DinToken` and becomes its immutable minting authority.



---

## 2. Inheritance & Dependencies

| Component | Source | Purpose |
|-----------|--------|---------|
| `Ownable` | OpenZeppelin | DAO admin access control |
| `ReentrancyGuardTransient` | OpenZeppelin (L2-optimized) | Prevents re-entrancy on ETH flows |
| `DinToken` | Local | Deployed inline at construction |
| `IDinValidatorStake` (local interface) | Local | Typed calls to `DinValidatorStake` |

`ReentrancyGuardTransient` is the L2-optimised variant that uses transient storage (EIP-1153), reducing gas cost for the re-entrancy lock on L2 networks.

---

## 3. State Variables

| Variable | Type | Visibility | Description |
|----------|------|-----------|-------------|
| `dinToken` | `DinToken` | `public immutable` | The DIN ERC-20 token, deployed by this contract in the constructor. |
| `dinValidatorStakeContract` | `IDinValidatorStake` | `public` | Mutable reference to the validator staking contract. Set after deployment via `updateValidatorStakeContract`. |
| `dinPerEth` | `uint256` | `public` | Exchange rate: how many raw DIN tokens (18-decimal units) are minted per 1 ETH wei. Default: `1,000,000 × 10¹⁸` (i.e., 1M DIN per ETH). |

---

## 4. Custom Errors

| Error | Condition |
|-------|-----------|
| `InvalidAddress()` | Zero-address provided to an address parameter |
| `ValidatorStakeContractNotSet()` | Slasher management called before `dinValidatorStakeContract` is configured |
| `ZeroValue()` | ETH deposit of zero value, or exchange rate update to zero |
| `TransferFailed()` | Low-level ETH transfer from `withdraw()` reverted |

---

## 5. Events

| Event | Parameters | Emitted When |
|-------|-----------|--------------|
| `EthDepositAndDINminted` | `address indexed user`, `uint256 ethAmount`, `uint256 mintAmount` | Successful `depositAndMint()` |
| `SlasherContractAdded` | `address indexed slasher` | Slasher registered on validator stake contract |
| `SlasherContractRemoved` | `address indexed slasher` | Slasher de-registered |
| `ValidatorStakeContractUpdated` | `address indexed validatorStakeContract` | Stake contract reference updated |
| `DinPerEthUpdated` | `uint256 newRate` | Exchange rate changed |

---

## 6. Access Control

```
Ownable (DAO representative / deployer)
  ├── withdraw()
  ├── addSlasherContract()
  ├── removeSlasherContract()
  ├── updateValidatorStakeContract()
  └── updateDinPerEth()

Any address (permissionless)
  └── depositAndMint()   ← payable, guarded by nonReentrant
```

---

## 7. Functions

### 7.1 Constructor

```solidity
constructor() Ownable(msg.sender)
```

- Deploys a new `DinToken` contract passing `address(this)` as the minting authority.
- `dinToken` is set once and becomes immutable.
- `dinPerEth` initialized to `1_000_000 * 1e18`.

---

### 7.2 `depositAndMint` — Token Issuance Mechanism

```solidity
function depositAndMint() external payable nonReentrant
```

**Purpose:** Converts ETH to DIN tokens at the current exchange rate.

**Algorithm:**
1. Revert with `ZeroValue()` if `msg.value == 0`.
2. Compute `mintAmount`:
   ```
   mintAmount = (msg.value × dinPerEth) / 10¹⁸
   ```
   - This performs safe decimal math: `dinPerEth` is stored as a 10¹⁸-scaled value, so dividing by 10¹⁸ correctly normalises the result.
   - Example: `msg.value = 1 ETH (10¹⁸ wei)` → `mintAmount = (10¹⁸ × 1_000_000 × 10¹⁸) / 10¹⁸ = 1_000_000 × 10¹⁸ raw DIN units`.
3. Call `dinToken.mint(msg.sender, mintAmount)`.
4. Emit `EthDepositAndDINminted`.

**Re-entrancy protection:** `nonReentrant` using transient storage. The ETH remains in the contract's balance until `withdraw()` is called.

---

### 7.3 `withdraw`

```solidity
function withdraw() external onlyOwner nonReentrant
```

Transfers the full ETH balance to the `owner()`. Silent no-op if balance is zero. Uses a low-level `.call` for ETH transfer; reverts with `TransferFailed()` if the call fails.

---

### 7.4 `addSlasherContract`

```solidity
function addSlasherContract(address slasherContract) external onlyOwner
```

Delegates to `dinValidatorStakeContract.addSlasherContract(slasherContract)`. Enforces:
- `slasherContract != address(0)`.
- `dinValidatorStakeContract` is set.

Used by the DAO representative to authorise `DINTaskCoordinator` and `DINTaskAuditor` contracts to call `slash()` on validators.

---

### 7.5 `removeSlasherContract`

```solidity
function removeSlasherContract(address slasherContract) external onlyOwner
```

Symmetric reverse of `addSlasherContract`. Delegates to `dinValidatorStakeContract.removeSlasherContract(slasherContract)`.

---

### 7.6 `updateValidatorStakeContract`

```solidity
function updateValidatorStakeContract(address validatorStakeContract) external onlyOwner
```

Updates the mutable `dinValidatorStakeContract` reference. Intended to be called once after `DinValidatorStake` is deployed. Reverts on zero address.

---

### 7.7 `updateDinPerEth`

```solidity
function updateDinPerEth(uint256 newRate) external onlyOwner
```

Updates the ETH→DIN exchange rate. Reverts on zero. Emits `DinPerEthUpdated`.

---

## 8. Token Issuance Economics

| Parameter | Default Value | Description |
|-----------|--------------|-------------|
| `dinPerEth` | `1,000,000 × 10¹⁸` | Raw DIN units minted per 1 ETH wei |
| Effective rate | 1 ETH → 1,000,000 DIN | Adjustable by DAO admin |

The ETH collected accumulates in this contract and is withdrawable by `owner()` at any time.

---

## 9. Deployment & Initialization Sequence

```
1. Deploy DinCoordinator
   └── DinToken is deployed automatically (DinCoordinator becomes its OWNER)

2. Deploy DinValidatorStake (requires dinToken address and DinCoordinator address)
   └── owner should be the DIN admin / DAO representative, or ownership should be transferred immediately after deployment

3. Call DinCoordinator.updateValidatorStakeContract(dinValidatorStakeAddress)

4. (Later) Call DinCoordinator.addSlasherContract(taskCoordinatorAddress)
   Call DinCoordinator.addSlasherContract(taskAuditorAddress)
```

---

## 10. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Re-entrancy via ETH deposit | `ReentrancyGuardTransient` on `depositAndMint` and `withdraw` |
| Rogue slasher registration | `onlyOwner` on add/remove slasher functions |
| Exchange rate manipulation | Only `owner` can update `dinPerEth` |
| ETH locked | `withdraw()` allows owner to drain contract at any time |

---

## 11. Interactions with Other Contracts

```
DinCoordinator
  ├── deploys → DinToken
  ├── calls   → DinToken.mint(user, amount)       [on depositAndMint]
  ├── calls   → DinValidatorStake.addSlasherContract()
  └── calls   → DinValidatorStake.removeSlasherContract()


```
