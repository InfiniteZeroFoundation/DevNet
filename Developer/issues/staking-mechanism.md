# Staking Infrastructure

## Summary

This issue defines the staking and validator-selection work needed to turn DIN's current validator gating into a fuller staking infrastructure.

The target execution flow is:

- validators stake DIN to participate in aggregation and evaluation
- stake acts as an economic commitment and reliability signal
- active stake determines eligibility for subgroup assignment
- validator selection is dynamic per subgroup and per round
- subgroup composition must satisfy configurable validator-to-participant ratios

This work maps to two near-term work packages:

- `WP 1.1` validator staking contract
- `WP 1.2` validator selection logic

## Why This Matters

DIN already depends on validators for aggregation and auditing, but those roles are still only partially backed by staking-aware infrastructure.

Without a stronger staking layer:

- validator admission rules remain too thin
- exits and slashability windows are easy to reason about incorrectly
- subgroup selection can drift toward ad hoc registration order
- fairness and Sybil resistance are weaker than the P3 roadmap implies
- participation policy is harder to tune as task volume grows

The protocol needs staking to be more than a balance check. It needs staking to define:

- who is eligible
- when they are eligible
- when they are exiting
- what stake remains slashable
- how validators are assigned across aggregation and evaluation subgroups

## Current State

The repo already contains a meaningful starting point:

- `hardhat/contracts/DinValidatorStake.sol`
- `hardhat/contracts/DINTaskCoordinator.sol`
- `hardhat/contracts/DINTaskAuditor.sol`
- mirrored Foundry versions under `foundry/src/`

Important current behavior:

- `DinValidatorStake.sol` already supports staking, unstake requests, delayed claims, and slashing across active stake plus pending withdrawals
- `MIN_STAKE` and `UNBONDING_PERIOD` are constants today
- validators are considered active through `isValidatorActive(...)`
- `DINTaskCoordinator.sol` and `DINTaskAuditor.sol` gate registration on active-validator status
- batch assignment currently relies on registered validator pools plus local shuffle logic

That means DIN has a base staking contract, but it does not yet have the complete infrastructure implied by the roadmap.

Main current gaps:

- no distinct validator registry module that exposes richer eligibility and lifecycle metadata
- no configurable stake thresholds
- no stake-aware subgroup policy beyond active-or-not-active checks
- no explicit validator rotation policy
- no fairness-reporting framework for subgroup selection
- randomness is local contract shuffling rather than a clearly specified validator-selection engine

## Target Direction

The desired architecture should separate three concerns cleanly.

### 1. Staking state

The staking contract should own:

- active stake
- pending withdrawals
- unbonding windows
- slashable balances
- validator lifecycle state

### 2. Validator registry

The registry layer should expose:

- whether a validator is eligible for assignment
- current role availability for aggregation and auditing
- exit status
- blacklisting or jailing state
- assignment metadata needed by the selection engine

This can remain in the staking contract for `v1` if needed, but the interface should behave like a registry even if storage is colocated.

### 3. Selection engine

The selection layer should decide:

- which validators enter each subgroup
- how many validators are needed for a participant set
- how rotations happen across rounds
- how to avoid repeatedly selecting the same validators
- how randomness is sampled and verified

## WP 1.1: Validator Staking Contract

**Duration:** May 4, 2026 to May 8, 2026

### Scope

This package should produce the `v1` staking contract and registry integration required for validator lifecycle management.

### Activities

- design staking contract architecture
- implement deposit and withdrawal logic
- define lock periods and minimum stake
- integrate validator registry

### Expected Deliverables

- staking smart contract (`v1`)
- unit tests
- validator registry integration module

### Design Requirements

The `v1` contract should support:

- deposits of DIN by validator address
- minimum stake enforcement
- explicit unstake requests instead of instant exits
- claimable withdrawals only after the lock period expires
- slashability during the pending-withdrawal window
- coordinator-controlled or governance-controlled blacklisting and slasher authorization
- event emission for every meaningful validator-state transition

Recommended `v1` contract rules:

- a validator below minimum active stake should not be assignable to new work
- a validator in `Exiting` state should remain slashable until withdrawal claim finalization
- only one pending withdrawal should exist per validator in `v1` unless partial-withdrawal queuing is deliberately implemented
- minimum stake and unbonding period should be configurable storage if governance tuning is expected soon, or constants only if the team accepts another migration later
- if a validator is blacklisted, funds may remain trapped in `v1` until governance introduces a dedicated confiscation and treasury-routing flow

### Future Governance Extension

Once DAO governance is in place, the staking system should add a governance-only confiscation path for permanently blacklisted funds:

