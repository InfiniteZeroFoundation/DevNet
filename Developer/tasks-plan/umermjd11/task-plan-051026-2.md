# Task Plan: Full-GI Alignment: Contracts Check + Richer GI States, dincli Commands, Integration Suite on Foundry, GI Docs

**ID:** task-plan-051026-2
**Author:** Umer Majeed (@umermjd11)
**Reviewer:** @umeradl
**Created:** 2026-10-05
**Status:** Approved in PR #229 with [review amendments 1–6](https://github.com/InfiniteZeroFoundation/DevNet/pull/229#issuecomment-6000550646) and [reviewer decisions 1–4](https://github.com/InfiniteZeroFoundation/DevNet/pull/229#issuecomment-6000552418) (recommended options accepted). Forwarded 2026-10-06 → [task_061026_21](https://github.com/InfiniteZeroFoundation/DevNet/blob/develop/Developer/tasks/task_061026_21.md) (forwarding PR, linked on this PR)
**Proposed dates:** Oct 6 – Oct 17, 2026
**Repo:** https://github.com/InfiniteZeroFoundation/DevNet
**Base branch:** `develop`, written against commit `a1fcce2` (2026-10-05). The task contracts, dincli and `tests/dincli/` are unchanged since `740a613`, where the audit below was done. Line numbers are for that tree.
**Roadmap ref:** P3 onboarding (dincli), P3-6.3b (audit preparation), DevNet 2.0 launch readiness
**Companion plan:** [task-plan-051026-1](https://github.com/InfiniteZeroFoundation/DevNet/pull/219) (PR #219) covers the contract follow-ups (#201 A4, #180, #193). The two plans are split so they don't conflict; see [Coordination](#coordination-with-task-plan-051026-1).

**Flow:**
1. umeradl reviews this plan on its PR.
2. I apply the review amendments here.
3. Once it is approved, the plan is forwarded as **one** `Developer/tasks/task_DDMMYY_n.md` spec with one Part per TP, and this file is marked as forwarded.

---

## Why

The task contracts on `develop` have moved well past what dincli and the full-GI integration suite exercise:
- commit-then-reveal in all three scoring/aggregation phases;
- future-block batch seeds;
- encrypted test data;
- per-GI reward pools with pull claims;
- disputes;
- the `modelId` constructor argument.

Read-only audit at `740a613`:

- **The integration suite (`tests/dincli/`) can't pass with either toolchain.**
  - **Phase 1 fails.** It asserts a `proxyAdmin` key (`test_01_platform.py:135-137`, `:164`), but `DeployPlatform.s.sol:404-419` and `hardhat/scripts/deploy-platform.ts:55-64` write per-contract `proxyAdmin*` keys.
  - **Hardhat task contracts.** `constants.py:50` sets `ARTIFACT_BASE = hardhat/artifacts/contracts`, so the suite deploys the **hardhat** task contracts. Those are the pre-foundry versions:
    - no commit-reveal, rewards, seed lock or encrypted test data;
    - a 23-member `GIstates` enum (`hardhat/contracts/DINShared.sol:10-34`), while dincli mirrors foundry's 26 (`dincli/cli/utils.py:640`, `:669`).
  - **Tracked ABIs overwritten.** `dump-abi --official` (`test_01_platform.py:167-197`, `test_02_task_contracts.py:74-107`) overwrites the tracked foundry ABIs in `dincli/abis/` with hardhat ABIs.
  - **Steps missing from `test_04_gi.py`:**
    - funding the reward pool;
    - registering auditor encryption keys;
    - all three reveal phases;
    - `T2 set-score`, release slots and claims.
  - **Stale final-state fallback.** `test_04_gi.py:478` passes on the name (`"GIended" in result.stdout or "23" in result.stdout`). The stale piece is the `or "23"` fallback (and the "index 23" docstring); the real ordinal is 25.
- **dincli can't drive a full GI on the foundry contracts.**
  - **`model-owner deploy`** sends the old constructors (`deploy.py:35`, `:77`; BL-27, issue [#223](https://github.com/InfiniteZeroFoundation/DevNet/issues/223)) and never calls `setDinToken`.
  - **No dincli command for:**
    - `depositRewards` / `DinEmission.fundGI`, so `gi start` reverts with `TC_GIRewardPoolNotFunded`;
    - `registerEncryptionKey`, so `create-testdataset --submit` fails. The error at `auditor.py:39` even names a nonexistent `dincli auditor register-encryption-key`;
    - `releaseGIRegistrationSlots` (BL-28);
    - `claimReward`/`claimRewards`;
    - both dispute families.
- **The GI state machine says too little about where a GI is.** Three steps change no state:
  - **Audit seed:** waiting for its block, or locked.
  - **Test data:** batches exist, but test data may or may not be assigned. `startLMsubmissionsEvaluation` (`DINTaskCoordinator.sol:532-538`) **doesn't check** that test data was assigned; `setTestDataAssignedFlag` (`:519-527`) only forwards a flag.
  - **Aggregation seed:** waiting, or locked.
- **CI never runs the suite** (`ci.yml:136-137` runs `-m "not integration"`). That follow-up is [#228](https://github.com/InfiniteZeroFoundation/DevNet/issues/228) and isn't part of this plan.
- **The public GI docs are stale**: wrong command names and missing funding/key/seed/reveal steps (see TP-5).

**Discussion #216 follow-ups.** [Discussion #216](https://github.com/InfiniteZeroFoundation/DevNet/discussions/216#discussioncomment-18761447) closed task_021026_19 and left these follow-ups. All of them are covered here:

| Follow-up | TP |
|---|---|
| `model-owner deploy` still uses the old constructors (no `modelId`) | TP-3 (closes [#223](https://github.com/InfiniteZeroFoundation/DevNet/issues/223) with BL-28) |
| No dincli commands for depositing/claiming rewards, `registerEncryptionKey` or disputes | TP-3 |
| `din-workflow.md` still lists 4 contracts and `withdraw` | TP-5 |
| Old command names in `roles/clients.md`, `roles/auditors.md`, `roles/model-owner.md`, `model-workflow.md` | TP-5 |
| `setup.md`'s broken `@main#subdirectory=dist` install line | TP-5 |
| `ROADMAP.md:19` (deploy-blocker sentence, wrong since PR #211) | TP-5 |

The Parts run in this order: **check the contracts → update dincli → make the suite run a complete GI → update the docs.**

---

## Sequencing

| Item | Touches | Conflicts with | Rule |
|---|---|---|---|
| TP-1 | Read-only audit, recorded in the spec. Two comment/text fixes (`DINShared.sol:30-34`, `utils.py` state 24 text) | — | First |
| TP-2 | `DINShared.sol` enum, `DINTaskCoordinator.sol` (3 state transitions + the eval-start gate), `DINTaskAuditor.sol` if a gate reads the flag, foundry tests, `dincli/cli/utils.py` mirrors and every dincli state gate, `dincli/abis/`, `DINShared.md`, `DINTaskCoordinator.md` | Plan 1 (`DINShared.sol` interface edit for #180; `DINTaskAuditor.json` ABI); PR #29 (subgraph enum mapping) | After TP-1. **Before** TP-3/TP-4, so the commands and the suite are built on the final state machine |
| TP-3 | `dincli/cli/modelownerd/deploy.py`, new dincli commands, `dincli/abis/DinEmission.json`, `cli/context.py` helper, `dinrep` approval check, unit tests | — | After TP-2 |
| TP-4 | `tests/dincli/**`, `tests/dincli/NOTES.md`, `dincli-testing-guide.md` | — | After TP-3 |
| TP-5 | `Documentation/public/**`, `CLAUDE.md`, `DINShared.md` §2.2 diagram | — | Last. It documents the final commands and states |

One PR per TP (TP-1's two text fixes can go with TP-2). Rebase on `develop` after each merge, with no stacked branches.

---

# TP-1 — Contracts check: what a complete GI needs

A read-only pass over every owner and role GI function in `DINTaskCoordinator`, `DINTaskAuditor`, `DinValidatorStake` and `DinEmission`. It is checked against `DINTaskCoordinator.md` §6 and the 26 `GIstates`, and its output is recorded in the spec as the reference table for TP-3 to TP-5.

**Preconditions a full GI needs on the foundry contracts:**

| Precondition | Where | Without it |
|---|---|---|
| `modelId` constructor argument on both task contracts | `DINTaskCoordinator.sol:290`, `DINTaskAuditor.sol:406` | The deploy fails at ABI encoding (BL-27) |
| `setDinToken` on the auditor (and the coordinator, for dispute bonds) | `DINTaskAuditor.sol:440`, `DINTaskCoordinator.sol:1307` | `depositRewards` and claims can't move DIN |
| GI reward pool funded for GI N+1 before each `startGI` | `DINTaskCoordinator.sol:379` → `DINTaskAuditor.depositRewards` (`:481`) or `DinEmission.fundGI` (`DinEmission.sol:174`) | `TC_GIRewardPoolNotFunded` |
| Every batch auditor has an X25519 key on `DinValidatorStake` | `registerEncryptionKey` (`DinValidatorStake.sol:501`); checked at `DINTaskAuditor.sol:1000-1001` | `TA_AuditorEncryptionKeyNotRegistered` when test data is assigned |
| Seed blocks get mined | `disputeSeedDelay` = 7 blocks. dincli polls (`utils.py:998-1080`), and anvil `--block-time 2` mines | The seed lock hangs on a chain that doesn't mine on its own |
| Each of the three reveal windows is opened by the owner | `start*Reveal` | `close` / `finalize` revert |

**dincli coverage**, from the audit (full table in the spec): commands exist for deploy (wrong constructors), slashers, genesis, registry, start, registrations, LMS, seed locks (also automatic), batches, test data, every commit, reveal and close, set-score, slash and end. These are **missing**:
- `setDinToken`;
- reward deposit / emission funding;
- `registerEncryptionKey`;
- release slots;
- claims;
- both dispute families;
- owner parameter setters (out of scope here).

**Text fixes found along the way:**
- `DINShared.sol:30-34` says "24-member table"; it's 26 today, and more after TP-2.
- `dincli/cli/utils.py` state 24's description reads "Validators slashed"; it should say aggregators.

**Gap found:** evaluation can start without test data (`startLMsubmissionsEvaluation` checks only `AuditorsBatchesCreated`). TP-2 closes it.

Any other blocker to a full GI that the check finds gets fixed in TP-2, or raised on its own issue if it needs a decision. I won't work around it in dincli.

**Estimate:** 0.5 day.

---

# TP-2 — Richer GI states

With more states, `dincli task gi show-state` (and the subgraph, and any dashboard) can tell exactly where a GI is. Each new state is **set by the function that already performs the step**, so a GI needs no extra owner transactions.

| New state | Inserted | Set by | Gate change |
|---|---|---|---|
| `AuditSeedLocked` | between `LMSclosed` and `AuditorsBatchesCreated` | `lockAuditSeed` (`DINTaskCoordinator.sol:1483`; anyone). Only on a successful lock, not on a re-anchor | `createAuditorsBatches` requires `AuditSeedLocked` instead of `LMSclosed` plus a non-zero seed |
| `AuditTestDataAssigned` | between `AuditorsBatchesCreated` and `LMSevaluationStarted` | `setTestDataAssignedFlag(gi, true)` (`:519`) | `startLMsubmissionsEvaluation` requires it. To **close the gap**, the auditor side of `setTestDataAssignedFlag` (`DINTaskAuditor.sol:1017-1029`) also checks that **every batch** of the GI has a stored commitment (`testDataCommitments[gi][b] != 0`, written by `assignAuditTestDataset`) and otherwise reverts with a new `TA_TestDataNotAssigned`. Without that check the flag is only the owner's own claim. The flag is already one-way (`TA_FlagMustBeTrue`, `TA_FlagAlreadySet`) |
| `AggSeedLocked` | between `LMSevaluationClosed` and `T1nT2Bcreated` | `lockAggSeed` (`:1459`) | `autoCreateTier1AndTier2` requires `AggSeedLocked` |

**Priority if the coordinator budget runs short** (Decision 1, option B): `AuditTestDataAssigned` first, because it closes a real gap, then `AuditSeedLocked`, then `AggSeedLocked`. The table above is in lifecycle order, which is also the enum insertion order.

**Considered, not recommended** (listed for the reviewer):
- **A "reward pool funded" state.** Funding happens on the auditor contract, anyone can do it, and it targets the *next* GI, so it doesn't fit the coordinator's per-GI state. A `isGIFunded(gi)` view, or the existing `giRewardPool(gi)` getter that dincli reads, covers it.
- **A "test-data dispute pending" state.** Disputes are per batch and can overlap the evaluation phases. That stays as dispute records, not GI state.
- **A "rewards settled / claim window" state.** `endGI` settles the pool and claims stay open indefinitely, so `GIended` already means that.

The review may add others. TP-1 lists every step that changes no state.

**Constraints:**
- **Insert at the lifecycle position, not at the end**, as PR #63 and PR #197 did. Every later ordinal shifts: `GIended` goes from 25 to 28 with all three states.
- **Everything that encodes ordinals or names changes in the same PR:**
  - `dincli/cli/utils.py` `states`/`stateDescription`;
  - every dincli state gate (grep for `GIstateToStr` and name comparisons);
  - `DINShared.md` §2.1/§2.2;
  - `DINTaskCoordinator.md` §6;
  - foundry tests that assert ordinals or names;
  - bundled ABIs (`dump-abi --official`).
- **Post the new ordinal table on PR #29** (the subgraph regenerates its `GIstates` mapping). Don't push to that branch.
- **Size.** `DINTaskCoordinator` has a 1,079 B margin. Measure each state on its own and together. If they don't all fit with the CI gate green, keep them in priority order (above) and replace the rest with views, then report it in the PR. The commitment check costs **`DINTaskAuditor` +75 B** (measured on `a1fcce2`). Together with task_061026_20's TP-1 + TP-2, the auditor comes to 22,575 B (2,001 B margin, warn band). task_061026_20 has the shared budget table and the ways back out of the warn band: the fold review, and dropping `Is_testdataCIDs_Assigned` once this state guards the double-set.
- **`lockAuditSeed` / `lockAggSeed` stay permissionless.** The state change happens inside the existing lock path, after the seed is stored.

**Tests:**
- Each transition happens.
- `createAuditorsBatches` / `autoCreateTier1AndTier2` revert before the lock.
- `startLMsubmissionsEvaluation` reverts until test data is assigned (a new regression test for the gap).
- With one batch's test data unassigned, `setTestDataAssignedFlag` reverts with `TA_TestDataNotAssigned`, and evaluation can't start.
- A re-anchor leaves the state unchanged.
- The full lifecycle test walks every ordinal.

**Estimate:** 1.5 days.

---

# TP-3 — dincli commands for a complete GI

**Deploy (BL-27). TP-3 closes issue [#223](https://github.com/InfiniteZeroFoundation/DevNet/issues/223)** (BL-27 + BL-28).
- `model-owner deploy task-coordinator` / `task-auditor` get `--model-id`. The default is `DINModelRegistry.totalModels()`, the ID the next approval assigns (`DINModelRegistry.sol:237`), with a warning that the guess only holds if no other request is approved first.
- The auditor deploy reads `modelId()` from the coordinator and refuses on a mismatch.
- Both deploys call `setDinToken`.
- Fix the latent `NameError` when the `stake` entry is missing (`deploy.py:27-28`, `:63-64`).
- `dinrep registry approve-registration-request` compares the request's contracts' `modelId()` with `totalModels()`. On a mismatch it refuses, unless `--force` is passed ([Decision 2](#reviewer-decisions)).

**New commands:**

| Command | Calls | Notes |
|---|---|---|
| `dincli model-owner rewards deposit <model_id> --gi N --amount <DIN>` | approve + `depositRewards` | Anyone can fund |
| `dincli model-owner rewards fund-emission <model_id> --gi N` | `DinEmission.fundGI` | Adds `dincli/abis/DinEmission.json` and `get_deployed_din_emission_contract` (`din_info` already has the `emission` key) |
| `dincli rewards claim <model_id> --gi N` / `dincli rewards withdraw <model_id>` | `claimReward(gi)` / `claimRewards()` | All roles. First checks that `giRewardSnapshot(gi).settled` is true and `rewardClaimed` is false |
| `dincli auditor register-encryption-key` | `DinValidatorStake.registerEncryptionKey` | Generates the X25519 key **per wallet** (for example `auditor_x25519_<address>.key`, chmod 600). Today it's one shared `auditor_x25519.key`, which breaks several `--demokey` auditors on one machine. `_load_auditor_x25519_key` (`auditor.py:33-41`) is updated to match, and the owner key at `auditor_batches.py:170-177` also gets chmod 600 |
| `dincli model-owner gi release-slots <model_id> --gi N` | `releaseGIRegistrationSlots` | BL-28 |
| `dincli auditor dispute-test-data`, `dincli model-owner disputes resolve-test-data / reassign-test-data`, `… disputes close-expired` | test-data dispute functions (`DINTaskAuditor.sol:1480`, `:1524`, `:1557`, `:1601`) | Bond approval first |
| `dincli aggregator dispute`, `dincli model-owner disputes resolve-aggregation / settle-recomputation`, `… expire`, `… claim-bond` | coordinator dispute functions (`:1368`, `:1535`, `:1609`, `:1671`, `claimDisputeBond` at `:1583`) | S4 |

**Fail fast instead of reverting:**
- `gi start` checks `giRewardPool(next GI) > 0` and points to `rewards deposit`.
- `create-testdataset --submit` checks every batch auditor's key and names the ones that are missing.

**Reuse:**
- `build_and_send_tx` (`dincli/cli/utils.py:947`);
- the `ctx.obj.get_deployed_din_task_*_contract(model_id)` lookups (`cli/context.py:339`, `:357`);
- an `approve_din(ctx, spender, amount)` helper taken from the inline approve in `dintoken.stake_dintokens` (`dincli/cli/dintoken.py:71-128`).

**Tests:** one pytest per command group in the `tests/test_dinrep_add_slasher.py` style (`SimpleNamespace` context, `build_and_send_tx` monkeypatched). They check the call arguments, approve-before-act, and the fail-fast checks.

**Estimate:** 3 days. The dispute commands can be split out ([Decision 4](#reviewer-decisions)).

---

# TP-4 — The integration suite runs a complete GI on the foundry contracts

**Toolchain:**
- `ARTIFACT_BASE` → `foundry/out`. It's the same `X.sol/X.json` layout, and `get_contract_instance` already reads `bytecode.object` (`contract_utils.py:150-152`).
- `npx hardhat compile` runs only when `PLATFORM_DEPLOY_TOOLCHAIN=hardhat`. The hardhat task contracts leave the GI path; hardhat stays an option for platform deploy only.
- The `dump-abi` tests write to `DIN_TEMP` (`--output`), not `--official`, so the suite never rewrites tracked files.
- Phase 1 asserts the per-contract `proxyAdmin*` keys.

**`test_04_gi.py` walks the complete GI**, asserting the state after each phase with the existing (unused) `_gi_state` helper (`:52-58`):

1. `setDinToken` (from deploy) → `rewards deposit` (or `fund-emission`) → `gi start`
2. Aggregator and auditor registration → `auditor register-encryption-key` for each auditor
3. LMS → `auditor lock-seed` (`AuditSeedLocked`) → `auditor-batches create` → `create-testdataset --submit` (`AuditTestDataAssigned`)
4. `lms-evaluation start` → `evaluate --submit` → `lms-evaluation start-reveal` → `auditor lms-evaluation reveal` → `close`
5. `aggregator lock-seed` (`AggSeedLocked`) → `create-t1nt2-batches`
6. `T1 start` → `aggregate-t1 --submit` → `T1 start-reveal` → `reveal-t1` → `T1 close`, then the same for T2 → `T2 set-score`
7. `slash auditors` → `slash aggregators` → `gi end` (assert `GIended` by name and its new ordinal)
8. `rewards claim` / `withdraw` for one client, one auditor and one aggregator (assert the DIN balance goes up) → `gi release-slots`

**Optional second GI** ([Decision 3](#reviewer-decisions)): fund GI 2 → `gi start` from `GIended`. This proves the loop and the slot release.

**Docs:** `tests/dincli/NOTES.md` (the INTERIM hardhat notes and the GI map) and `Documentation/technical/testing/dincli-testing-guide.md`:
- 7 platform contracts, not 4;
- no hardhat compile;
- the new phases;
- the account ranges, which really are `range(2, 11)` for clients.

**Verification:** run `pytest tests/dincli/ -v -x -m integration --tb=short` locally (anvil, IPFS, Docker) through the end, and paste the run summary in the PR. CI comes later in #228.

**Estimate:** 2 days.

---

# TP-5 — GI docs

These docs walk the GI or the role commands. Each is brought to the final commands and states:

| Doc | Main fixes |
|---|---|
| `Documentation/public/workflows/model-workflow.md` | foundry artifacts plus `--model-id`, `create-genesis-model`/`submit-genesis-model`, `task model-owner register-request` plus DIN-Rep approval, `update-manifest-request`, funding before `gi start`, `train-lms` → `submit-lm`, auditor key prerequisite, the three reveal windows, seed-lock states, claim and release-slots after `gi end` |
| `Documentation/public/roles/model-owner.md` | `get-registry-fee`, the `task model-owner …` registry commands (replacing the nonexistent `model-owner registry …`), genesis names, funding, `start-reveal` (evaluation, T1, T2), `create-testdataset --submit`, claim, release slots |
| `Documentation/public/roles/auditors.md` | `register-encryption-key`, `lms-evaluation reveal`, claim, disputes |
| `Documentation/public/roles/clients.md` | `train-lms` then `submit-lm`, claim |
| `Documentation/public/roles/aggregators.md` | claim, `reveal-t2 --batch`, dispute |
| `Documentation/public/getting-started.md` | `aggregator show-t1/t2-batches`, auditor key + reveal + `lock-seed`, `submit-lm`, the outdated "rewards not the focus" line |
| `Documentation/public/manifest.md`, `guides/keystore-migration.md` | genesis command name; `train-lms --submit` |
| `Documentation/public/workflows/din-workflow.md` | 7 contracts; `withdraw` → `sweep-fees`; the fee value conflict |
| `Documentation/technical/contracts/DINShared.md` §2.2 | diagram with the funding gate, seed and test-data states |
| `CLAUDE.md` | 7 platform contracts; GI summary with funding, seed locks, keys, reveals, claim and release slots |
| `Documentation/public/setup.md` | Option B's `pip install git+…@main#subdirectory=dist` can't build: `dist/` on `main` holds only wheels and sdists, with no `pyproject.toml`. Replace it with a working install (e.g. `pip install "git+https://github.com/InfiniteZeroFoundation/DevNet.git@main"` from the repo root, or a direct wheel URL), and bring Option A's wheel name (`dincli-0.1.0`) to the current version |
| `Developer/ROADMAP.md:19` | Rewrite the deploy-blocker sentence ("24,585 B … 9 B over EIP-170") for the PR #211 sizes and the CI size gate. The "DevNet 3.0" vs "DevNet 2.0" naming is flagged in the PR for Umer to decide |

Flagged for the reviewer, not changed here: the node README's "local Hardhat devnet" line.

After merge: a wiki follow-up for the pages that say "no dincli command yet".

`python3 .github/scripts/check_doc_links.py Documentation` and `… Developer` must be green.

**Estimate:** 1.5 days.

---

## Coordination with task-plan-051026-1

- **`DINShared.sol`.** TP-2 here edits the `GIstates` enum. Plan 1's #180 adds `isDINAggregator` to `IDINTaskCoordinator` in the same file. The sections differ; whichever PR merges second rebases.
- **`dincli/abis/DINTaskAuditor.json`.** Both plans regenerate it; the second to merge regenerates on top of the first.
- **Getters.** Plan 1's TP-1 recommended set (`auditBatches`, `dinAuditors`, `Is_testdataCIDs_Assigned`, `auditorGIWeight`) isn't used by dincli or the suite. TP-3 here reads `giRewardSnapshot`, `rewardClaimed` and `testDataDisputes`, which plan 1 keeps public. If TP-2 makes the test-data flag redundant, `Is_testdataCIDs_Assigned` can go entirely. Coordinate in whichever PR lands second.
- **#180 guard.** The suite uses disjoint accounts (aggregators 11–22, auditors 50–58), so the guard doesn't affect it. Once plan 1 has landed, TP-4 adds a negative check.
- **PR #218.** `P3Adversarial.t.sol` runs the full GI lifecycle in foundry. If it merges before TP-2, TP-2 updates any state ordinals or names it asserts.

---

## Reviewer decisions

Resolved 2026-10-06 on the [decisions comment](https://github.com/InfiniteZeroFoundation/DevNet/pull/229#issuecomment-6000552418). The reviewer's recommended option was accepted each time.

1. **New GI states: B.** All three, with `AuditTestDataAssigned` first in priority, then `AuditSeedLocked`, then `AggSeedLocked`. `AuditTestDataAssigned` only counts if `setTestDataAssignedFlag` checks that every batch has a stored commitment (review amendment 5). The `flag=false` question is dropped, because the flag is already one-way.
2. **`modelId` check: A.** It is done in dincli at approval: `approve-registration-request` refuses on a mismatch unless `--force` is passed. A contract-side check in `DINModelRegistry.approveModel` is a mainnet-registry follow-up, in the same area as BL-34 / issue #224.
3. **Suite: A.** One complete GI. A second GI is added afterwards as an optional test, marked `integration` + slow and kept out of CI.
4. **Dispute commands: A.** They stay in TP-3 and are built against the PR #215 dispute shape: owner-only resolve, an unanswered dispute upheld on expiry, no penalty after settlement, and `TA_RewardsAlreadySettled`.

---

## Deferred (not in this plan)

| Item | Reason |
|---|---|
| [#228](https://github.com/InfiniteZeroFoundation/DevNet/issues/228) | Running the integration suite in a separate CI job. It follows once TP-4 passes a complete GI |
| #201 A4, #180, #193 | In [task-plan-051026-1](https://github.com/InfiniteZeroFoundation/DevNet/pull/219) (PR #219) |
| Owner parameter setters in dincli (`setDisputeParams`, `setS1/S2/S3*`, `setRewardSplit`, `setNetworkFeeFloor`) | Not needed for a complete GI. Revisit with #155's parameter decisions |
| BL-29 to BL-33, #194, #78, #181, #178 | Same reasons as in plan 1's Deferred table |
