# types.ts — Deploy Types Documentation

> **File:** `hardhat/deploy/types.ts`
> **Role:** shape of the per-network deployment record (`deployments/<network>.json`)

---

## 1. Contents

```ts
export interface PlatformAddresses {
  dinToken: string;
  dinCoordinator: string;
  dinValidatorStake: string;
  dinModelRegistry: string;
  proxyAdmin?: string;
  implementations?: {
    dinToken?: string;
    dinCoordinator?: string;
    dinValidatorStake?: string;
    dinModelRegistry?: string;
  };
}
```

---

## 2. Field Semantics

| Field | Written by | Meaning |
|-------|-----------|---------|
| `dinToken` … `dinModelRegistry` | `deploy-platform.ts` | **Proxy** addresses — permanent, user-facing, the ones dincli and docs should reference |
| `proxyAdmin` | `deploy-platform.ts` | The ProxyAdmin contract holding upgrade rights (read from the token proxy's ERC-1967 admin slot; shared across the platform's proxies in a deployment run) |
| `implementations.*` | `upgrade-platform.ts` | Latest implementation address per contract, recorded after each upgrade (absent until a contract has been upgraded at least once) |

Optionality encodes history: a fresh deployment has no `implementations` block; each upgrade merges its contract's entry in without touching the others.

## 3. Consumers

- `scripts/upgrade-platform.ts` — reads proxy addresses, appends implementation addresses.
- Operational reference — the file is the canonical record for verifying contracts on a block explorer (proxy + implementation pairs).
