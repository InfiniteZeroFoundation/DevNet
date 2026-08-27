# DIN Feasibility Report

## Executive Summary

DIN is feasible as a staged DevNet-to-testnet protocol, but it is not feasible if all items in the Developer roadmap are treated as one simultaneous production build.

The current repository already has a meaningful foundation:

- protocol-level contracts for token minting, staking, model registration, and slasher authorization;
- task-level contracts for global iteration orchestration, local model submission, auditor scoring, and tiered aggregation;
- `dincli` workflows for model owners, clients, auditors, and aggregators;
- IPFS-backed service artifacts and manifest-driven task execution;
- a simple but working federated-learning path using local training, audit scoring, and aggregation;
- initial differential privacy support in client services.

The project becomes high risk when it tries to solve every advanced requirement at once: robust decentralized validation, contribution scoring, tokenomics, slashing, validator rewards, client rewards, governance, Filecoin storage, daemon automation, and production-grade privacy. Those are each real systems, not small features.

The feasible path is to narrow the immediate objective:

> Build a transparent DevNet protocol that can run one model-training task end to end, score local updates honestly, aggregate accepted updates, and publish enough evidence for operators to inspect the round.

Everything else should be layered after that.

## Current Reality

The Documentation directory describes a functioning protocol shape. DIN already has defined actors:

- model owner;
- clients;
- auditors;
- aggregators;
- DIN representative or future DAO.

The current workflow is also concrete:

1. model owner deploys task contracts;
2. task contracts are authorized as slashers;
3. model owner publishes manifest and services;
4. genesis model is created and registered;
5. clients train and submit local models;
6. auditors score local models;
7. approved models are aggregated through T1 and T2 aggregation;
8. global iteration ends with optional slashing.

This is not fantasy. It is an early protocol implementation with real moving parts.

However, the current implementation is closer to a coordinated DevNet than a trust-minimized decentralized AI network. Several mechanisms still depend on trusted model-owner actions, simple off-chain service execution, average-based scoring, weak randomness, and incomplete reward/token accounting.

## Feasibility Verdict

| Area | Feasibility | Notes |
|---|---:|---|
| End-to-end DevNet training workflow | High | Already documented and partially implemented. Needs hardening, tests, and smoother UX. |
| Manifest-driven services | High | Current architecture is reasonable. Runtime context pattern is a strong direction. |
| Basic client training | High | Works for supervised tasks like MNIST-style classification. Needs training-policy abstraction for broader tasks. |
| Basic auditor scoring | High | Feasible with validation-set scoring and eligibility checks. Needs robust aggregation and better result schema. |
| Basic aggregation | High | Tiered aggregation exists. Can be improved incrementally. |
| Differential privacy baseline | Medium | Current post-training/update noise is useful for experiments, not production privacy guarantees. |
| Validator selection | Medium | Capability-aware selection is feasible off-chain first. Full trustless resource proofs are out of scope. |
| Client rewards | Medium | Feasible after scoring outputs are stable. Should start off-chain or with compact on-chain summaries. |
| Validator rewards | Medium | Feasible after completion evidence and fee/reward pools are defined. |
| Slashing | Medium-Low | Simple inactivity or non-submission slashing is feasible. Correctness slashing is hard without deterministic verification. |
| Tokenomics | Medium-Low | Needs a clear asset model before production. Current DIN token is DevNet utility collateral, not complete economics. |
| Governance | Medium-Low | DAO-controlled admin is feasible. Full decentralized governance should wait. |
| Filecoin integration | Medium | Feasible as a storage-provider extension. Not required for MVP. |
| Daemon and agentic automation | Medium-Low | Useful later, but not required to prove protocol feasibility. |
| Backdoor-resistant ML security | Low for MVP | Clean validation scoring catches crude poisoning, not stealthy backdoors. Treat as later hardening. |

## The Main Risk

The main risk is not that the idea is impossible.

The main risk is scope coupling: every mechanism appears to depend on every other mechanism.

