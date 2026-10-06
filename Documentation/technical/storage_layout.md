# Storage Layout — DIN Platform Contracts

This document covers the storage layout rules and variable inventory for the eight
upgradeable platform contracts: `DinToken`, `DinCoordinator`, `DinValidatorStake`,
`DINModelRegistry`, `DinEmission`, `DinFeeRouter`, `DinTreasury` and
`DinFairLaunchDistributor`. All follow the OpenZeppelin Transparent Proxy pattern
(`Initializable`, `OwnableUpgradeable`) and end their own block with a
`uint256[50] private __gap` reservation to allow safe future additions. Contract-own slot numbers below are from
`forge inspect <Contract> storageLayout`. OpenZeppelin v5 upgradeable bases
(`Initializable`, `OwnableUpgradeable`, `ERC20Upgradeable`) keep their state in
namespaced ERC-7201 storage, so they do not occupy these sequential slots; they are
listed in brackets for completeness.

---

## Core rules for upgradeable contracts

**Append-only.** Every state variable occupies an absolute storage slot derived from
its declared position in the inheritance chain. Any upgrade that inserts, removes, or
reorders variables corrupts the storage of the live proxy. The only safe operation is
appending new variables at the end of a contract's own block, before the `__gap`.

**Consume gap slots before adding post-gap variables — once a proxy is live.** When a
new state variable is needed on a contract that already has a deployed proxy, shrink
`__gap` by the number of slots required and place the new variable immediately above
`__gap`. Never add variables after `__gap`. Nothing on `develop` is live on Sepolia
yet, so this repo currently adds new variables above `__gap` without shrinking it —
there's no deployed slot layout to preserve. Start shrinking `__gap` per addition as
soon as a proxy is actually deployed and holds state worth preserving.

**Inherited storage is namespaced.** OpenZeppelin v5 upgradeable bases
(`_initialized`, `_owner`, ERC-20 balances, etc.) live at ERC-7201 namespaced
locations determined upstream, not in the contract's sequential slots. They must not
be touched, and they do not shift when contract-own variables are added.

**`ReentrancyGuardTransient` is slot-neutral.** `DinCoordinator`,
`DinValidatorStake`, `DinEmission`, `DinFeeRouter`, `DinTreasury`,
`DinFairLaunchDistributor`, and `DINModelRegistry` (added for the
`requestModelRegistration` / `requestManifestUpdate` overpayment refunds, L-3)
inherit from `ReentrancyGuardTransient`, which stores its lock in EIP-1153
transient storage (cleared each transaction). It contributes zero persistent
storage slots.

---

## DinToken

```
[Initializable]            (ERC-7201 namespaced)
[ERC20Upgradeable]         (ERC-7201 namespaced: balances, allowances, totalSupply, name, symbol)
[OwnableUpgradeable]       (ERC-7201 namespaced: _owner)
─────────────────────────────────── contract-own slots ───
  coordinator       : address                                slot 0
  __gap             : uint256[50]                            slots 1–50
```

`setCoordinator` is one-shot; `coordinator` will not change after initial wiring.

---

## DinCoordinator

```
[Initializable] [OwnableUpgradeable]   (ERC-7201 namespaced)
─────────────────────────────────── contract-own slots ───
  dinToken                    : DinToken             (slot 0)
  dinValidatorStakeContract   : IDinValidatorStake   (slot 1)
  dinPerEth                   : uint256              (slot 2, exchange rate, 1e18-scaled)
  faucetRetired               : bool                 (slot 3)
  mintCap                     : uint256              (slot 4, 0 = uncapped)
  totalMinted                 : uint256              (slot 5)
  feeRouter                   : IDinFeeRouter        (slot 6)
  emissionContract            : address              (slot 7)
  __gap                       : uint256[50]          (slot 8)
```

`dinValidatorStakeContract` is set by `updateValidatorStakeContract`, `dinPerEth` by
`updateDinPerEth`, `mintCap` by `setMintCap`, `feeRouter` by `setFeeRouter` and
`emissionContract` by `setEmissionContract`. `faucetRetired` is flipped one-way by
`retireFaucet`. `__gap` stays at `[50]` rather than shrinking — see "Core rules"
above for why that's fine pre-deployment.

