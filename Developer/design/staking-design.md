# DIN Staking — Design (easy-to-follow)

**Status:** Working design — the readable entry point for validator staking
**Owner:** Umer
**Tracking:** [GitHub issue #37](https://github.com/InfiniteZeroFoundation/DevNet/issues/37)
**Deep-dive companions:** [MECHANISM_DESIGN §3](MECHANISM_DESIGN.md) (consolidated design) · [issues/staking-mechanism.md](../issues/staking-mechanism.md) (registry/selection backlog + jailing/tombstoning proposals) · [suggested-staking-mechanism.md](suggested-staking-mechanism.md) (production hardening spec — parts of its fix set have since shipped, see §2)

---

## 1. Why staking, in one minute

Validators (auditors + aggregators) are the only roles with power to corrupt outcomes — scores, aggregation results, and therefore rewards. Staking makes that power expensive: every validator action is backed by capital at risk that should exceed the profit from cheating on one GI. Clients deliberately do **not** stake (a stake would kill data-contribution supply; client Sybil resistance comes from scoring, not capital). Staking depends on the DIN token, which is why [tokenomics-design.md](tokenomics-design.md) comes first in the design order.

## 2. Staking today — what exists, what's missing

More is implemented than older docs suggest. The full current-state reference (lifecycle state machine, unbonding, non-blocking slash semantics, eligibility gates) is graduated to [`Documentation/technical/mechanisms/staking-mechanism.md`](../../Documentation/technical/mechanisms/staking-mechanism.md) per the [graduation rule](../README.md). In short, `develop` already has: the 10-DIN min-stake gate, 7-day unbonding with slashable pending withdrawals, non-blocking capped `slash(validator, amount, reason)`, the `None/Active/Exiting/Jailed/Blacklisted` lifecycle enum, `isValidatorActive()` gates at registration/batch/submission in both task contracts, and a single `minStake()` source of truth.

What is **missing** — the design gaps this document targets:

| Gap | Detail |
|---|---|
| **Jailing unreachable** | `Jailed` status exists but nothing can set it — no `jailValidator()`, no `reactivate()` |
| **Slashed-stake destination** | Slashed DIN strands inside the contract (accidental burn) |
| **Governable parameters** | `MIN_STAKE`, `UNBONDING_PERIOD` are constants |
| **Per-model stake sizing** | One network-wide floor only |
| **Stake-at-risk accounting across GIs** | One 10-DIN stake can back any number of concurrent registrations |
| **Withdrawal queue** | Only one pending withdrawal at a time |
| **Tombstoning / permanent removal** | Blacklist is administrative and reversible; no protocol-level permanent ban |

> Historical note: [suggested-staking-mechanism.md](suggested-staking-mechanism.md) §"Current Implementation Findings" documented eligibility-gate and blocking-slash bugs; its Phase 1–2 migration plan (active-status gates, request/claim unbonding, lifecycle statuses, non-blocking slash) is now implemented. Its Phase 3–4 (full penalty classes, deadlines, governance hardening) remains open and is folded into the target design below and into [issue #38 (slashing)](https://github.com/InfiniteZeroFoundation/DevNet/issues/38).

## 3. Target design (DevNet 2.0)

### 3.1 Stake sizing — from one constant to three layers

1. **Network floor** — `minStake` becomes DAO-settable storage (replacing the constant).
2. **Per-model requirement** — the model owner sets a stake requirement at task deploy, bounded by DAO `modelMinStakeBounds[min,max]`, so high-value models demand more skin in the game.
3. **Registration check** — GI registration requires `getStake(validator) >= max(networkMin, modelMin)` (today only Active status is checked).

### 3.2 Stake-at-risk across concurrent GIs

A validator registered in N concurrent GIs has the same stake backing all N commitments. 2.0 adds a cap: concurrent registrations ≤ `stake / slashableAmountPerRegistration` (parameter `maxConcurrentRegistrationsPerStakeUnit`), so one floor stake cannot back 20 tasks.

### 3.3 Lifecycle completion — make Jailed real

From [issues/staking-mechanism.md](../issues/staking-mechanism.md) (proposals adopted):

- `jailValidator(address, uint64 duration, bytes32 reason)` — callable by slasher contracts, for liveness/procedural faults (cheaper than slashing for honest-but-offline).
- Explicit `reactivate()` — operator-initiated after `jailedUntil` expires and stake ≥ floor; no silent auto-return to Active (a node should prove it's back before receiving work).
- **Tombstoning** (permanent, protocol-level ban for provable malice) — proposed, with open questions (authority, 100% vs partial slash, accidental-tombstone recovery); decision folds into the S4/S5 full-slash design in [issue #38](https://github.com/InfiniteZeroFoundation/DevNet/issues/38).
- Blacklist stays an emergency/administrative kill switch, not a discipline tool; a governance-only `confiscateBlacklistedStake()` → treasury path comes with DAO governance (future).

### 3.4 What deliberately does *not* change

- **Unified stake pool** for both validator roles (simpler accounting; slashers already wired). Revisit only if role risk profiles diverge.
- **7-day unbonding, slashable while pending** — already correct. (Unbonding must outlast offence detection for the last GI participated in.)
- **Random/rotational batch assignment above the stake floor.** Stake-weighted selection is **rejected**: it concentrates work in whales and weakens the cross-validator median. To be recorded in `rejected-ideas/`.
- **No delegation until P5+** — the white paper specifies DPoS delegation; this scope call is now confirmed by Abraham (via Slack, 2026-07-21) in [discussion #46](https://github.com/InfiniteZeroFoundation/DevNet/discussions/46).

### 3.5 Quality-of-life

Withdrawal queue (multiple pending withdrawals) replaces the single-slot limitation — non-blocking, not a 2.0 gate.

## 4. Parameters

| Parameter | Today | Target |
|---|---|---|
| `minStake` | constant 10 DIN | DAO-settable storage |
| `unbondingPeriod` | constant 7 days | DAO-settable (≥ offence-detection window) |
| `modelMinStakeBounds[min,max]` | — | DAO-settable; bounds model-owner stake requirements |
| `maxConcurrentRegistrationsPerStakeUnit` | — | DAO-settable |
| Jail durations per offence class | — | DAO-settable (escalating for repeats — see issue #38) |

Governance hooks arrive via P3-5.1 (`onlyOwner` setters now, multisig/DAO path later).

## 5. Open decisions

| Decision | Recommendation | Where |
|---|---|---|
| Per-role min stake (auditor vs aggregator) | **No** — single floor for 2.0 | this doc / issue #37 |
| Delegation in 2.0 | ✅ **Resolved: No, P5+** — confirmed by Abraham (white-paper author), via Slack, 2026-07-21; not just Umer's recommendation | [Discussion #46](https://github.com/InfiniteZeroFoundation/DevNet/discussions/46) |
| Stake floor economic grounding (cost-of-corruption model vs nominal constant) | Derive from P3-5.2 simulation + Sybil bound (`minStake × validator-to-participant ratio`) | with [tokenomics-design.md](tokenomics-design.md) simulation |
| Tombstoning semantics (authority, slash %, accidental recovery) | ✅ **Resolved for 2.0: no permanent tombstoning** — jail/blacklist suffices (Abraham, via Slack, 2026-07-21). Full tombstoning semantics revisited once delegation lands. | [Issue #38](https://github.com/InfiniteZeroFoundation/DevNet/issues/38) / [discussion #44](https://github.com/InfiniteZeroFoundation/DevNet/discussions/44) |
| Selection: stake as eligibility only vs weight | Eligibility only (weighting rejected) | recorded here; selection engine in [issues/validator_selection.md](../issues/validator_selection.md) |

## 6. Sequencing

1. Tokenomics asset model + stake-floor economics land first ([tokenomics-design.md](tokenomics-design.md), discussions #44/#45).
2. Freeze this spec (§3 target + §5 decisions) → record in [MECHANISM_DESIGN §3](MECHANISM_DESIGN.md).
3. Contract work: governable parameters → per-model stake + registration check → concurrent-registration cap → jailing/reactivation → withdrawal queue. All under PR #13 proxy conventions, with the [suggested-staking-mechanism.md](suggested-staking-mechanism.md) test matrix as the base test plan.
4. Slashing tiers, destinations, and disputes build on top — [issue #38](https://github.com/InfiniteZeroFoundation/DevNet/issues/38), roadmap P3-4.x.
