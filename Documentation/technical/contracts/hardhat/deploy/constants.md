# constants.ts — Deploy Constants Documentation

> **File:** `hardhat/deploy/constants.ts`
> **Role:** single source of truth for proxy kind and the platform contract list

---

## 1. Contents

```ts
export const PROXY_KIND = "transparent" as const;

export const PLATFORM_CONTRACTS = [
  "DinToken",
  "DinCoordinator",
  "DinValidatorStake",
  "DINModelRegistry",
] as const;

export type PlatformContractName = (typeof PLATFORM_CONTRACTS)[number];
```

---

## 2. Purpose

- **`PROXY_KIND`** pins the OpenZeppelin proxy pattern to **Transparent** in exactly one place using a const assertion to guarantee strict immutability. Instead of letting TypeScript think this is a generic string that could be modified later, it locks the type strictly to the literal value "transparent". Every `deployProxy` / `upgradeProxy` / `validateUpgrade` call in scripts and tests imports it, so the platform cannot drift into a mixed transparent/UUPS deployment by a stray option.
- **`PLATFORM_CONTRACTS`** is the allowlist the upgrade script validates its `CONTRACT` env var against, and the key set for the `PROXY_KEYS` mapping in [`upgrade-platform.ts`](../scripts/upgrade-platform.md).

The `as const` tuple gives compile-time exhaustiveness via `PlatformContractName`. Instead of the array containing generic strings, TypeScript tracks the exact literal values and their order.

TypeScript evaluates PlatformContractName to: `"DinToken" | "DinCoordinator" | "DinValidatorStake" | "DINModelRegistry"`.

## 3. Maintenance

Adding a new platform contract requires touching this list, the `PROXY_KEYS` map in `scripts/upgrade-platform.ts`, the [`PlatformAddresses`](types.md) interface, the deploy script, and the test fixture — the compiler will flag most of these once the tuple is extended.
