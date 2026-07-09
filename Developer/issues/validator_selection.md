# Validator Selection and Capability Matching

## Summary

DIN currently treats validator selection as:

- stake check
- on-chain role registration
- random batch assignment
- slashing after failure

That is acceptable for the current lightweight devnet path, but it is not a safe contract for production workloads where auditing and aggregation have materially different RAM, disk, network, and runtime requirements.

The protocol should move to capability-aware selection with four explicit stages:

1. the model owner publishes a machine-readable capability spec in the manifest;
2. the validator runs a local preflight and registers with a capability snapshot;
3. the model owner or daemon filters the registered pool down to a compatible subset before randomization;
4. the validator becomes slashable only after accepting the concrete assignment.

## Problem Restated

The real issue is not just "who can register."

The issue is that the current contracts:

- do not know whether a registered validator can actually execute the assigned batch;
- build auditor and aggregator batches from the full registered pool;
- expose validators to slashing after assignment, even when the assignment may have been predictably infeasible.

The current off-chain services make this mismatch concrete:

- the auditor path evaluates models one by one and is relatively serial;
- the aggregator path currently downloads every assigned model and loads every state dict into memory before averaging.

That means aggregation is already a higher-risk role than auditing, and the protocol should represent that difference explicitly.

## Design Direction

The recommended direction is:

- keep detailed hardware and workload descriptions off-chain in the manifest;
- keep local machine inspection off-chain in `dincli` and later `dind`;
- keep assignment accountability on-chain;
- stop using blind batch creation over the full registered pool;
- make selection auditable by publishing a selection receipt;
- move slashability to post-acceptance rather than post-assignment.

This keeps the contracts small enough to be practical while still fixing the current failure mode.

## Decision Summary

### 1. Capability spec lives in the manifest

Use the existing manifest and model-registry flow as the source of truth for role requirements.

- no dedicated registry contract change is required for `v1`;
- the capability spec is anchored automatically when the manifest CID is approved or updated through `DINModelRegistry`;
- the initial spec should be embedded in the manifest as a `capability_spec` block.

### 2. Validators register intent plus capability metadata

Registration should still be stake-gated, but it should also carry a capability profile reference.

- aggregators and auditors register for a GI with a profile CID or profile hash;
- the profile is generated locally from measured hardware plus operator-declared limits;
- the profile remains an off-chain attestation, not a trustless proof.

### 3. Selection filters first, randomizes second

Batch creation should no longer shuffle the full registered pool.

Instead:

1. fetch the registered validators for the GI;
2. fetch each validator capability profile;
3. filter out hard mismatches;
4. randomize within the compatible subset;
5. record a selection receipt for later audit.

### 4. Acceptance is the slashability boundary

A validator should not become fully slashable merely because it was included in a proposed batch.

The safer contract is:

1. register;
2. get proposed assignment;
3. run final local preflight against the exact batch;
4. accept assignment on-chain;
5. become slashable if the accepted work is not completed.

### 5. Delivery should be phased

This should not be attempted as one large all-or-nothing change.

- `v1`: manifest capability spec, local preflight, capability-aware eligible pools, selection receipt
- `v2`: explicit assignment acceptance and slash-on-accept
- `v3`: daemon automation, availability tracking, reputation-aware ranking

## Deliverables In This Folder

- [Design](validator_selection/design.md): target architecture, schemas, selection flow, contract model, and trust assumptions
- [Implementation Plan](validator_selection/implementation.md): phased work breakdown mapped to concrete files in this repository

## Definition Of Done

This issue should be considered properly addressed when DIN can do all of the following:

- publish role-specific resource requirements through the manifest;
- detect or load a validator capability profile locally;
- block or strongly gate registration when a validator does not meet hard requirements;
- build auditor and aggregator batches from compatible subsets rather than all registrants;
- publish an auditable receipt that explains why validators were included or excluded;
- ensure slashing only applies after explicit assignment acceptance.

## Out Of Scope For Initial Delivery

The first production-worthy version does not need:

- trustless hardware proofs;
- zero-knowledge resource attestation;
- fully autonomous on-chain capability verification;
- stake-weighted reputation markets.

Those can come later. The immediate goal is to stop predictable capability mismatch from turning into avoidable slashing.
