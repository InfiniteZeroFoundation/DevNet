# helpers.ts — Deploy Helper Documentation

> **File:** `hardhat/deploy/helpers.ts`
> **Role:** shared proxy-deployment, upgrade, and address-persistence utilities

---

## 1. Purpose

Thin, typed wrappers around the OpenZeppelin Hardhat Upgrades plugin plus JSON persistence for deployed addresses. Used by both production scripts (`scripts/deploy-platform.ts`, `scripts/upgrade-platform.ts`) and every test suite — a single code path for proxy handling everywhere.

---

## 2. Functions

### `deployTransparentProxy(factory, initArgs = [], initializer = "initialize")`

Wraps `upgrades.deployProxy(factory, initArgs, { kind: PROXY_KIND, initializer })` and awaits deployment. `PROXY_KIND` is `"transparent"` from [`constants.ts`](constants.md). The optional `initializer` parameter allows a non-standard initializer name; all current platform contracts use the default `initialize`.

#### The cast: three contracts, not one

One `deployTransparentProxy` call leaves **three** contracts on chain. The
common misconception is that "the proxy" contains the contract's code (the
empty constructor, `initialize`, `OwnableUpgradeable`) — it contains none of
it. All of that lives in the implementation; the proxy only *borrows* the code
via `delegatecall` while keeping all the state:

| Contract | Contains | Stores |
|----------|----------|--------|
| **Implementation** (e.g. `DinToken` at address `I`) | all the logic: `initialize`, `mint`, `owner()`, the empty constructor — everything in `DinToken.sol` | nothing (its own storage is bricked by `_disableInitializers`) |
| **Proxy** (address `P` — the "DinToken address" everyone uses) | almost no code: a fallback that `delegatecall`s, plus ERC-1967 slot handling | all the state: balances, name, `owner`, `coordinator`, the initialized flag |
| **ProxyAdmin** | upgrade plumbing | who may upgrade (`owner()` = deployer) |

The implementation must go first because the proxy cannot exist without it:
`TransparentUpgradeableProxy(address logic, address initialOwner, bytes data)`
takes the implementation address as a constructor argument, and its
constructor immediately `delegatecall`s the encoded `initialize()` — which
requires the logic to already be on chain. Concretely, two transactions:

```
tx 1:  deploy DinToken                → implementation at I
       (constructor runs _disableInitializers — I is a bricked code library)

tx 2:  deploy TransparentUpgradeableProxy(I, deployer, encode(initialize()))
       inside this ONE tx, the proxy constructor:
         a. stores I in its ERC-1967 implementation slot
         b. deploys the ProxyAdmin, stores it in the ERC-1967 admin slot
         c. delegatecalls initialize() → writes "DIN Token", owner=deployer
            into the PROXY's storage
```

The split exists because code at an address is immutable on the EVM. State
must live forever at one stable address (the proxy); code must be replaceable
(disposable implementations). An upgrade is just: deploy `DinTokenV2` at `I2`,
have the ProxyAdmin flip the proxy's implementation slot from `I` to `I2`.
No balances move, no address changes for users.

What one call puts on chain, step by step:

**Step 1 — deploy the implementation (logic) contract.** The plugin deploys the
factory's contract (e.g. `DinToken`) as a plain contract. Its bytecode is what
will eventually execute, but **its own storage will never be used** — every
call will arrive via `delegatecall` from the proxy, which executes the
implementation's code against the *proxy's* storage. If an identical
implementation is already recorded in the `.openzeppelin/` network manifest,
it is reused instead of redeployed.

**Step 2 — why the implementation constructor must stay empty.** A constructor
runs exactly once, at the moment the implementation contract itself is
deployed, and writes to the *implementation's* storage. The proxy is not
involved (it does not even exist yet), so any state a constructor set would be
invisible to the proxy — `delegatecall` reads the proxy's storage, which is
still all zeros. That is why constructor arguments are useless for upgradeable
contracts and all setup moves to `initialize(...)`:

```solidity
/// @custom:oz-upgrades-unsafe-allow constructor
constructor() {
    _disableInitializers();
}

function initialize() external initializer {
    __ERC20_init("DIN Token", "DIN");
    __Ownable_init(msg.sender);
}
```

