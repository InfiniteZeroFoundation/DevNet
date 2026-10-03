# DINTaskAuditor — Technical Documentation

> **File:** [`foundry/src/DINTaskAuditor.sol`](../../../foundry/src/DINTaskAuditor.sol)
> **SPDX-License-Identifier:** UNLICENSED
> **Solidity:** `^0.8.28`
> **Deployment:** once per model by the model owner, paired with its `DINTaskCoordinator` (plain `Ownable`, **not** upgradeable)

---

## 1. Overview

`DINTaskAuditor` is the evaluation, reward and test-data half of a model's task contracts. It handles:

- **auditor registration** (active validator, per-model stake floor, concurrent-registration cap, 300-per-GI cap);
- **local model submissions** from clients (one per client per GI, 10 000 per GI);
- **audit batch formation** from the coordinator's locked seed, and encrypted **test-data assignment** (per-auditor encrypted keys, content commitment);
- **commit-then-reveal scoring**: eligibility vote + 0–100 score, median per model, approval against `passScore`;
- **auditor slashing**: S1 (missed vote, partial) and S3 (score deviation, full, behind a switch that is off by default);
- the per-GI **reward pool**: funding, settlement at `endGI`, pull-based claims for clients, auditors and aggregators;
- **test-data disputes**: bonded challenges against the model owner's test data.

Phase transitions are driven by the paired [`DINTaskCoordinator`](DINTaskCoordinator.md); this contract reads its `GI()` / `GIstate()` and gates each function on them.

---

## 2. Inheritance & Dependencies

| Component | Purpose |
|-----------|---------|
| `Ownable` (OpenZeppelin, non-upgradeable) | Model owner: test-data assignment, parameters |
| `ReentrancyGuardTransient` | Guards `claimRewards` and the dispute functions |
| `SafeERC20` / `IERC20` | DIN reward pools, dispute bonds |
| `IBurnableDinToken` (local) | Burns the burn half of forfeited bonds and penalties, and anything that can't be forwarded because no treasury is set |
| `DINShared.sol` | `GIstates`, `IDinValidatorStake`, `IDINTaskCoordinator`, `TA_*` errors |

---

## 3. State

### 3.1 Wiring

| Variable | Description |
|----------|-------------|
| `dinvalidatorStakeContract` | `DinValidatorStake` proxy (constructor) |
| `dintaskcoordinatorContract` | Paired coordinator (constructor) |
| `modelId` (`immutable`) | Registry model ID for the stake floor (constructor) |
| `dinToken` | DIN token (`setDinToken`); required before `depositRewards`, claims or bonded disputes |

There is no treasury address on this contract. The treasury share of rewards and the treasury half of forfeitures go to `dinvalidatorStakeContract.slashTreasury()`, the platform treasury configured on `DinValidatorStake`.

### 3.2 `Params` (constructor defaults — no setter except `passScore`)

| Field | Default | Meaning |
|-------|---------|---------|
| `auditorsPerBatch` | 3 | Auditors per batch |
| `modelsPerBatch` | 3 | Target models per batch |
| `MIN_MODELS_PER_BATCH` | 2 | Smallest allowed final batch |
| `minEligibilityQuorum` | 2 | Votes needed to decide eligibility, and "yes" votes needed to be eligible |
| `minScoreQuorum` | 2 | Revealed scores needed to compute a median |
| `passScore` | 50 | Minimum median for approval; updated via the coordinator's `startGI(gi, score)` |

Constants: `MAX_REGISTERED_AUDITORS = 300`; `MAX_LM_SUBMISSIONS = 10000` (a plain storage variable, not `constant`).

### 3.3 Governable parameters (owner-settable)

| Variable | Default | Setter |
|----------|---------|--------|
| `rewardSplit` | clients 60% / auditors 20% / aggregators 15% / treasury 5% | `setRewardSplit` (must sum to 10 000 bps) |
| `s1SlashFractionBps` | 3000 (30%) | `setS1SlashFractionBps` (1 – 10 000) |
| `s3DeviationThreshold` | 40 (on the 0–100 scale) | `setS3DeviationThreshold` (≤ 100) |
| `s3SlashingEnabled` | `false` (shadow mode) | `setS3SlashingEnabled` |
| `disputeBondAmount` | 100 DIN (`100 * 1e18`) | `setDisputeBondAmount` |
| `disputeWindowBlocks` | 7200 (~1 day on Optimism) | `setDisputeWindowBlocks` |
| `disputePenaltyBps` | 2500 (25% of the GI pool) | `setDisputePenaltyBps` (≤ 10 000) |

