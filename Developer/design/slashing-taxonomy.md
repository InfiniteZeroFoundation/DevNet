# Slashing conditions taxonomy — implementation mapping (Issue #38, Part 4a)

**Status:** Spec only. No contract changes in this document — see `foundry/test/SlashingInvariants.t.sol` for the invariant tests that back the "current behaviour" claims below, and `DINTaskCoordinator.sol`'s `DisputeResolution` scaffold (Part 4c) for the one condition (S4) that gets an actual code hook this round.

This expands the S1–S6 table in `Developer/design/MECHANISM_DESIGN.md` §4 with exactly where each condition would hook into the existing contracts, and what's already there today versus what's still a gap. Read that section first for the resolved policy decisions (penalty tiers, 50/50 burn/treasury destination, dispute bond mechanics) — this doc doesn't repeat those, it maps them to call sites.

## Today's baseline, verified against code (not the design doc's description of it)

`DinValidatorStake.slash()` (`foundry/src/DinValidatorStake.sol:197`) decrements `v.activeStake` (then `v.pendingWithdrawals` if active stake is insufficient) by the slashed amount and emits `ValidatorSlashed`. **Update (2026-08-31):** at this doc's original merge-base that was the entire effect — no `transfer`/`burn` call, slashed tokens stranded unreachable in the stake contract's own balance, accounted to nobody. #65 (merged into `develop` after this branch cut) closed that gap: `slash()` now burns 50% of the slashed amount via `IBurnableToken.burn` and routes the other 50% to `slashTreasury` via `safeTransfer` (or burns both halves if `slashTreasury` is unset), before emitting `ValidatorSlashed`. `Developer/design/MECHANISM_DESIGN.md` §4's "50/50 burn/treasury destination" policy is therefore now actually implemented in code, not just decided — the "accidental burn" framing this section originally used no longer applies.

`SlashingInvariants.t.sol` (Part 4b) was written to prove the pre-#65 "never moves tokens" behavior with a fuzz test rather than asserting it from reading the source once — it now fails 3 of its 12 tests against current `develop` for exactly that reason (`test_slash_doesNotTransferOrBurnTokens` and both balance/stranded-amount invariants). Updating those 3 tests to assert #65's burn/treasury split instead is tracked separately (see the backlog), not done as part of this doc fix.

Also confirmed: both existing slash call sites (`DINTaskAuditor.slashAuditors`, `DINTaskCoordinator.slashAggregators`) pass a flat `minStake()` as the slash amount, not a fraction of it. That's the "Partial" tier column in the MECHANISM_DESIGN table being aspirational, not actual — today a single missed vote or missed T1/T2 submission fully unstakes a floor-staked validator. Flagged as a gap below (S1/S2), not fixed here — the DAO-settable partial-slash fraction is explicitly Robbert's `task_210726_5` scope per this task's brief.

## S1 — Missed audit vote in assigned batch