The only thing the constructor legitimately does is `_disableInitializers()`,
which permanently locks the **bare implementation** so nobody can call
`initialize` directly on it and pose as its owner. The
`@custom:oz-upgrades-unsafe-allow constructor` annotation tells the plugin's
validator this constructor is intentional and safe. (The general rule has one
exception — `immutable` variables live in bytecode, not storage, so they *do*
survive `delegatecall` — but the platform contracts don't use any.)

**Step 3 — `initialize` replaces the constructor, guarded against re-runs.**
`initialize` is an ordinary external function executed *through the proxy*, so
its writes land in the proxy's storage — the storage that actually matters.
Since an ordinary function could be called again, the `initializer` modifier
(from `Initializable`) records in the proxy's storage that initialization has
happened and reverts on any second attempt. Parent contracts are set up by
calling their `__X_init` functions (`__ERC20_init`, `__Ownable_init`) instead
of relying on their constructors, for exactly the same reason.

**Step 4 — deploy the proxy, with initialization in the same transaction.**
The plugin encodes the initializer call (`initArgs` ABI-encoded against the
`initializer` function) and passes it as the `data` argument of the
`TransparentUpgradeableProxy` constructor. The proxy's constructor stores the
implementation address in its ERC-1967 slot and immediately `delegatecall`s
`data` into the implementation. **Deployment and initialization are therefore
atomic** — one transaction, no block in between — so there is no window in
which an attacker could call `initialize` on a deployed-but-uninitialized
proxy and become its owner. Inside that `delegatecall`, `msg.sender` is the
account that sent the deploy transaction, which is how the deployer ends up as
`owner()` via `__Ownable_init(msg.sender)`.

**Step 5 — the ProxyAdmin and the two "owners".** The proxy constructor also
deploys a dedicated **`ProxyAdmin`** contract (OpenZeppelin v5: one per proxy,
not shared) and stores its address in the ERC-1967 *admin* slot. The
transparent pattern routes calls by caller: if `msg.sender` is the admin, the
proxy only accepts `upgradeToAndCall` and never delegates; any other caller is
delegated to the implementation. Making the admin a contract (rather than the
deployer's EOA) means no human address is ever "trapped" on the admin side,
unable to call normal functions. This leaves two independent owners:

| Role | Lives where | Controls |
|------|-------------|----------|
| `ProxyAdmin.owner()` — the deployer | ProxyAdmin contract | upgrades only (`upgradeAndCall`) |
| `owner()` from `OwnableUpgradeable` — also the deployer | proxy storage, set by `initialize` | business functions (`onlyOwner`) |

Same address today, but mechanically independent — transferring one does not
move the other.

**Step 6 — bookkeeping.** Implementation and proxy addresses plus the full
storage layout are recorded in the `.openzeppelin/<network>.json` manifest;
`upgradeTransparentProxy` relies on that layout record later.

### `upgradeTransparentProxy(proxyAddress, factory)`

Wraps `upgrades.upgradeProxy(proxyAddress, factory, { kind: PROXY_KIND })` and awaits deployment. Used by `scripts/upgrade-platform.ts` and all `*.upgrade.test.ts` suites. Step by step:

1. **Storage-layout validation.** The plugin compares the new contract's
   storage layout against the manifest's record for the current
   implementation and refuses the upgrade if existing variables were
   reordered, retyped, or removed (appending, or consuming a `__gap` slot, is
   fine). This protects the state already sitting in the proxy's storage.
2. **Deploy (or reuse) the new implementation.** Its constructor again runs
   `_disableInitializers()` — bricking the bare implementation, exactly as in
   step 2 above.
3. **Point the proxy at it.** The plugin calls
   `ProxyAdmin.upgradeAndCall(proxy, newImpl, "")`. This only succeeds if the
   transaction signer is the **ProxyAdmin's owner** (the deployer) — this is
   the moment the admin/owner distinction from step 5 becomes operational.
4. **No re-initialization.** `initialize` already ran and the `initializer`
   flag lives in the proxy's storage, so it cannot run again after an upgrade
   — all balances, wiring, and `owner()` carry over untouched. If a future
   version needs one-time migration logic, the pattern is a new
   `reinitializer(n)` function passed via `upgradeAndCall`'s data argument;
   nothing in the platform uses that yet.

### Which of the three addresses must be stored?

**Only the proxy address is essential.** It is the contract's identity: the
address users hold tokens at, the address `dincli`/`din_info.json` and every
other integration must point at, and the only address that never changes. The
other two are *derivable from the proxy at any time*, because ERC-1967 pins
them in known storage slots of the proxy:

```ts
await upgrades.erc1967.getImplementationAddress(proxy)  // current logic
await upgrades.erc1967.getAdminAddress(proxy)           // ProxyAdmin
```

So losing the implementation or ProxyAdmin address loses nothing — one
`eth_getStorageAt` recovers them. Losing the proxy address loses everything.

They still have occasional uses, which is why the repo records them as
optional extras in [`PlatformAddresses`](types.md):

- **Implementation address** — needed for block-explorer source verification
  and audits ("what code is this proxy running right now?"). Never call it
  directly: its storage is empty and bricked.
- **ProxyAdmin address** — tells you who can upgrade. You don't need it to
  *perform* an upgrade, though: `upgrades.upgradeProxy` resolves it from the
  proxy's admin slot automatically.

What the scripts actually persist in `deployments/<network>.json`:

- `deploy-platform.ts` saves the **four proxy addresses** (the required
  fields) plus one convenience `proxyAdmin` — read via
  `getProxyAdminAddress(dinTokenAddress)`. Note the OpenZeppelin v5 nuance:
  each proxy has its *own* ProxyAdmin, so this field records DinToken's admin
  only, informationally; the other three proxies' admins are recoverable from
  their own admin slots.
- `upgrade-platform.ts` fills `implementations.<contract>` with the **new**
  implementation address after each upgrade.

**After an upgrade:** the proxy address is unchanged (that is the whole point
— nothing that stored it needs updating), the ProxyAdmin is unchanged, and
only the implementation address is new. The old implementation stays on chain
forever, abandoned — nothing points at it anymore, and being bricked it can't
be misused.

### `deploymentPath(network)`

Returns `hardhat/deployments/<network>.json`.

### `savePlatformAddresses(network, addresses)` / `loadPlatformAddresses(network)`

Write/read the [`PlatformAddresses`](types.md) record. `save` creates `deployments/` if needed and pretty-prints with a trailing newline; `load` throws a descriptive error if the file is missing ("Run the platform deploy script first").

### `getProxyAdminAddress(proxyAddress)`

Reads the ERC-1967 **admin slot** of a proxy via `upgrades.erc1967.getAdminAddress` — returns the ProxyAdmin contract address that holds upgrade rights over that proxy.

---

## 3. Notes

- These helpers deliberately expose *no* raw `deployProxy`/`upgradeProxy` options beyond the initializer name — proxy kind is pinned in one place (`constants.ts`) so a script can't accidentally deploy a UUPS proxy.
- The address JSON in `deployments/` is the tooling's source of truth; the `.openzeppelin/` manifest is the plugin's own bookkeeping (layout history, impl reuse). They serve different purposes and both matter for upgrades.
