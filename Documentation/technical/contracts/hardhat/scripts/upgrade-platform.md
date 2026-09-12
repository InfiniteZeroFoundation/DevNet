# upgrade-platform.ts — Script Documentation

> **File:** `hardhat/scripts/upgrade-platform.ts`
> **Role:** upgrade a single platform proxy to a freshly compiled implementation
> **Run:** `cd hardhat && CONTRACT=<Name> npx hardhat run scripts/upgrade-platform.ts --network <network>`

---

## 1. Purpose

Swaps the implementation behind one platform Transparent Proxy while keeping the proxy address (and all state) unchanged. The contract to upgrade is selected with the `CONTRACT` environment variable; valid names come from `PLATFORM_CONTRACTS` in [`deploy/constants.ts`](../deploy/constants.md):

```
CONTRACT=DinToken | DinCoordinator | DinValidatorStake | DINModelRegistry
```

Example:

```bash
CONTRACT=DinCoordinator npx hardhat run scripts/upgrade-platform.ts --network sepolia_op_devnet
```

---

## 2. What It Does

1. **Validates `CONTRACT`** against `PLATFORM_CONTRACTS` — anything else throws with the list of valid names.
2. **Loads the proxy address** for that contract from `hardhat/deployments/<network>.json` (`loadPlatformAddresses`; throws if the file or the address is missing — run the deploy script first).
3. **Upgrades** via `upgradeTransparentProxy` ([`deploy/helpers.ts`](../deploy/helpers.md)) → `upgrades.upgradeProxy(proxy, factory, { kind: "transparent" })`. The OZ plugin:
   - checks storage-layout compatibility against the recorded layout (aborts on incompatible changes);
   - deploys the new implementation (or reuses an identical one already on-chain);
   - calls the ProxyAdmin to point the proxy at it.
4. **Records the new implementation address** under `implementations.<contract>` in the deployments file and prints proxy + implementation.

---

## 3. Preconditions & Trust

- The signer must be the **ProxyAdmin owner** (the platform deployer, unless ownership was transferred) — otherwise the ProxyAdmin call reverts.
- The new implementation is whatever the **currently compiled source** for `CONTRACT` is — the upgrade "payload" is your working tree. Upgrading from a dirty or wrong branch deploys that code; verify the checkout before running.
- The OZ plugin's layout check relies on `.openzeppelin/<network>.json` manifest data (network files maintained by the plugin). Storage rules for authors: append-only state, consume `__gap` slots when adding variables, never reorder or delete.
- If the new version needs one-time setup for new state, add a `reinitializer(n)` function and pass it via the upgrade call — the current script does not wire an initializer during upgrades (the V2 test fixtures deliberately need none; see [`upgrades/`](../upgrades/DinTokenV2.md)).

---

## 4. Relationship to Tests

`hardhat/test/*.upgrade.test.ts` rehearse exactly this flow per contract (via the same `upgradeTransparentProxy` helper plus `upgrades.validateUpgrade`) against V2 fixtures, asserting that state, wiring, and access control survive. Run them before any real upgrade:

```bash
npx hardhat test test/DinToken.upgrade.test.ts test/DinCoordinator.upgrade.test.ts \
  test/DinValidatorStake.upgrade.test.ts test/DINModelRegistry.upgrade.test.ts
```

---

## 5. Notes

- One contract per invocation — upgrading several contracts is several runs (deliberate: keeps each on-chain change reviewable).
- There is no timelock, dry-run flag, or confirmation prompt; the only safety nets are the OZ layout validation and operational discipline.
- The script never touches wiring (`setCoordinator`, `updateValidatorStakeContract`) — proxy addresses are stable, so wiring never needs to change on upgrade.