Examples:

- client rewards depend on scoring;
- validator rewards depend on scoring, assignment, completion, and fee routing;
- slashing depends on validator selection, accepted assignments, deterministic evidence, and dispute rules;
- tokenomics depends on staking, rewards, fees, slashing, treasury, and governance;
- governance depends on tokenomics and upgrade policy;
- production privacy affects scoring accuracy and poisoning detection.

If these are implemented as one large system, the project becomes unmanageable. If they are staged behind clear interfaces, the project remains feasible.

## What Should Be Considered Core

The core protocol should be reduced to the smallest loop that proves DIN's value:

1. A model owner registers a task.
2. Clients train locally and submit updates.
3. Validators evaluate submitted updates.
4. Bad or useless updates are rejected.
5. Accepted updates are aggregated.
6. A new global model is produced.
7. Round evidence is published for inspection.

This core does not require full DAO governance, mature tokenomics, Filecoin settlement, advanced privacy accounting, autonomous daemons, or exact Shapley valuation.

## What Should Be Deferred

The following should not block the next feasible milestone:

- exact or sample-level Shapley valuation;
- TKNN-Shapley in validator scoring;
- fully trustless ML evaluation;
- backdoor-proof model auditing;
- production token monetary policy;
- full DAO voting;
- upgradeable contract migration across every contract;
- Filecoin storage deals and payment settlement;
- autonomous `dind` execution;
- zero-knowledge, MPC, or TEE-based evaluation.

These are not bad ideas. They are later layers.

## Recommended MVP Definition

The next realistic milestone should be:

> A repeatable DevNet round where multiple clients submit local model updates, multiple validators score those updates using a documented scoring policy, accepted updates are aggregated, and all round artifacts are inspectable by CID.

### MVP In Scope

- manifest-level `scoring_policy`;
- eligibility checks for submitted models;
- validation-set utility scoring;
- median or majority validator aggregation;
- accepted-update-only aggregation;
- basic DP update clipping/noise as an optional client setting;
- off-chain metric bundles;
- clear CLI commands for each actor;
- tests for one reference task.

### MVP Out Of Scope

- automatic reward payouts;
- production slashing for correctness disputes;
- full governance;
- production tokenomics;
- Filecoin-native storage settlement;
- daemon automation;
- advanced no-label training modes;
- backdoor-resistant auditing.

## Critical Design Simplifications

### 1. Treat validators as auditors first

The current system already has auditors. Use them as the first validator role for scoring. Avoid adding a second validator abstraction until the existing auditor path is robust.

### 2. Keep contribution scoring separate from admission scoring

Admission decides whether an update enters aggregation. Contribution decides later reward weight. Mixing them creates bad incentives and makes the system harder to debug.

### 3. Use model-update scoring, not sample-level data valuation

Validators see model updates, not raw client datasets. Scoring should therefore operate on model updates. TKNN-Shapley and similar sample-level valuation methods are not viable in the validator path.

### 4. Keep rich evidence off-chain

Contracts should store compact summaries, CIDs, and final decisions. Full metric bundles, evaluation specs, contribution reports, and selection receipts should remain off-chain.

### 5. Do not overclaim privacy

Current DP is a useful experimental layer. It should be described as update perturbation and clipping, not as a complete privacy guarantee until accounting, threat models, and composition are implemented.

### 6. Do not overclaim decentralization

The DevNet can be honest-but-auditable. That is acceptable. Production decentralization can be layered through validator selection, staking, governance, dispute handling, and independent indexers.

## Feasible Build Order

### Phase 1: Stabilize The Existing Round

Goal: make the current model workflow reliable.

Deliverables:

- one reference task that can be run repeatedly;
- clean setup documentation;
- deterministic local test data layout;
- contract and CLI tests for the GI lifecycle;
- successful client training, audit, aggregation, and GI finalization.

Exit criteria:

- one clean end-to-end run can be reproduced from docs;
- failures are observable and recoverable;
- submitted artifacts can be inspected by CID.