- **Role:** Auditor
- **Today:** Implemented. `DINTaskAuditor.slashAuditors` (`DINTaskAuditor.sol:620`) iterates every auditor in every batch for the GI and slashes anyone who didn't call `setAuditScorenEligibility` (or, once PR #63 merges, didn't reveal) for every model index in their batch. Reason code `"AUD_NO_VOTE"`.
- **Gap:** flat `minStake()` slash amount, not the partial fraction MECHANISM_DESIGN specifies for a liveness fault. No distinction between "missed one model out of five" and "missed all five" — both slash the full stake once. Fix belongs to the DAO-settable-fraction work (Robbert's task), not this one.

## S2 — Missed T1/T2 aggregation submission

- **Role:** Aggregator
- **Today:** Implemented. `DINTaskCoordinator.slashAggregators` (`DINTaskCoordinator.sol:678`) walks every T1 and T2 batch and slashes any assigned aggregator who either didn't submit or submitted a CID that lost the majority vote. Reason codes `"AGG_T1_NO_SUBMISSION"` / `"AGG_T1_BAD_CONSENSUS"` / the T2 equivalents.
- **Gap:** same flat-amount issue as S1, and no distinction between "didn't submit" (liveness) and "submitted the wrong CID" (could be liveness — stale local state — or could be S4-grade malice) — both currently slash the same amount under the same tier. Splitting those two reason codes into different penalty tiers is a natural follow-up once the partial-slash fraction exists, not attempted here.

## S3 — Score deviation beyond threshold from cross-auditor median

- **Role:** Auditor
- **Hook point:** `DINTaskAuditor.finalizeEvaluation`, immediately after the per-model median is computed. Part 1 (`feature/scoring-validation`, PR #62) added `_medianOf` and the `s3DeviationThreshold`/`AuditorScoreDeviation` event pair in shadow mode — computed and emitted, never gating. This condition is that event, wired to an actual slash call once the threshold graduates out of shadow mode.
- **Today:** not slashed. Deliberately — PR #62 shipped detection only, per this task's own §1d ("ship the S3 deviation threshold in shadow mode... don't gate anything yet"). Turning shadow-mode detection into an actual S3 slash is future work, not silently smuggled into this stretch part.
- **Note:** this is a "Partial → Full on repeat" tier per MECHANISM_DESIGN, i.e. it depends on S5 (recidivism counting) to reach its full form. Sequencing: S3 gating needs real-world threshold calibration first (the shadow-mode data collection is the point), S5 needs the counter infra described below. Neither blocks the other's spec from being written now.

## S4 — Invalid aggregation (T1/T2 CID fails recomputation)

- **Role:** Aggregator
- **Hook point:** built this round. `DINTaskCoordinator`'s new dispute-resolution scaffold (Part 4c) — a validator opens a dispute against a specific finalized T1 or T2 batch within a dispute window, posting a bond; if upheld (by owner/DAO adjudication for now — no on-chain recomputation of model weights is feasible in this contract, see note below), the batch is marked disputed and a fresh aggregator subgroup (excluding the accused and the original batch's aggregators) is assigned to redo it. Bond forfeiture/bounty payout is stubbed behind a treasury-shaped interface, matching Part 3's `treasuryAccrued` pattern — no real fund movement, since `DinTreasury` doesn't exist on `develop` yet.
- **Why "off-chain challenge + on-chain dispute" rather than on-chain recomputation:** the CID being disputed points to aggregated model weights on IPFS; verifying "does this CID actually equal the correct aggregation of these inputs" requires re-running the aggregation function over potentially large tensors, which is not something a Solidity contract can or should do. The chain's job is bond custody, window enforcement, and re-assignment bookkeeping — the actual dispute adjudication (was the CID wrong?) happens off-chain today (by the owner, in this scaffold) and is a natural target for a future on-chain fraud-proof or committee-vote mechanism. Flagged, not solved, here.
- **Gap:** adjudication is `onlyOwner` in the scaffold, i.e. centralized. That's explicit and intentional for this stretch scope — MECHANISM_DESIGN's dispute section doesn't specify the adjudicator, and building a fair on-chain jury mechanism is well beyond a stretch-scope scaffold.

## S5 — Repeated liveness failures (recidivism)

- **Role:** Both
- **Hook point:** would need a per-validator, per-window slash counter — e.g. `mapping(address => uint256[]) recentSlashGIs` or a simpler rolling count reset by GI number, checked inside `DinValidatorStake.slash()` or by the calling task contract before each S1/S2/S3 slash. Since `slash()` is shared across every task contract for every model (it's on the platform-level `DinValidatorStake`, not per-task), the counter almost certainly belongs there, not in `DINTaskAuditor`/`DINTaskCoordinator`, so behavior is consistent across all models a validator participates in.
- **Today:** no counter exists anywhere. Every slash is independent; a validator can miss every vote for ten GIs running and pay the exact same partial (well — currently flat) penalty each time.
- **Gap:** full gap, nothing to reuse. Needs `DinValidatorStake` storage changes (a new mapping, `r`/`w` DAO parameters), which puts it in the same bucket as the partial-slash fraction — governable storage additions to a contract Robbert's concurrent task is also touching. Sequencing this after `task_210726_5` merges avoids a storage-layout collision on an upgradeable proxy.

## S6 — Registration without capacity

- **Role:** Both
- **Hook point:** `DINTaskCoordinator.registerDINaggregator` (`DINTaskCoordinator.sol:185`) and `DINTaskAuditor.registerDINAuditor` (`DINTaskAuditor.sol:188`) at registration time, plus a read at `endGI`/`slashAuditors`/`slashAggregators` time comparing "registered" against "actually did anything" across GIs, not just within one.
- **Today:** no cross-GI participation counter exists. A validator who registers every GI and never submits anything is currently indistinguishable, penalty-wise, from one who registers once and has a single bad GI — S1/S2 already slash the no-participation case *within* a GI, but nothing tracks the pattern *across* GIs to escalate it.
- **Gap:** full gap. Same storage-collision reasoning as S5 — this is naturally a `DinValidatorStake`-level counter (capacity is a validator-level concept, not a per-model one), so it's sequenced behind Robbert's task for the same reason.

## Summary: what's actually gap-closed by this task vs. spec-only

| Condition | This task | Status after this task |
|---|---|---|
| S1 | — | Implemented (pre-existing), flat-amount gap noted, unfixed |
| S2 | — | Implemented (pre-existing), flat-amount + reason-tier gap noted, unfixed |
| S3 | — (Part 1 shipped shadow-mode detection separately) | Detected, not gated; slash wiring is future work |
| S4 | Dispute scaffold built (Part 4c) | Bond/window/reassignment on-chain; adjudication centralized, payout stubbed |
| S5 | Spec only (this doc) | No code; blocked behind Robbert's governable-storage work |
| S6 | Spec only (this doc) | No code; blocked behind Robbert's governable-storage work |

Invariant tests (Part 4b) exercise S1/S2's existing `slash()` path only — S3–S6 have no slash call sites yet to test against.