---

## DinValidatorStake

```
[Initializable] [OwnableUpgradeable]   (ERC-7201 namespaced)
─────────────────────────────────── contract-own slots ───
  DIN_TOKEN                              : IERC20                                   (slot 0)
  DIN_COORDINATOR                        : address                                  (slot 1)
  MIN_STAKE                              : uint256                                  (slot 2)
  UNBONDING_PERIOD                       : uint64                                   (slot 3)
  slasherContracts                       : mapping(address => bool)                 (slot 4)
  validators                             : mapping(address => ValidatorInfo)        (slot 5)
  modelMinStakeBounds                    : mapping(uint256 => ModelStakeBounds)     (slot 6)
  maxConcurrentRegistrationsPerStakeUnit : uint256                                  (slot 7)
  slashTreasury                          : address                                  (slot 8)
  encryptionKeys                         : mapping(address => bytes)                (slot 9)
  activeRegistrationCount                : mapping(address => uint256)              (slot 10)
  s5RecidivismWindow                     : uint256                                  (slot 11)
  s5RecidivismThreshold                  : uint256                                  (slot 12)
  s5JailDuration                         : uint256                                  (slot 13)
  _partialSlashGIs                       : mapping(address => mapping(address => uint256[]))  (slot 14)
  s6NoParticipationThreshold             : uint256                                  (slot 15)
  s6NoParticipationCount                 : mapping(address => uint256)              (slot 16)
  __gap                                  : uint256[50]                              (slot 17)
```

`DIN_TOKEN` / `DIN_COORDINATOR` are set once in `initialize` (upper-case names, but
ordinary storage, not `immutable`). `MIN_STAKE` and `UNBONDING_PERIOD` are initialised
to `10 DIN` / `7 days` and owner-settable (`setMinStake`, `setUnbondingPeriod`), as are
`modelMinStakeBounds`, `maxConcurrentRegistrationsPerStakeUnit` and `slashTreasury`.
`UNBONDING_PERIOD` is a `uint64` but still takes a full slot: the next variable is a
mapping, which always starts a new slot. `ValidatorInfo` / `ModelStakeBounds` are
structs stored inside mapping entries; their internal layout does not affect the
contract's top-level slot numbering.

---

## DINModelRegistry

```
[Initializable] [OwnableUpgradeable]   (ERC-7201 namespaced)
[ReentrancyGuardTransient]
  (transient lock only — no persistent slot)
─────────────────────────────────── contract-own slots ───
  dinValidatorStake        : IDinValidatorStake        (slot 0)
  openSourceFee            : uint256                   (slot 1)
  proprietaryFee           : uint256                   (slot 2)
  openSourceUpdateFee      : uint256                   (slot 3)
  proprietaryUpdateFee     : uint256                   (slot 4)
  models                   : Model[]                   (slot 5)
  modelRequests            : ModelRequest[]            (slot 6)
  manifestRequests         : ManifestUpdateRequest[]   (slot 7)
  _modelIdByTaskCoordinator: mapping(address => uint256)  (slot 8)
  _modelIdByTaskAuditor    : mapping(address => uint256)  (slot 9)
  modelDisabled            : mapping(uint256 => bool)     (slot 10)
  feeRouter                : IDinFeeRouter             (slot 11)
  __gap                    : uint256[50]               (slot 12)
```

Contract-own slot numbers are from `forge inspect DINModelRegistry storageLayout`.
Ownership is plain `OwnableUpgradeable` — there is no separate `daoAdmin` slot.
`_modelIdByTaskCoordinator` / `_modelIdByTaskAuditor` store `modelId + 1` so that
`0` means "not registered".

---

## DinEmission