The reward split and the S1 fraction are explicitly provisional (MECHANISM_DESIGN §5; issue #155).

### 3.4 Per-GI data

- **Registration:** `dinAuditors[gi]`, `isRegisteredAuditor[gi][addr]`.
- **Submissions:** `lmSubmissions[gi]` (`LMSubmission`: client, modelCID, submittedAt, eligible, evaluated, approved, finalMedianScore), `clientHasSubmitted`, `clientSubmissionIndex`.
- **Batches:** `auditBatches[gi]` (`AuditBatch`: batchId, auditors, modelIndexes, testDataCID), `isBatchAuditor`, `isBatchModelIndex`.
- **Scoring:** `auditScoreCommits`, `hasCommittedLM`, `auditScores`, `LMeligibleVote`, `hasAuditedLM` (all keyed `[gi][batchId][auditor][modelIndex]`).
- **Test data:** `encryptedTestDataKey[gi][batchId][auditor]`, `testDataCommitments[gi][batchId]`, `Is_testdataCIDs_Assigned[gi]`, `testDataDisputes[gi][batchId]`.
- **Rewards:** `giRewardPool[gi]`, `giRewardSnapshot[gi]`, `giTotalApprovedScore[gi]`, `giTotalAuditWeight[gi]`, `auditorGIWeight[gi][addr]`, `rewardClaimed[gi][addr]`, `claimable[addr]`, `treasuryAccrued`.

---

## 4. Access Control

| Caller | Functions |
|--------|-----------|
| Paired coordinator (`onlyTaskCoordinator`) | `updatePassScore`, `createAuditorsBatches`, `setTestDataAssignedFlag`, `finalizeEvaluation`, `slashAuditors`, `settleRewards`, `decrementAuditorRegistrations` |
| `owner()` (model owner) | `assignAuditTestDataset`, `reassignAuditTestDataset`, all setters |
| Assigned auditor (`onlyAssignedAuditor`) | `commitAuditScore`, `revealAuditScore` |
| Auditor of the disputed batch (`isBatchAuditor`) | `openTestDataDispute` |
| Any active validator | `registerDINAuditor` |
| Any address | `submitLocalModel`, `depositRewards`, `claimReward`, `claimRewards`, `closeExpiredDispute`, views |

---

## 5. Registration & Submissions

- **`registerDINAuditor(gi)`** — requires the coordinator state `DINauditorsRegistrationStarted`. Checks: not already registered, fewer than 300 registered (`TA_RegistrationCapReached`), `isValidatorActive` (`TA_AuditorNotActive`), stake ≥ the model floor (`TA_StakeBelowModelFloor`), and the concurrent-registration cap (`TA_ConcurrentRegistrationCapReached`). Then calls `incrementActiveRegistration` and emits `DINAuditorRegistered`.
- **`submitLocalModel(cid, gi)`** — state `LMSstarted`; one submission per address per GI; up to 10 000 per GI. No stake or registration needed.

---

## 6. Batches & Test Data

- **`createAuditorsBatches(gi, seed)`** (from the coordinator, state `LMSclosed`) — `seed` is the coordinator's locked `auditSeed[gi]` (see [DINTaskCoordinator §6.3](DINTaskCoordinator.md#63-batch-assignment-seed-lock)). A zero seed reverts with `TA_AuditSeedNotLocked`; the coordinator checks this too, so this is a second guard. The function then:
  1. filters `dinAuditors[gi]` to auditors still `isValidatorActive` at call time (`TA_NotEnoughAuditors` if fewer than `auditorsPerBatch` remain);
  2. shuffles the active auditors with `keccak256(seed, "AUD_ADDR")` and the model indexes with `keccak256(seed, "AUD_IDX")` (Fisher-Yates, in memory);
  3. greedily forms batches of 3 auditors × 3 models (the last batch may take 2). Leftover auditors and models are unused.

  Emits `AuditorsBatchAuto` per batch and `AuditorsBatchesCreated`. The seed comes from a block hash, so the residual trust assumptions in the coordinator doc apply here as well; one of them is specific to this function: a validator can still change the active pool by unstaking after the seed is locked and before this call.
- **`assignAuditTestDataset(gi, batchId, testDataCID, encryptedKeys[], commitment)`** (owner) — stores the encrypted test-data CID (`AES-256-GCM(K, rawCID ‖ Sign(ownerSK, rawCID))`) and one encrypted copy of `K` per auditor, in the batch's auditor order. Every auditor must have an X25519 key on `DinValidatorStake`. Also stores `commitment = keccak256(gi, batchId, keccak256(K), keccak256(plaintext))`. Blocked while the batch awaits reassignment.
- **`setTestDataAssignedFlag(gi, true)`** (from the coordinator, state `AuditorsBatchesCreated`) — one-shot flag. Informational only: nothing checks it before scoring starts.

---

## 7. Commit-then-Reveal Scoring

1. **Commit** (`LMSevaluationStarted`): `commitAuditScore(gi, batchId, modelIndex, commitHash)` with `commitHash = keccak256(abi.encode(score, vote, salt, auditor, gi, batchId, modelIndex))`, where `auditor` is the committing address. Binding the auditor and the slot means a peer can't copy the hash and replay the reveal, and one commit can't be reused for another model, batch or GI (issue No. 192). The caller must be an assigned, active auditor; one commit each; a zero hash is rejected.
2. **Reveal** (`LMSevaluationRevealStarted`): `revealAuditScore(gi, batchId, modelIndex, score, vote, salt)`. Checks the auditor is active, `score ≤ 100`, a commit exists, no prior reveal, and the hash matches. Records the score and vote, sets `hasAuditedLM`, increments `auditorGIWeight` / `giTotalAuditWeight` (the auditor reward basis), and tries to finalize eligibility.
3. **Eligibility** (`_tryFinalizeEligibility`): once revealed votes ≥ `minEligibilityQuorum`, `eligible = (yesVotes ≥ minEligibilityQuorum)`. With the defaults that means 2 "yes" votes out of 3.
4. **`finalizeEvaluation(gi)`** (from the coordinator's `closeLMsubmissionsEvaluation`, still in the reveal state): for each batch model with ≥ `minScoreQuorum` revealed scores, `finalMedianScore = median`, `evaluated = true`, `approved = eligible && median ≥ passScore`. The first time a model is approved, its median is added to `giTotalApprovedScore` (the client reward basis). Emits `AuditorScoreDeviation` for every revealing auditor (S3 shadow data). Returns `true` if at least one model reached quorum.
5. **`approvedModelIndexes(gi)`** feeds the coordinator's T1/T2 batch formation.

An auditor who commits but never reveals is treated as a non-voter: excluded from quorum and median, and slashed as a missed vote (§8).

---

## 8. Auditor Slashing — `slashAuditors(gi)`

From the coordinator in `T2AggregationDone`. For each batch auditor:

- **S1 — missed vote** on any batch model: `slashPartial(auditor, minStake × s1SlashFractionBps / 10 000, "AUD_NO_VOTE", gi)` (partial, with S5 recidivism escalation).
- **Otherwise, S3 — deviation**, only when `s3SlashingEnabled`: if any of their scores deviates from that model's median by more than `s3DeviationThreshold`, `slash(auditor, minStake, "AUD_SCORE_DEVIATION")`.

At most one slash per auditor per batch; S1 takes priority. Emits `AuditorSlashed(gi, batchId, auditor, reason, requested, actual)`.

---

## 9. Rewards

| Step | Function | Notes |
|------|----------|-------|
| Fund | `depositRewards(gi, amount)` — anyone | `gi` must be ≥ the current GI and non-zero; pulls DIN. The coordinator refuses to `startGI` an unfunded GI. |
| Settle | `settleRewards(gi, aggregatorTotalWeight)` — coordinator's `endGI` | Splits `giRewardPool[gi]` by `rewardSplit`. The treasury share (plus rounding dust) is forwarded in full to `slashTreasury()`, or burned if no treasury is set. Stores a snapshot. No participant loops. |
| Credit | `claimReward(gi)` — each participant, once per GI | Client: `clientPool × finalMedianScore / giTotalApprovedScore` (approved submissions only). Auditor: `auditorPool × auditorGIWeight / giTotalAuditWeight` (one unit per revealed vote). Aggregator: `aggregatorPool × aggregatorWeight / aggregatorTotalWeight` (read from the coordinator). Reverts `TA_NoRewardEarned` if all three are zero. |
| Withdraw | `claimRewards()` | Pull payment of the accumulated `claimable` balance. |

`DinEmission.fundGI` funds pools through the same `depositRewards` path, using freshly minted emission DIN.

---

## 10. Test-Data Disputes

Lets a batch auditor challenge the model owner's test data.

| Step | Who | Effect |
|------|-----|--------|
| `isEncryptionKeyEmpty(gi, batchId, auditor)` | View | Free check: an auditor who received no key has grounds to dispute |
| `openTestDataDispute(gi, batchId)` | An auditor of that batch (`TA_NotAssignedAuditor` otherwise) | Needs a stored commitment; pulls `disputeBondAmount` DIN (100 DIN by default); window = `disputeWindowBlocks` |
| `resolveTestDataDispute(gi, batchId, K, plaintextHash)` | Owner, within the window | The owner reveals `K` and the plaintext hash, and the commitment is recomputed. **Match →** dispute false: bond forfeited. **Mismatch →** upheld: bond returned; `disputePenaltyBps` of `giRewardPool[gi]` removed as a penalty; batch marked `pendingReassignment` |
| `closeExpiredDispute(gi, batchId)` | Anyone, after the window | The owner didn't answer, so the dispute is **upheld** with the same effects as a mismatch. Emits `DisputeExpired(gi, batchId)`, then `TestDataDisputeUpheld` |
| `reassignAuditTestDataset(…)` | Owner | New CID, keys and commitment for a batch pending reassignment |

Forfeited bonds and penalties are split 50% burned / 50% forwarded to `slashTreasury()`; both halves are burned if no treasury is set. `treasuryAccrued` is a running counter of everything routed out this way (including the burned part). No tokens are held against it.

The dispute is not bound to the caller (anyone can open one), and any caller can trigger the "upheld" branch with a wrong `K` (§13 No. 1).

---

## 11. What Is On-Chain

| Data | On-chain | Off-chain |
|------|---------|-----------|
| Model weights | ❌ | ✅ IPFS (`modelCID`) |
| Test dataset | ❌ (only the encrypted CID) | ✅ IPFS |
| Test-data key `K` | Only per-auditor encrypted copies (`encryptedTestDataKey`) | Decrypted client-side by each auditor with their X25519 key |
| Test-data content | Only the commitment `keccak256(gi, batchId, keccak256(K), keccak256(plaintext))` | — |
| Score / vote before reveal | Only the commit hash | `(score, vote, salt)` known to the auditor |
| Score / vote after reveal, final approval, rewards | ✅ | — |

---

## 12. Events

Registration & data: `DINAuditorRegistered`, `LocalModelSubmitted`, `AuditorsBatchAuto`, `AuditorsBatchesCreated`, `EncryptedTestDataKeysAssigned`, `TestDataCommitmentStored`. Scoring: `AuditScoreCommitted`, `AuditScoreSubmitted`, `EligibilityVoted`, `EligibilityFinalized`, `AuditorScoreDeviation`, `PassScoreUpdated`. Slashing: `AuditorSlashed`. Rewards: `RewardDeposited`, `RewardsSettled`, `RewardsClaimed`, `DinTokenSet`, `RewardSplitUpdated`. Parameters: `S1SlashFractionBpsUpdated`, `S3DeviationThresholdUpdated`, `S3SlashingEnabledUpdated`. Disputes: `TestDataDisputeOpened`, `TestDataDisputeResolvedFalse`, `TestDataDisputeUpheld`, `BatchPendingReassignment`, `DisputeExpired`.

---

## 13. Review Notes & Open Caveats

Read alongside the [foundry/src security review](../audits/foundry-src-security-review.md).

- **No. 1 — Fixed: a test-data dispute can no longer be won by the challenger alone.** `resolveTestDataDispute` used to be callable by anyone, and any commitment mismatch upheld the dispute. So any address could pass a junk `K` and win: bond back, the model owner's GI pool cut by `disputePenaltyBps`, and the batch blocked until reassignment. With a 0 default bond this was free and repeatable. Now only an auditor of the batch can open a dispute, the bond defaults to 100 DIN, and only the owner can resolve. An owner who doesn't answer within the window loses through `closeExpiredDispute` (issue No. 205). Remaining trust assumption: the owner reveals evidence about their own data, and a bad plaintext behind a correct `K` can't be proven on-chain. Decentralised adjudication is tracked in issue No. 181.
- **No. 2 — Fixed: commit hashes are now bound to the auditor.** The old hash, `keccak256(abi.encodePacked(score, vote, salt))`, carried no address, GI, batch or model. An assigned auditor could copy a peer's commit hash, wait for the peer's reveal, and replay it for a free vote. The hash now binds `msg.sender`, `gi`, `batchId` and `modelIndex` (§7), as the aggregation commits on the coordinator do (issue No. 192).
- **No. 3 — Committed-but-unrevealed is slashed as a liveness miss.** An auditor who commits and then withholds the reveal pays the S1 fraction (`AUD_NO_VOTE`, 30% of `minStake` by default). That is less than the full-`minStake` S3 slash a revealed outlier would pay once `s3SlashingEnabled` is on, so an auditor who sees they will be in the minority can choose not to reveal. Whether this case gets its own reason code and fraction is open in issue No. 201 (Part B).
- **No. 4 — Unclaimable remainders.** If no model is approved (`giTotalApprovedScore == 0`), or nobody reveals, or no aggregator weight exists, that role's pool share stays in the contract with no reclaim path.
- **No. 5 — `setTestDataAssignedFlag` gates nothing:** scoring can open before any test data is assigned.
- **No. 6 — Stale NatSpec and reused errors:** `slashAuditors` says S1 and S3 are both `minStake()` (S1 is now a fraction). Several comments call parameters "DAO-settable"; they are `onlyOwner`, i.e. set by the model owner. `setDisputePenaltyBps` reuses `TA_InvalidDisputeBond`, and `closeExpiredDispute` reuses `TA_DisputeWindowClosed` for "window still open".
- **No. 7 — `modelId` is fixed at construction**, before the registry assigns it (see [DINTaskCoordinator §10 No. 4](DINTaskCoordinator.md#10-review-notes--open-caveats)).
- **No. 8 — dincli lags this contract:** `dincli model-owner deploy task-auditor` still calls the older two-argument constructor (no `modelId`).
- **No. 9 — dincli auditor commit retry can lose the committed salt.** Rerunning `dincli auditor lms-evaluation evaluate --submit` generates a new salt and overwrites the local commit cache even when the on-chain commit already exists. The later reveal then fails the hash check and the auditor is slashed for a missed vote. Tracked in issue No. 202 (Part 1); until it is fixed, don't rerun the command for a GI that already has commits.

---

## 14. Change Log

### P3 (foundry)

- Commit-then-reveal scoring (`commitAuditScore` / `revealAuditScore`), replacing `setAuditScorenEligibility`; median-based scores.
- Per-GI reward pools with O(1) settlement snapshots and pull-based claims (BL-10), replacing `totalDepositedRewards`.
- Encrypted per-auditor test-data keys, content commitments, test-data disputes and reassignment.
- S1 partial slashing via `slashPartial`; S3 deviation slashing behind `s3SlashingEnabled`.
- Registration caps and floors, the active-registration counter, and the `modelId` constructor argument.
- Treasury shares and forfeitures forwarded to the platform treasury (`slashTreasury()`), replacing the per-contract treasury address (issue No. 152).
- `createAuditorsBatches` takes the coordinator's locked audit seed (issue No. 156 H-2, PR No. 191).
- The audit commit hash binds the auditor and the slot: `keccak256(abi.encode(score, vote, salt, msg.sender, gi, batchId, modelIndex))` replaces `keccak256(abi.encodePacked(score, vote, salt))` (issue No. 192). Function signatures and the ABI are unchanged; in-flight commits made under the old formula can't be revealed after the switch.
- Test-data disputes (issue No. 205): only an auditor of the batch can open one; `resolveTestDataDispute` is owner-only; `closeExpiredDispute` now upholds an unanswered dispute instead of forfeiting the bond; `disputeBondAmount` defaults to 100 DIN. `DisputeExpired` drops its `bondForfeited` field.
