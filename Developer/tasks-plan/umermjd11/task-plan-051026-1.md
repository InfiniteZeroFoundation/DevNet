# Task Plan: Contract Follow-ups: `DINTaskAuditor` Size (#201 A4), Dual-Role Guard (#180), Cross-Model S5 (#193)

**ID:** task-plan-051026-1
**Author:** Umer Majeed (@umermjd11)
**Reviewer:** @umeradl
**Created:** 2026-10-05
**Status:** Approved in PR #219 with [review amendments 1–5](https://github.com/InfiniteZeroFoundation/DevNet/pull/219#issuecomment-6001172350) and [reviewer decisions 1–3](https://github.com/InfiniteZeroFoundation/DevNet/pull/219#issuecomment-6001173454) (recommended options accepted). Forwarded 2026-10-06 → [task_061026_20](https://github.com/InfiniteZeroFoundation/DevNet/blob/develop/Developer/tasks/task_061026_20.md) (forwarding PR, linked on this PR)
**Proposed dates:** Oct 6 – Oct 9, 2026
**Repo:** https://github.com/InfiniteZeroFoundation/DevNet
**Base branch:** `develop`. The plan was written against commit `740a613` (2026-10-05, after PR #215 and its follow-up). Line numbers below are for that commit.
**Roadmap ref:** P3-6.3a (gas/size), P3-6.3b (audit preparation, open findings), P3-4.2 (penalty tiers, S5)
**Companion plan:** [task-plan-051026-2](https://github.com/InfiniteZeroFoundation/DevNet/pull/229) (PR #229) covers full-GI alignment: contracts check plus richer GI states, dincli commands, the integration suite on foundry, and GI docs. This plan was narrowed to the contract items so the two don't conflict; see [Coordination](#coordination-with-task-plan-051026-2).
**Previous plan:** [task-plan-021026-1](task-plan-021026-1.md) → [task_021026_19](../../tasks/task_021026_19.md) (all six Parts landed; [Discussion #216](https://github.com/InfiniteZeroFoundation/DevNet/discussions/216))

**Flow:**
1. umeradl reviews this plan on its PR.
2. I apply the review amendments here.
3. Once it is approved, the plan is forwarded as **one** `Developer/tasks/task_DDMMYY_n.md` spec with one Part per TP, and this file is marked as forwarded.

---

## Selection

After task_021026_19, the open issues that need no outside owner are either one decision away from code (#180, #193), or are what's left of an issue that has already partly landed (#201 Part A item 4).

The dincli, integration-suite and docs items this plan first carried (BL-27/BL-28, the DevNet 2.0 dincli commands, public docs drift) moved to [task-plan-051026-2](https://github.com/InfiniteZeroFoundation/DevNet/pull/229). Plan 2 orders that work as contracts check → dincli → suite → docs.

| # | Issue | Area | Why now |
|---|---|---|---|
| TP-1 | [#201](https://github.com/InfiniteZeroFoundation/DevNet/issues/201) Part A, item 4 | `DINTaskAuditor` size review | Left open in the [#201 status update](https://github.com/InfiniteZeroFoundation/DevNet/issues/201). `DINTaskAuditor` is at 22,718 B (1,858 B margin), so the gate warns on every PR, and TP-2 and later mechanism work add more bytes |
| TP-2 | [#180](https://github.com/InfiniteZeroFoundation/DevNet/issues/180) | Dual-role registration (auditor + aggregator, same GI) | The decision is all that's missing. Prototype: guard +102 B. Also carries the amendment-4 NatSpec fix |
| TP-3 | [#193](https://github.com/InfiniteZeroFoundation/DevNet/issues/193) | S5 recidivism per slasher contract | `DinValidatorStake` has about 14 KB headroom. Needs an option choice ([Decision 3](#reviewer-decisions)). The fix fits the existing storage gap |

---

## Status check at `740a613`

| Item | State at `740a613` |
|---|---|
| #201 A4 | `DINTaskAuditor` is 22,718 B runtime (1,858 B margin, gate **warns**). It has 16 public mappings, and several duplicate an existing view or have no reader outside the contract (see TP-1) |
| #180 | `registerDINAuditor` (`DINTaskAuditor.sol:667-698`) and `registerDINaggregator` (`DINTaskCoordinator.sol:401-434`) have no cross-role check. The PR #182 review ruled dual-role **not** intended (`adversarial-threat-model.md` Judgment call 2, Row 6 = KNOWN GAP). The stale "(not yet enforced)" NatSpec is still at `DinValidatorStake.sol:451` and `:462` |
| #193 | The S5 ring is `_partialSlashGIs[validator][msg.sender]` (`DinValidatorStake.sol:146`, used in `slashPartial` at `:294-322`), so it is counted per slasher **contract**. Even within one model, S1 (auditor contract) and S2 (coordinator) are separate rings. `Developer/design/MECHANISM_DESIGN.md:81` defines S5 per validator across both roles |

---

## Sequencing

| Item | Touches | Conflicts with | Rule |
|---|---|---|---|
| TP-1 | `DINTaskAuditor.sol` (getter visibility), the foundry tests that read those getters, `dincli/abis/DINTaskAuditor.json`, `DINTaskAuditor.md` §3 | TP-2 (same contract, size); plan 2 TP-3 (views it reads) | **First.** Measure on the actual implementation and agree the getter set ([Decision 1](#reviewer-decisions)) |
| TP-2 | `DINTaskAuditor.registerDINAuditor`, `IDINTaskCoordinator` (`DINShared.sol`), a new error, `DinValidatorStake.sol` NatSpec, tests, threat model Row 6 | TP-1 | After TP-1, or as commit 2 of TP-1's PR (the same pattern as task_021026_19 A+B) |
| TP-3 | `DinValidatorStake.sol` (S5 storage + `slashPartial`), S5 tests, `DinValidatorStake.md`, threat model Row 11, deploy-script S5 keys | — | **In parallel with TP-1.** Different contract |

**PR #218** (`P3Adversarial.t.sol`, #154 Part 2) is open and encodes Row 6 (#180) and Row 11 (#193) as `test_knownGap_…`. If it merges first, TP-2 and TP-3 each flip their row's test to `test_defended_…` in the same PR. If TP-2/TP-3 merge first, PR #218 rebases and flips them. Either way, no test is left asserting a closed gap.

One PR per TP, or TP-1 + TP-2 as two commits in one PR. Rebase on `develop` after each merge, with no stacked branches. PR #31/#32 (`dincli/sdk`, daemon) rebase onto these changes.

---

# TP-1 — #201 Part A item 4: `DINTaskAuditor` size review

Same approach as task_021026_19 Part A. Shrink the contract in place, with no library, split or deploy change. Only **getter visibility** changes. No state-changing function, event or storage slot changes.

**Prototype on `740a613`.** `via_ir`, 200 runs. Each line makes one public mapping `internal`; the last two lines combine several.

| Getter | Readers outside the contract | Saving | Note |
|---|---|---|---|
| `auditBatches` (struct array) | none (the only hit is a comment, `RewardEngine.t.sol:895`) | −100 B | `getAuditorsBatch` already returns the batch |
| `dinAuditors` | none | −83 B | `getDINtaskAuditors` already returns the list |
| `Is_testdataCIDs_Assigned` | none | −58 B | Unused |
| `auditorGIWeight` | none | −79 B | |
| `rewardClaimed` | none | −84 B | plan 2's claim command reads it, so **keep** |
| `testDataDisputes` | 2 foundry tests | −117 B | plan 2's dispute commands read it, so **keep** |
| `giRewardSnapshot` | 2 foundry tests | −145 B | plan 2's claim command reads `settled`, so **keep** |
| **Recommended four** (the first four rows) | | **−320 B → 22,398 B** (2,178 B margin) | Clears the warn band. With TP-2: 22,500 B (measured in the review) |
| All seven | | −666 B → 22,052 B | Only if plan 2 reads that state some other way |

Scope:
- Make the agreed getters `internal`. No test reads `auditBatches`, so no test changes are needed.
- Regenerate `dincli/abis/DINTaskAuditor.json` (`dump-abi --official`) and update `DINTaskAuditor.md` §3.
- Check the subgraph branch for reads of the dropped getters, and post an ABI note on PR #29 (as in task_021026_19 Part A).
- Do the "same review" of per-phase duplication that #201 item 4 asks for. Measuring the folds of the near-duplicate dispute and reassignment paths is **required, not optional** (review amendment 3): TP-1 + TP-2 leave only 28 B above the 2,048 B warn line. Commit a fold only if it actually shrinks the contract: in task_021026_19, `via_ir` made the coordinator folds **grow** it.

**`DINTaskAuditor` budget across both plans** (review amendment 4 / Decision 1). Scratch builds on `a1fcce2`, `via_ir`, 200 runs:

| Step | Runtime | Margin | Band |
|---|---|---|---|
| `develop` | 22,718 B | 1,858 B | warn |
| + TP-1 (four getters `internal`) | 22,398 B | 2,178 B | ok |
| + TP-2 (#180 guard, +102 B) | 22,500 B | 2,076 B | ok (28 B above the warn line) |
| + plan 2's every-batch commitment check in `setTestDataAssignedFlag` (+75 B) | 22,575 B | 2,001 B | **warn** (47 B under the line, far above the 1,024 B fail line) |

To get back out of the warn band after both plans:
- The fold review above.
- Dropping `Is_testdataCIDs_Assigned` entirely, once task_061026_21's `AuditTestDataAssigned` coordinator state guards the double-set. It is written but never read outside its own guard.

Whichever task lands second reports the combined size.

**Deliverables:** a size table from one build of the implementation. `forge test` (full suite, including `UpgradeValidation.t.sol`) and `pytest -m "not integration"` are green, and the gate is green.

**Estimate:** 1 day.

---

# TP-2 — #180: one address can't hold both roles in a GI

**Recommendation: a per-address cross-role guard** ([Decision 2](#reviewer-decisions)). The guard is Sybil-bypassable (a second address with its own stake), which the threat model already notes. But it forces the attacker to put up a second stake and makes the attack visible on-chain, for +102 B. Documenting stake cost as the only defence would also need a non-zero `maxConcurrentRegistrationsPerStakeUnit` default. That is a tokenomics call belonging to #155, so I'd rather not tie this fix to it.

- **Where the guard goes.** Aggregator registration (states 6–7) always comes **before** auditor registration (8–9) (`DINShared.sol:17-20`). So the guard belongs in `registerDINAuditor`: `if (dintaskcoordinatorContract.isDINAggregator(_GI, msg.sender)) revert TA_DualRoleNotAllowed();`. It needs `isDINAggregator(uint256,address)` added to `IDINTaskCoordinator`, and the coordinator's public mapping `isDINAggregator` (`DINTaskCoordinator.sol:34`) already provides it. A coordinator-side guard would never fire, because no auditor exists yet when aggregators register.
- **Prototype cost:** `DINTaskAuditor` goes from 22,718 to 22,820 B (+102 B). The coordinator is unchanged.
- **NatSpec (amendment 4):** fix `DinValidatorStake.sol:451` and `:462` ("not yet enforced"), and the "decremented at endGI time" note at `:121` (the decrement happens in `releaseGIRegistrationSlots`).
- **Tests** (next to the `StakingEnforcement.t.sol` registration tests):
  - An aggregator registering as an auditor in the same GI reverts.
  - Registering as an auditor in a different GI succeeds.
  - A different address with its own stake succeeds, which documents the Sybil limit.
- **Docs:** threat model Row 6 changes from KNOWN GAP to DEFENDED (with the Sybil-limit note), and its stale line refs are fixed. Update `DINTaskAuditor.md` (registration checks, §13 caveat) and the `DINShared.md` error row.

**Estimate:** 0.5 day.

---

# TP-3 — #193: S5 escalation across models

**Recommendation: a two-level check where the global level is time-based** ([Decision 3](#reviewer-decisions), options A/B/C below).

- **The per-slasher ring stays as it is** (per-model escalation, existing tests and semantics).
- **Add a per-validator global ring of `block.timestamp` values**, `_partialSlashTimes[validator]`, with `s5GlobalWindow` (seconds) and `s5GlobalThreshold`.
  - Timestamps are monotonic across every slasher, so the ascending-order trim that forced per-contract keying (`DinValidatorStake.sol:136-146`) stays safe.
  - `slashPartial` escalates when **either** level reaches its threshold, and clears both rings on escalation.
- **Also closes the same-model split.** S1 (auditor contract) and S2 (coordinator) misses by one validator in one model now add up.

Options for the decision:
- **A (recommended): two-level, as above.** Per-model behaviour is unchanged. The cross-model gap closes. Two new owner-settable params.
- **B: replace the per-slasher ring with the global timestamp ring.** Simpler, but it changes S5 from "per N GIs" to "per T seconds" for every model, and models with different GI cadences then mean different things.
- **C: accept and document.** Calibrate the per-model threshold as the issue describes, and leave Row 11 as an accepted trust assumption.

Scope (option A):
- **Storage.** Append the new storage before `__gap` (`DinValidatorStake.sol:174`) and shrink the gap by the slots used. `DinValidatorStakeV2` inherits the change, and `UpgradeValidation.t.sol` plus the `DeployPlatform.t.sol` upgrade tests must stay green.
- **Setter.** `setS5GlobalParams(window, threshold)` with the same validation style as `setS5RecidivismParams` (`:583-594`).
  - **Defaults:** `s5GlobalWindow = 7 days` and `s5GlobalThreshold = 2 × s5RecidivismThreshold` (6). These are placeholders until #155.
  - Set them in `initialize`. For an upgraded proxy, **0 means off** (Decision 3), not a `reinitializer`. Nothing on `develop` is deployed, and the DevNet 2.0 deploy is a fresh `DeployPlatform.s.sol` run, so `initialize` sets the defaults. Add optional deploy-script env keys `S5_GLOBAL_*`, matching the existing `S5_*` keys.
- **Event.** `ValidatorEscalatedS5` gets a level flag, or a sibling event, so indexers can tell which level fired.
- **Tests:**
  - **Two slashers below the threshold.** Two task contracts each slash one validator (threshold−1) times within the window. The global level escalates.
  - **Window expiry** resets the count.
  - **Per-model behaviour unchanged.** The existing S5 tests and `test_crossModelGICollision_slashPartialDoesNotUnderflow` stay green.
- **Docs:** `DinValidatorStake.md`, `Developer/design/MECHANISM_DESIGN.md` S5 row, and threat model Row 11 (change it to DEFENDED). Also record the separate discrepancy found here: `Developer/design/MECHANISM_DESIGN.md:87` says S5 is "entire slashable stake + blacklist", while the code does `MIN_STAKE` + a 7-day jail. Note it; don't change it in this TP.

**Estimate:** 1.5 days.

---

## Coordination with task-plan-051026-2

[task-plan-051026-2](https://github.com/InfiniteZeroFoundation/DevNet/pull/229) touches some of the same files. This is how the two avoid conflicts:

- **Getters (TP-1).** The recommended set (`auditBatches`, `dinAuditors`, `Is_testdataCIDs_Assigned`, `auditorGIWeight`) isn't read by dincli or the integration suite. Plan 2's new commands read `giRewardSnapshot`, `rewardClaimed` and `testDataDisputes`, so those stay public. That's why Decision 1 recommends the set of four, not all seven. If plan 2's new `AuditTestDataAssigned` state makes the test-data flag redundant, `Is_testdataCIDs_Assigned` can go entirely, settled in whichever PR lands second.
- **`DINShared.sol`.** TP-2 here adds `isDINAggregator` to `IDINTaskCoordinator`. Plan 2's TP-2 edits the `GIstates` enum in the same file. The sections differ; the second PR to merge rebases.
- **`dincli/abis/DINTaskAuditor.json`.** Both plans regenerate it (`dump-abi --official`); the second to merge regenerates on top of the first.
- **#180 guard vs the suite.** The integration suite uses disjoint accounts (aggregators 11–22, auditors 50–58), so the guard doesn't break it. Plan 2's suite adds a negative check once this lands.
- **#193** doesn't affect a single-model GI, so plan 2's suite is unaffected.

---

## Reviewer decisions

Resolved 2026-10-06 on the [decisions comment](https://github.com/InfiniteZeroFoundation/DevNet/pull/219#issuecomment-6001173454). The reviewer's recommended option was accepted each time.

1. **TP-1 getter set: A, with C's accounting.** The four getters (`auditBatches`, `dinAuditors`, `Is_testdataCIDs_Assigned`, `auditorGIWeight`) become `internal`. The PR reports one size table covering TP-1, TP-1 + TP-2, and task_061026_21's commitment check (budget table above). If `Is_testdataCIDs_Assigned` is still needed after task_061026_21, it stays `internal`.
2. **#180: A, a per-address guard in `registerDINAuditor`,** with the three tests. PR #218's `test_knownGap_dualRoleRegistration` flips to `test_defended_…` in whichever PR lands second.
3. **#193: A, two-level S5.** Placeholder defaults are `7 days` / threshold `6` until #155. For upgraded proxies, 0 means off (no `reinitializer`). `UpgradeValidation.t.sol` stays green. The `Developer/design/MECHANISM_DESIGN.md:87` discrepancy is recorded as a note, not changed.

---

## Deferred (not in this plan)

| Issue | Reason |
|---|---|
| [#201](https://github.com/InfiniteZeroFoundation/DevNet/issues/201) Part B | Mechanism decision (the slash reason for committed-but-unrevealed), tied to #155 / #38 |
| [#194](https://github.com/InfiniteZeroFoundation/DevNet/issues/194) | Needs a design note first (refund path, CID repair) |
| [#78](https://github.com/InfiniteZeroFoundation/DevNet/issues/78) | Two decisions open: where the network-fee floor is enforced, and which gas-price input to use |
| [#154](https://github.com/InfiniteZeroFoundation/DevNet/issues/154) Part 2 | Owned through [task_240926_17](../../tasks/task_240926_17.md) Part 2: `P3Adversarial.t.sol` is open as [PR #218](https://github.com/InfiniteZeroFoundation/DevNet/pull/218). TP-2 and TP-3 flip its Row 6 and Row 11 tests (see [Sequencing](#sequencing)) |
| [#181](https://github.com/InfiniteZeroFoundation/DevNet/issues/181), [#178](https://github.com/InfiniteZeroFoundation/DevNet/issues/178) | Mainnet-grade (decentralized adjudication, VRF) |
| [#185](https://github.com/InfiniteZeroFoundation/DevNet/issues/185), #166, #167 | Long-run / umbrella |
| #155, #157, #158, #174, #42, #43, #24, #21, #20, #23, #75 | Assigned to others, deferred, or non-code |
| [#39](https://github.com/InfiniteZeroFoundation/DevNet/issues/39) workstream 2, [#38](https://github.com/InfiniteZeroFoundation/DevNet/issues/38) | Mechanism redesign tracking, not a single change |
| BL-27, BL-28, DevNet 2.0 dincli commands, integration suite, GI docs | Moved to [task-plan-051026-2](https://github.com/InfiniteZeroFoundation/DevNet/pull/229) (PR #229) |
| [#228](https://github.com/InfiniteZeroFoundation/DevNet/issues/228) | Integration suite in a separate CI job, a follow-up once plan 2's suite passes a complete GI |
| BL-29, BL-30, BL-31 | Each needs a design decision (FeeRouter bucket consumers, GI abort, S6 scope) |
| BL-32, BL-33 | Ideas (preflight `doctor`, deployment drift check). These are good candidates for the next plan |