```
[Initializable] [OwnableUpgradeable]   (ERC-7201 namespaced)
[ReentrancyGuardTransient]
  (transient lock only — no persistent slot)
─────────────────────────────────── contract-own slots ───
  coordinator          : IDinCoordinator                                (slot 0)
  dinToken             : IERC20                                         (slot 1)
  initialEmissionPerGI : uint256                                        (slot 2)
  decayBps             : uint256                                        (slot 3)
  epochLength          : uint256                                        (slot 4)
  maxEpochs            : uint256                                        (slot 5)
  emissionState        : mapping(address => EmissionState)              (slot 6)
  totalEmitted         : uint256                                        (slot 7)
  giEmissionFunded     : mapping(address => mapping(uint256 => bool))   (slot 8)
  modelRegistry        : IDINModelRegistry                              (slot 9, issue #226)
  __gap                : uint256[49]                                    (slot 10 — shrunk from 50 to
                                                                           49 when modelRegistry was
                                                                           appended; total slot count
                                                                           unchanged, safe for the
                                                                           Transparent Proxy)
```

---

## DinFeeRouter

```
[Initializable] [OwnableUpgradeable]   (ERC-7201 namespaced)
[ReentrancyGuardTransient]
  (transient lock only — no persistent slot)
─────────────────────────────────── contract-own slots ───
  dinToken           : IBurnableERC20                (slot 0)
  treasury           : address                       (slot 1, bytes 0–19)
  treasuryBpsCeiling : uint16                        (slot 1, bytes 20–21 — packed with treasury)
  feeSources         : mapping(address => bool)      (slot 2)
  dinSplit           : DinSplit                      (slot 3 — 5 × uint16, one slot)
  ethSplit           : EthSplit                      (slot 4 — 4 × uint16, one slot)
  accruedDin         : mapping(bytes32 => uint256)   (slot 5)
  accruedEth         : mapping(bytes32 => uint256)   (slot 6)
  __gap              : uint256[50]                   (slot 7)
```

`treasury` and `treasuryBpsCeiling` share slot 1, and each split struct fits in a
single slot. Adding a field to `DinSplit`/`EthSplit` can still fit in that slot (up
to 16 × `uint16`), but inserting a variable between `treasury` and
`treasuryBpsCeiling`, or widening either, changes the packing — treat slot 1 as fixed.

---

## DinTreasury

```
[Initializable] [OwnableUpgradeable]   (ERC-7201 namespaced)
[ReentrancyGuardTransient]
  (transient lock only — no persistent slot)
─────────────────────────────────── contract-own slots ───
  __gap              : uint256[50]   (slot 0)
```

`DinTreasury` holds ETH/ERC20 balances only; it has no contract-own state yet, so the
whole block is reserved.

---

## DinFairLaunchDistributor

```
[Initializable] [OwnableUpgradeable]   (ERC-7201 namespaced)
[ReentrancyGuardTransient]
  (transient lock only — no persistent slot)
─────────────────────────────────── contract-own slots ───
  dinToken              : IERC20                               (slot 0)
  merkleRoot            : bytes32                              (slot 1)
  claimsOpen            : bool                                 (slot 2, byte 0)
  cliffDuration         : uint64                               (slot 2, bytes 1–8)
  vestingDuration       : uint64                               (slot 2, bytes 9–16)
  vestingStart          : uint64                               (slot 2, bytes 17–24)
  totalFunded           : uint256                              (slot 3)
  totalClaimedPrincipal : uint256                              (slot 4)
  positions             : mapping(address => VestingPosition)  (slot 5)
  hasClaimed            : mapping(address => bool)             (slot 6)
  __gap                 : uint256[50]                          (slot 7)
```

`claimsOpen` and the three `uint64` vesting fields pack into slot 2.

---

## Upgrade checklist

Before deploying an implementation upgrade to a proxy:

1. Run `forge inspect <Contract> storage-layout` on both the old and new
   implementation and diff the output. No existing variable should change slot,
   type, or size.
2. Any new variable must appear above `__gap` with `__gap` shrunk by the
   corresponding number of slots.
3. Structs used in mappings may gain new fields only if they are appended at the
   end of the struct definition and the mapping is not iterated in a way that
   assumes fixed struct size.
4. Confirm `_disableInitializers()` remains in the implementation constructor.
5. Run `openzeppelin-foundry-upgrades` `validateUpgrade` against the live proxy
   address before executing the upgrade on-chain.