### Phase 2: Scoring V1

Goal: replace the weak one-score path with explicit eligibility and utility scoring.

Deliverables:

- `eligibility_anomaly_gate`;
- `holdout_delta_score`;
- median or majority validator aggregation;
- `evaluationSpecCID`;
- `metricBundleCID`;
- normalized audit result shape.

Exit criteria:

- invalid models are rejected before aggregation;
- accepted models are justified by published metrics;
- scoring no longer depends on a single opaque average.

### Phase 3: Accepted-Update Aggregation

Goal: ensure aggregation only consumes accepted updates.

Deliverables:

- aggregation input filtering based on auditor approval;
- clipped averaging baseline;
- optional score-weighted aggregation;
- tests for rejected updates not entering T1/T2 batches.

Exit criteria:

- harmful or ineligible updates do not affect the global model in the reference task.

### Phase 4: Reward Simulation Before Reward Contracts

Goal: validate incentive math before locking it into contracts.

Deliverables:

- client reward calculator;
- validator reward calculator;
- simulation harnesses for edge cases;
- off-chain reward reports.

Exit criteria:

- reward formulas satisfy invariants;
- no reward pool can be overdrawn;
- zero-contribution and failed-work cases are handled.

### Phase 5: Minimal Reward Accounting

Goal: add compact on-chain summaries only after formulas are stable.

Deliverables:

- task-level reward pool accounting;
- claimable summary roots or per-address claims;
- event-based indexing path;
- tests for rounding, withholding, and rollover.

Exit criteria:

- rewards can be audited without putting all scoring details on-chain.

### Phase 6: Hardening

Goal: prepare for wider testnet usage.

Deliverables:

- capability-aware validator selection;
- assignment acceptance before slashability;
- stronger randomness or VRF plan;
- indexer for protocol state;
- upgrade policy for platform contracts;
- clearer tokenomics and treasury policy.

Exit criteria:

- operators can understand risk before participating;
- model owners can run tasks without manual contract archaeology;
- the protocol has a credible route from DevNet to testnet.

## What Would Make The Project Non-Feasible

The project becomes non-feasible if it requires all of these at once:

- trustless validation of arbitrary ML workloads;
- production privacy guarantees;
- exact contribution valuation;
- permissionless economic security;
- strong Sybil resistance;
- mature tokenomics;
- decentralized governance;
- autonomous agent execution;
- robust storage markets;
- production-grade adversarial ML defense.

That combination is a multi-year protocol program. It should not be treated as the first version.

## What Makes The Project Feasible

The project remains feasible if it accepts these constraints:

- start with one or two reference task types;
- make scoring explicit but simple;
- publish evidence rather than trying to verify everything on-chain;
- keep contracts compact;
- use off-chain simulations before on-chain economics;
- treat DevNet as honest-but-auditable;
- defer advanced privacy, governance, and backdoor defense;
- build one phase until it is boring before adding the next phase.

## Recommended Immediate Priorities

1. Freeze the near-term target as "DevNet scoring and accepted aggregation," not full cryptoeconomics.
2. Finish the scoring mechanism work before reward work.
3. Add tests around auditor scoring and approved-model aggregation.
4. Convert reward mechanisms into simulations first.
5. Keep tokenomics as a design decision document until reward and staking behavior are stable.
6. Create an operator-facing runbook for one complete GI.
7. Use an indexer/event strategy before adding more on-chain query complexity.

## Final Assessment

DIN is ambitious but not inherently unrealistic.

The credible version is a staged protocol: first a working auditable FL DevNet, then robust scoring, then incentive simulations, then compact reward accounting, then governance and hardening.

The unrealistic version is a fully decentralized, privacy-preserving, adversarially robust, economically secure AI network delivered as one build.

The project should proceed, but with a strict scope boundary:

> Prove the training, scoring, and aggregation loop first. Do not let tokenomics, governance, storage, daemon automation, or exact valuation become blockers for that proof.