- `confiscateBlacklistedStake(address validator, uint256 amount, bytes32 reason)`
- callable only through accepted DAO governance execution, not by the interim admin directly
- usable only when the validator is currently `Blacklisted`
- should move confiscated DIN from the staking contract to the protocol treasury
- should execute only after a governance proposal to confiscate the trapped blacklisted stake is accepted
- should emit a dedicated event so indexers can distinguish confiscation from ordinary slashing

This should be treated as a separate governance action from blacklisting itself. Blacklisting freezes validator funds and participation immediately; confiscation is the later treasury-transfer step that happens only if governance approves it.

### Registry Integration Requirements

The registry integration layer should provide at least:

- `isValidatorEligible(address)`
- `isValidatorActive(address)`
- `slashableStakeOf(address)`
- validator status reads for `Active`, `Exiting`, `Jailed`, and `Blacklisted`
- event surfaces that an indexer can consume for validator history and assignment dashboards

### Testing Requirements

Unit tests should cover:

- stake below minimum
- stake increase by an existing validator
- unstake request creation
- withdrawal claim before and after unlock
- slash against active stake
- slash against pending withdrawals
- blacklisted validator restrictions
- status transitions after stake drops below threshold

When DAO governance is implemented, governance-path tests should also cover:

- rejection of confiscation for non-blacklisted validators
- rejection of confiscation outside governance execution
- partial and full confiscation of trapped blacklisted stake
- treasury receipt of confiscated DIN
- event emission and post-confiscation stake accounting

## WP 1.2: Validator Selection Logic

**Duration:** May 11, 2026 to May 15, 2026

### Scope

This package should replace simple registration-order behavior with a defined validator-selection engine for subgroup assignment and rotation.

### Activities

- implement randomized validator selection
- design subgroup assignment logic
- implement validator rotation
- define validator-to-participant ratio

### Expected Deliverables

- validator selection engine
- rotation mechanism
- fairness testing report

### Selection Requirements

The engine should support:

- dynamic validator selection per subgroup
- filtering to currently eligible validators only
- deterministic assignment from an agreed randomness input
- configurable subgroup size and ratio policy
- prevention of duplicate assignment within the same subgroup where not allowed
- role-aware assignment if aggregators and auditors have separate pools later

### Ratio Policy

The validator-to-participant ratio should be explicit rather than implicit.

At minimum, the design should define:

- minimum validators per aggregation subgroup
- minimum validators per audit subgroup
- how ratios scale with participant count
- behavior when the active validator set is too small
- whether stake affects only eligibility or also selection weight

### Rotation Requirements

Rotation should aim to reduce concentration without making assignment unstable.

The mechanism should define:

- whether cooldown windows exist after assignment
- whether prior-round participation reduces near-term reselection probability
- how to handle validators who stay active across many rounds
- how to recover if too few fresh validators are available

### Fairness Testing Report

The fairness report should measure:

- assignment distribution across many simulated rounds
- concentration of repeated selection
- effect of ratio changes on subgroup quality
- behavior under small-validator-set conditions
- behavior under skewed stake distributions if weighted selection is used

## Recommended Implementation Path

A practical `v1` path for this repo is:

1. extend `DinValidatorStake.sol` only where needed to formalize validator lifecycle and registry-style reads
2. keep `DINTaskCoordinator.sol` and `DINTaskAuditor.sol` consuming validator eligibility through a narrow interface
3. move subgroup selection rules into a clearer engine or library instead of relying on ad hoc local shuffle helpers
4. add indexer-friendly events for stake, exit, slash, and assignment transitions

This keeps the initial implementation compatible with the current codebase while leaving room for later governance and upgradeability work.

## Open Design Questions

- should stake influence selection probability, or only minimum eligibility?
- should aggregators and auditors share one validator pool in `v1`?
- should the randomness source remain pseudo-random for devnet, or should the interface already prepare for a stronger source later?
- should minimum stake and unbonding period be governance-controlled parameters?
- should validator rotation be hard-enforced on-chain or left to coordinator policy plus observable fairness tests?
- once DAO governance is live, should `confiscateBlacklistedStake(...)` permit partial confiscation, full confiscation only, or both?
- which treasury address should receive confiscated blacklisted stake after a successful governance proposal?

## Done Criteria

This issue is complete when:

- staking lifecycle rules are explicitly documented and implemented for `v1`
- registry-style validator eligibility reads exist
- subgroup selection and rotation behavior are specified
- ratio policy is written down and enforced in code or coordinator logic
- tests cover both staking correctness and selection fairness expectations
