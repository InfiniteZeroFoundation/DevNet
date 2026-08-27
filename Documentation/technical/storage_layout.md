# Storage Layout — DIN Platform Contracts

This document covers the storage layout rules and variable inventory for the four
upgradeable platform contracts. All four follow the OpenZeppelin Transparent Proxy
pattern (`Initializable`, `OwnableUpgradeable`) and carry a `uint256[50] private __gap`
reservation at each inheritance level to allow safe future additions.

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

**Inherited slots are fixed.** Slots occupied by OpenZeppelin base contracts
(`_initialized`, `_owner`, etc.) are determined by their upstream storage layout and
must not be touched.

**`ReentrancyGuardTransient` is slot-neutral.** `DinCoordinator` and
`DinValidatorStake` inherit from `ReentrancyGuardTransient`, which stores its lock in
EIP-1153 transient storage (cleared each transaction). It contributes zero persistent
storage slots.

---

## DinToken

```
[Initializable]
  _initialized      : uint64  (packed with _initializing bool)
[OwnableUpgradeable]
  _owner            : address
[ERC20Upgradeable]
  _balances         : mapping(address => uint256)
  _allowances       : mapping(address => mapping(address => uint256))
  _totalSupply      : uint256
  _name             : string
  _symbol           : string
─────────────────────────────────── contract-own slots ───
  coordinator       : address
  __gap             : uint256[50]   ← 50 reserved slots
```

`setCoordinator` is one-shot; `coordinator` will not change after initial wiring.
Future variables must be inserted above `__gap`, reducing its size accordingly.

---

## DinCoordinator

```
[Initializable]
  _initialized      : uint64
[OwnableUpgradeable]
  _owner            : address
─────────────────────────────────── contract-own slots ───
  dinToken                    : address   (DinToken proxy)
  dinValidatorStakeContract   : address   (IDinValidatorStake)
  dinPerEth                   : uint256   (exchange rate, 1e18-scaled)
  treasury                    : address   (fee-router destination for withdraw())
  __gap                       : uint256[50]
```

`dinValidatorStakeContract` is written once by `updateValidatorStakeContract`.
`dinPerEth` is mutable via `updateDinPerEth`. `treasury` is mutable via `setTreasury`;
`withdraw()` reverts with `TreasuryNotSet` until it's set. `__gap` stays at `[50]`
rather than shrinking — see "Core rules" above for why that's fine pre-deployment.

---

## DinValidatorStake

```
[Initializable]
  _initialized      : uint64
[OwnableUpgradeable]
  _owner            : address
─────────────────────────────────── contract-own slots ───
  DIN_TOKEN           : IERC20   (immutable after initialize)
  DIN_COORDINATOR     : address  (immutable after initialize)
  slasherContracts    : mapping(address => bool)
  validators          : mapping(address => ValidatorInfo)
  __gap               : uint256[50]
```

`ValidatorInfo` is a struct packed into a single mapping entry; its internal layout
does not affect the contract's top-level slot numbering.

---

## DINModelRegistry

```
[Initializable]
  _initialized      : uint64
[OwnableUpgradeable]
  _owner            : address
─────────────────────────────────── contract-own slots ───
  daoAdmin            : address
  modelCount          : uint256
  models              : mapping(uint256 => Model)
  modelIdByCoordinator: mapping(address => uint256)
  modelIdByAuditor    : mapping(address => uint256)
  proprietaryFee      : uint256
  pendingModels       : mapping(uint256 => PendingModel)
  pendingCount        : uint256
  __gap               : uint256[50]
```

`daoAdmin` exists alongside `_owner` to preserve backward compatibility with
external callers that used the old `daoAdmin()` accessor. `setDAOAdmin` updates
both `daoAdmin` and transfers OZ ownership simultaneously.

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
