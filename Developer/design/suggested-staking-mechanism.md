Affected contracts: `DinValidatorStake.sol`, `DINTaskCoordinator.sol`, `DINTaskAuditor.sol`, `DINShared.sol`, `DinCoordinator.sol`

# DIN Protocol: Suggested Production Staking and Slashing Mechanism

## Purpose
This document defines a production-hardening specification for the DIN validator staking and slashing flow. It is intended to replace the current prototype-level behavior with a validator lifecycle that is resistant to mid-round exits, stale registrations, non-executable slashes, and incomplete penalty settlement.

The scope is limited to:
- `DinValidatorStake.sol`
- `DINTaskCoordinator.sol`
- `DINTaskAuditor.sol`
- shared interfaces in `DINShared.sol`
- the administrative coupling exposed through `DinCoordinator.sol`

## Executive Summary
The current implementation is not production-grade because it allows immediate unstaking, performs only partial eligibility checks, has incomplete auditor slashing, and treats slash deductions as accounting-only without finalized settlement semantics.

The production design must enforce five properties:
- stake remains slashable for a bounded period after participation;
- active eligibility is revalidated at registration, assignment, and submission time;
- slashing is non-blocking and executable even if a validator is already partially underwater;
- auditor and aggregator penalties are explicit, deterministic, and role-specific;
- validator lifecycle transitions are formalized instead of inferred from raw balance.

## Current Implementation Findings

The following issues are present in the current contracts and must be treated as concrete correctness bugs, not just optimization opportunities.

### 1. Blacklisted validators can still register
- `DINTaskCoordinator.registerDINaggregator()` checks `getStake(msg.sender) >= minStake`.
- `DINTaskAuditor.registerDINAuditor()` checks `getStake(msg.sender) >= minStake`.
- `DinValidatorStake.getStake()` returns raw stake and does not enforce `!blacklisted`.
- `DinValidatorStake.isValidatorStaked()` is the function that actually combines minimum stake and blacklist status.

Result:
- a blacklisted validator with enough existing stake can still register as an aggregator or auditor.

Required correction:
- replace registration-time `getStake()` checks with validator-activity checks exposed by the stake contract;
- treat raw stake as informational only, never as an eligibility gate.

### 2. Eligibility is not revalidated after registration
- Aggregator assignment currently pulls from `dinAggregators[_GI]`.
- Auditor assignment currently pulls from `dinAuditors[_GI]`.
- Submission paths check assignment membership, but not whether the validator is still active.

Result:
- a validator can register, then unstake or be blacklisted, and still be assigned and allowed to submit.

Required correction:
- revalidate active status during:
- registration;
- batch creation;
- submission;
- optionally slash/finalization for defense in depth.

### 3. Slashing can stall GI completion
- `DINTaskCoordinator.slashAggregators()` calls `DinValidatorStake.slash()` directly for each slashable validator.
- the current `DinValidatorStake.slash()` reverts if the validator is no longer registered or if its stake is below the requested amount.

Result:
- one already-inactive or undercollateralized validator can revert the whole slashing loop and block transition to `AggregatorsSlashed`.

Required correction:
- slash execution must be non-blocking;
- the stake contract must return actual slashed amount instead of reverting on partial shortfall;
- coordinator loops must continue even when actual slash amount is zero.

### 4. Auditor slashing is not implemented
- `slashAuditors()` is a placeholder.

Result:
- auditors currently face no complete on-chain penalty path for abstaining or misbehavior.

Required correction:
- implement explicit auditor offense classification and per-auditor slash handling.

### 5. Stake thresholds can drift
- `DinValidatorStake` has `MIN_STAKE`.
- `DINTaskCoordinator` has local `minStake`.
- `DINTaskAuditor` has local `minStake`.
- `DINTaskAuditor.Params` also has `minAuditorStake`.

Result:
- the codebase has multiple stake thresholds and the documentation claim of perfect alignment is not guaranteed.

Required correction:
- keep the minimum stake source of truth only in `DinValidatorStake.sol`;
- expose it by interface to all role contracts.

### 6. Existing staking documentation overstates blacklist enforcement
The current `staking-mechanism.md` states that blacklisting completely neutralizes bad actors. That is stronger than the actual implementation because validators already holding stake or already registered are not consistently neutralized across registration, assignment, and submission paths.

Required correction:
- update documentation to state current behavior precisely;
- only claim complete neutralization once all role-contract checks are aligned with stake-contract active status.

## Minimum Fix Set For Current Contracts

Before the full production redesign in later sections, the current codebase should implement the following minimum patch set.

### `DINShared.sol`
- add `isValidatorStaked(address)` to `IDinValidatorStake`;
- optionally add `minStake()` if stake threshold consolidation begins immediately.

### `DinValidatorStake.sol`
- keep raw `getStake()` for informational reads only;
- expose `isValidatorStaked()` through the shared interface;
- change `slash()` so that it can support non-blocking partial slashes in the next step of hardening.

### `DINTaskCoordinator.sol`
- replace `getStake()` registration gate with `isValidatorStaked()`;
- filter inactive validators out of `autoCreateTier1AndTier2()`;
- reject inactive assigned validators in `submitT1Aggregation()` and `submitT2Aggregation()`;
- make `slashAggregators()` robust against already-inactive or already-underwater validators.

### `DINTaskAuditor.sol`
- replace `getStake()` registration gate with `isValidatorStaked()`;
- filter inactive validators out of `createAuditorsBatches()`;
- reject inactive assigned auditors in `setAuditScorenEligibility()`;
- remove the drift between `minStake` and `params.minAuditorStake`.

### Immediate policy decision required
For validators that were active at registration but lose eligibility later, the implementation must choose one of these two behaviors and apply it consistently:
- remove them from future assignment and treat them as non-participants;
- keep them accountable for already-assigned work, but reject new submissions once inactive.

Recommended minimum behavior:
- filter them out before assignment if already inactive;
- if they become inactive after assignment, keep them slashable for the assigned duty and reject further submissions.

## Design Goals
- Preserve economic security during and after each GI.
- Prevent validators from escaping penalties through fast unstake or blacklist timing.
- Eliminate stale registered sets being treated as active participants.
- Ensure that one faulty validator cannot block round completion or slashing.
- Keep emergency controls available while reducing arbitrary admin impact on active stake.
- Make slashing results auditable on-chain through events and explicit accounting.

## Non-Goals
- This document does not redesign DIN tokenomics.
- This document does not define governance for DAO voting.
- This document does not define cryptographic verification of aggregation correctness beyond the existing task-layer assumptions.

## Required Contract Model

### 1. `DinValidatorStake.sol`: Convert from balance vault to validator state machine

The stake contract must become the single source of truth for validator status.

Replace the current `ValidatorInfo` model with a lifecycle-aware structure:

```solidity
enum ValidatorStatus {
    None,
    Active,
    Exiting,
    Jailed,
    Blacklisted
}

struct ValidatorInfo {
    uint256 activeStake;
    uint256 pendingWithdrawals;
    uint64 withdrawAvailableAt;
    uint64 jailedUntil;
    ValidatorStatus status;
}
```

### 2. Core invariants
- Only `Active` validators are eligible for new registration, batch assignment, or submission.
- `Exiting` validators are not eligible for new work, but their pending withdrawal remains slashable until the exit window ends.
- `Jailed` validators are not eligible for new work until reactivated.
- `Blacklisted` validators are permanently ineligible unless governance explicitly unblacklists them.
- `activeStake + pendingWithdrawals` is the slashable base while the unbonding window is open.

### 3. Minimum required stake semantics
- `MIN_STAKE` must remain in one contract only: `DinValidatorStake.sol`.
- Coordinator and auditor contracts must not maintain independent hardcoded minimums.
- Shared interface must expose:

```solidity
function minStake() external view returns (uint256);
function isValidatorActive(address validator) external view returns (bool);
function slashableStakeOf(address validator) external view returns (uint256);
```

Any role contract using local `minStake` copies is out of spec.

## Validator Lifecycle

### 1. Stake
`stake(uint256 amount)` must:
- reject blacklisted validators;
- add to `activeStake`;
- set status to `Active` if resulting stake is `>= MIN_STAKE`;
- emit the post-operation stake and status.

### 2. Start exit
Replace immediate `unstake()` with:

```solidity
function requestUnstake(uint256 amount) external;
```

Behavior:
- moves `amount` from `activeStake` to `pendingWithdrawals`;
- sets `withdrawAvailableAt = block.timestamp + UNBONDING_PERIOD`;
- if remaining active stake falls below `MIN_STAKE`, status becomes `Exiting` unless already jailed or blacklisted;
- pending withdrawals remain slashable until claimed.

### 3. Finalize exit
Add:

```solidity
function claimUnstaked() external;
```

Behavior:
- only allowed after `withdrawAvailableAt`;
- transfers the matured `pendingWithdrawals`;
- if no active stake remains, status becomes `None`.

### 4. Jail
Add:

```solidity
function jailValidator(address validator, uint64 until) external onlySlasherContract;
function reactivateValidator() external;
```

Behavior:
- jailing is used for liveness or procedural faults;
- jailed validators cannot register or submit work;
- reactivation requires `block.timestamp >= jailedUntil` and `activeStake >= MIN_STAKE`.

### 5. Blacklist
Blacklisting remains an emergency governance action, but must:
- immediately set status to `Blacklisted`;
- freeze new stake, new work, and withdrawals until governance policy decides whether emergency withdrawals are allowed;
- not erase slashability of existing funds.

## Slashing Semantics

### 1. Slash accounting must be real
The current accounting-only deduction is out of spec. Slashed stake must have an explicit destination:
- burn;
- treasury;
- insurance / dispute reserve;
- validator reward redistribution pool.

Recommended initial production path:
- transfer slashed DIN to a treasury or insurance sink address controlled by governance.

Required interface:

```solidity
function slash(
    address validator,
    uint256 amount,
    bytes32 reason
) external returns (uint256 slashedAmount);
```

Rules:
- slash up to the available slashable amount;
- do not revert solely because the validator has less than `amount`;
- return actual amount slashed;
- emit the requested amount, actual amount, reason, and caller.

This change is mandatory to avoid round-stalling from partial balances.

### 2. Slashing must be non-blocking
`slash()` must not revert for these normal conditions:
- validator already below target slash amount;
- validator already exiting;
- validator already jailed;
- validator has partial stake remaining.

It may revert only for:
- unauthorized caller;
- invalid validator address;
- zero amount;
- internal transfer/accounting failure.

### 3. Suggested slash reasons
Use canonical `bytes32` reasons:
- `AGG_T1_NO_SUBMISSION`
- `AGG_T1_BAD_CONSENSUS`
- `AGG_T2_NO_SUBMISSION`
- `AGG_T2_BAD_CONSENSUS`
- `AUD_NO_VOTE`
- `AUD_LATE_VOTE`
- `AUD_OUTLIER_SCORE`
- `AUD_BAD_ELIGIBILITY_VOTE`
- `EMERGENCY_BLACKLIST_ENFORCEMENT`

## `DINTaskCoordinator.sol` Production Requirements

### 1. Registration checks
`registerDINaggregator(uint256 gi)` must use `isValidatorActive(msg.sender)`, not `getStake(msg.sender)`.

### 2. Batch construction must filter stale validators
`autoCreateTier1AndTier2()` must not use the raw registration list as the assignment set. It must:
- iterate the registered pool;
- retain only validators where `isValidatorActive(validator) == true`;
- optionally emit a `ValidatorSkippedForInactivity` event for filtered participants.

This is required because registration is historical, but assignment eligibility is real-time.

### 3. Submission gates
`submitT1Aggregation()` and `submitT2Aggregation()` must require:
- assigned validator;
- current GI state is correct;
- validator is still active and not blacklisted/jailed/exiting.

Recommended error:
- `TC_ValidatorNotActive()`

### 4. Fault classification
The coordinator must distinguish:
- no submission;
- late submission if deadlines are introduced;
- mismatched CID against final consensus;
- unassignable due to becoming inactive before work began.

If a validator became inactive before batch creation, it must not be assigned.
If it became inactive after assignment but before submission, the protocol should:
- mark it as failed participation;
- slash if policy says active commitment had already started;
- otherwise jail without economic penalty if the design chooses a softer liveness response.

This choice must be fixed in code and docs. For production, recommended policy is:
- once assigned to a batch, the validator remains accountable for that batch until GI close or slash resolution.

### 5. Aggregator slashing execution
`slashAggregators(uint256 gi)` must:
- attempt every slash independently;
- never revert the entire loop because one slash partially succeeds or returns zero;
- aggregate totals and emit per-validator results.

Required event:

```solidity
event AggregatorSlashed(
    uint256 indexed gi,
    uint256 indexed batchId,
    address indexed aggregator,
    bytes32 reason,
    uint256 requested,
    uint256 actual
);
```

### 6. Deadlines
Production slashing should not rely purely on manual owner sequencing. Add explicit timestamps for:
- registration close;
- T1 submission deadline;
- T2 submission deadline;
- audit deadline;
- slash execution window.

Without deadlines, the system depends too much on operator timing and off-chain coordination.

## `DINTaskAuditor.sol` Production Requirements

### 1. Registration checks
`registerDINAuditor(uint256 gi)` must use `isValidatorActive(msg.sender)`.

### 2. Batch construction
`createAuditorsBatches()` must filter inactive validators exactly like the coordinator filters aggregators.

### 3. Submission gates
`setAuditScorenEligibility()` must require the auditor to still be active.

Recommended error:
- `TA_AuditorNotActive()`

### 4. Auditor accountability model
Auditor slashing must be fully implemented. At minimum, support three fault classes:
- assigned auditor failed to vote before deadline;
- auditor submitted clearly adversarial eligibility vote versus final majority;
- auditor score was a strong outlier beyond configured tolerance.

Recommended production policy:
- no-vote: fixed liveness slash plus optional jail;
- bad eligibility vote: fixed fault slash if vote contradicts final accepted consensus and quorum is strong;
- outlier score: slash only if deviation exceeds an objective threshold to avoid punishing honest disagreement.

### 5. Scoring policy
Do not slash purely for minority scoring without tolerance bounds. Production systems need room for honest variance.

Add configuration:

```solidity
uint256 public maxScoreDeviation;
uint256 public noVoteSlashAmount;
uint256 public badEligibilitySlashAmount;
uint256 public outlierScoreSlashAmount;
```

### 6. Auditor slashing function
Move auditor slashing logic to the auditor contract or keep the entrypoint in coordinator with explicit auditor evidence retrieval. In either case, production behavior must:
- evaluate every assigned auditor;
- classify the offense;
- call stake slashing with a specific reason;
- emit per-auditor slash results.

Required event:

```solidity
event AuditorSlashed(
    uint256 indexed gi,
    uint256 indexed batchId,
    address indexed auditor,
    bytes32 reason,
    uint256 requested,
    uint256 actual
);
```

## `DINShared.sol` Interface Changes

The shared validator stake interface should be expanded to:

```solidity
interface IDinValidatorStake {
    function minStake() external view returns (uint256);
    function isValidatorActive(address validator) external view returns (bool);
    function slashableStakeOf(address validator) external view returns (uint256);
    function validatorStatus(address validator) external view returns (uint8);
    function slash(
        address validator,
        uint256 amount,
        bytes32 reason
    ) external returns (uint256 slashedAmount);
}
```

Remove role-contract dependency on raw `getStake()` for eligibility decisions. Raw balance reads may still be used for views, but not for access control.

## `DinCoordinator.sol` Governance Hardening

The current owner powers are too broad for a production security primitive. Minimum hardening:
- place slasher add/remove operations behind a timelock or DAO executor;
- require delayed execution for blacklist operations unless emergency mode is explicitly entered;
- treat validator stake contract replacement as a high-risk governance action with time delay and event transparency.

Recommended additions:
- `TimelockController` or equivalent executor;
- two-step stake contract upgrade announcement and acceptance;
- separate emergency guardian from long-term governance.

## Economic Parameters

### Required configurable parameters
- `MIN_STAKE`
- `UNBONDING_PERIOD`
- slash amounts per offense class
- jail durations per offense class
- auditor score deviation tolerance
- late submission grace windows, if any

### Parameter guidance
- `MIN_STAKE` must be large enough that running many Sybil validators is materially expensive.
- `UNBONDING_PERIOD` must exceed the maximum time needed to detect and process offenses from the GI in which the validator last participated.
- liveness slashes should be smaller than provable-maliciousness slashes.
- repeated offenses should escalate to jailing and eventually blacklist eligibility review.

## Operational Policy

### 1. Assignment commitment
Once a validator is assigned to a batch, that assignment creates a slashable commitment. Exiting after assignment must not remove accountability for that assignment.

### 2. Blacklist usage
Blacklist is an emergency kill switch, not a normal validator discipline tool. Normal faults should prefer:
- slash;
- jail;
- eventual reactivation.

### 3. Round completion
GI completion must not depend on every slash succeeding at the full requested amount. The round should complete as long as every participant has been evaluated and the slash attempts have been recorded.

## Migration Plan

### Phase 1: Critical fixes
- Add `isValidatorActive()` and `minStake()` to the shared interface.
- Replace registration and submission checks in coordinator/auditor.
- Filter inactive validators during batch creation.
- Make slash non-blocking and return actual slashed amount.

### Phase 2: Lifecycle hardening
- Replace immediate unstake with request/claim unbonding flow.
- Add validator statuses: `Active`, `Exiting`, `Jailed`, `Blacklisted`.
- Add slashable pending withdrawals.

### Phase 3: Full production penalties
- Implement auditor slashing.
- Introduce slash reasons and per-offense events.
- Add deadlines and timestamp-based enforcement.

### Phase 4: Governance hardening
- Add timelock for slasher management and blacklist actions.
- Separate emergency actions from routine operations.

## Test Requirements

Production readiness requires tests covering at least:
- register while blacklisted;
- register with enough raw stake but inactive status;
- unstake request after assignment;
- slash while validator is exiting;
- slash while pending withdrawals exist;
- partial slash where stake is below requested amount;
- multiple slashes in one GI without loop-wide revert;
- inactive validators excluded from new batch creation;
- inactive assigned aggregators rejected on submission;
- inactive assigned auditors rejected on submission;
- auditor no-vote penalty;
- auditor outlier score tolerance;
- blacklist during GI;
- jail expiry and reactivation.

## Acceptance Criteria

The staking/slashing system should be considered production-candidate only if:
- no validator can avoid slashability by withdrawing immediately;
- no coordinator/auditor action relies on stale stake snapshots for eligibility;
- slash execution is non-blocking and records actual outcomes;
- both aggregators and auditors have implemented, tested penalty paths;
- governance actions over slashers and blacklist are delayed or tightly constrained;
- documentation matches actual contract behavior exactly.

## Bottom Line
The current DIN staking logic is a useful prototype, but not a production security mechanism. The hardening path is to turn `DinValidatorStake.sol` into a lifecycle-aware slashable collateral manager, and to make `DINTaskCoordinator.sol` and `DINTaskAuditor.sol` consume active eligibility instead of raw stake balances.

If these requirements are implemented, the DIN protocol would move from a demo-grade staking vault toward a credible production validator security layer.
