# Validator Selection Implementation Plan

## Implementation Strategy

The right implementation is incremental.

If DIN tries to ship capability specs, selector logic, contract ABI changes, assignment acceptance, and daemon automation all at once, the migration risk is much higher than necessary.

The recommended order is:

1. establish the metadata and local checking path;
2. change batch creation so compatible subsets can actually be enforced;
3. add acceptance and update slashing semantics;
4. only then move matching into the daemon.

## Workstream 1: Manifest And Capability Schema

### Goal

Make workload requirements machine-readable and available to every role through the existing manifest flow.

### Files To Update

- `Documentation/technical/manifest.md`
- `cache_model_0/manifest.json`
- optionally `Documentation/model-owner.md`, `Documentation/aggregators.md`, and `Documentation/auditors.md`

### Changes

- add a documented `capability_spec` block to the manifest;
- define role-specific requirement fields for clients, auditors, and aggregators;
- document which fields are hard requirements versus advisory estimates;
- update the reference manifest so there is one concrete example in the repo.

### Notes

Do not overload `requirements.txt` for this purpose.

That key already describes Python dependency files. The capability schema should be its own first-class manifest block.

## Workstream 2: Local Capability Detection And Preflight

### Goal

Make `dincli` able to decide whether the local machine should register for a role before sending a transaction.

### Recommended New Modules

- `dincli/services/capability.py`
- optionally `dincli/cli/capability.py` or an extension inside `dincli/cli/system.py`

### Existing Files To Update

- `dincli/services/runtime.py`
- `dincli/cli/utils.py`
- `dincli/cli/aggregator.py`
- `dincli/cli/auditor.py`

### Changes

- add helpers to load `capability_spec` from the manifest;
- add local hardware detection for RAM, disk, CPU, GPU, and bandwidth when possible;
- add a normalized capability profile format;
- add a preflight matcher that compares local profile to role requirements;
- add operator-facing commands to inspect local capability data;
- gate `aggregator register` and `auditor register` behind preflight checks, with an explicit override flag for dev-only usage.

### Why This Comes First

Without this step, the protocol has nowhere to source the capability information that later selection depends on.

## Workstream 3: Registration Metadata

### Goal

Attach an auditable capability-profile reference to each on-chain role registration.

### Contracts To Update

- `foundry/src/DINTaskCoordinator.sol`
- `foundry/src/DINTaskAuditor.sol`
- `foundry/src/DINShared.sol`
- mirrored files in `hardhat/contracts/`

### ABI Strategy

Add new versioned methods instead of breaking the old ones immediately.

Recommended methods:

- `registerDINaggregatorV2(uint gi, bytes32 capabilityProfileCID)`
- `registerDINAuditorV2(uint gi, bytes32 capabilityProfileCID)`

### Storage And Events

Add:

- profile CID mappings per GI and validator;
- registration events that include the profile reference.

### CLI Changes

Update:

- `dincli/cli/aggregator.py`
- `dincli/cli/auditor.py`

So that registration:

1. builds a capability profile;
2. optionally uploads it to IPFS;
3. converts the CID to `bytes32`;
4. calls the `V2` registration method.

### Backward Compatibility

If a manifest does not declare `capability_spec`, the CLI can either:

- keep legacy registration available behind a `--legacy-selection` flag; or
- refuse registration for production networks and only allow it on local devnet.

The stricter option is better once the feature stabilizes.

## Workstream 4: Capability-Aware Batch Creation

### Goal

Replace blind shuffling across all registrants with shuffling across a compatible subset chosen off-chain.

### Contracts To Update

- `foundry/src/DINTaskAuditor.sol`
- `foundry/src/DINTaskCoordinator.sol`
- mirrored `hardhat/contracts/` copies

### Recommended Methods

- `createAuditorsBatchesV2(uint gi, address[] calldata eligibleAuditors, bytes32 selectionReceiptCID)`
- `createTier1AndTier2V2(uint gi, address[] calldata eligibleTier1Aggregators, address[] calldata eligibleTier2Aggregators, bytes32 selectionReceiptCID)`

### Required Validation

The contract should verify that every supplied address:

- is registered for that GI;
- still has sufficient stake;
- is still active according to the validator stake contract.

The contract should not attempt to re-run capability matching.

### Selector Location In The Current Repo

Implement the first selector in the model-owner CLI because batch creation is already driven there.

Update:

- `dincli/cli/modelownerd/auditor_batches.py`
- `dincli/cli/modelownerd/aggregation.py`
- optionally shared selector helpers in `dincli/services/capability.py`

### Selector Flow

1. load the manifest capability spec;
2. fetch the registered pool from the contracts;
3. fetch each validator profile reference;
4. resolve the profiles from local cache or IPFS;
5. filter hard mismatches;
6. build a selection receipt;
7. upload the receipt to IPFS;
8. call the `V2` batch-creation method with the eligible subset and receipt CID.

### Why Selection Receipt Matters

Once the model owner decides the compatible subset off-chain, there needs to be a reviewable artifact explaining which validators were excluded and why.

## Workstream 5: Assignment Acceptance

### Goal

Make acceptance, not assignment, the start of slashability.

### Contracts To Update

- `foundry/src/DINTaskAuditor.sol`
- `foundry/src/DINTaskCoordinator.sol`
- `foundry/src/DINShared.sol`

### Recommended Minimal Additions

- acceptance and decline functions for auditor, T1, and T2 batches;
- per-batch acceptance mappings;
- accepted-count tracking or equivalent checks.

### State-Machine Approach

Do not add a large number of new GI states unless necessary.

A lower-risk path is:

- keep `AuditorsBatchesCreated` and `T1nT2Bcreated`;
- allow acceptance during those states;
- make `startLMsubmissionsEvaluation()` require accepted auditor quorum;
- make `startT1Aggregation()` require accepted T1 quorum;
- make `startT2Aggregation()` require accepted T2 quorum.

This keeps the lifecycle readable and reduces migration cost.

### CLI Changes

Update:

- `dincli/cli/auditor.py`
- `dincli/cli/aggregator.py`

Add commands to:

- show acceptance status for assigned batches;
- accept a batch;
- decline a batch.

Update model-owner commands to detect when a batch lacks accepted quorum and either:

- rebuild the batch; or
- abort the phase transition with a clear error.

## Workstream 6: Slashing Semantics

### Goal

Align slashing with explicit accepted responsibility.

### Contracts To Update

- `foundry/src/DINTaskCoordinator.sol`
- `foundry/src/DINTaskAuditor.sol`
- technical docs that currently describe slashing behavior

### Changes

- slash aggregators only if they accepted the relevant T1 or T2 assignment;
- slash auditors only if they accepted the relevant audit batch;
- exclude declined or unaccepted validators from no-show penalties.

### Important Limitation

The first version does not need a separate slashing path for "false hardware advertisement."

Operationally, the accepted-assignment boundary is enough to fix the current unfairness.

## Workstream 7: Documentation And Examples

### Goal

Make the new model understandable and reproducible for contributors and model owners.

### Files To Update

- `Documentation/technical/DINTaskCoordinator.md`
- `Documentation/technical/DINTaskAuditor.md`
- `Documentation/technical/manifest.md`
- `Documentation/aggregators.md`
- `Documentation/auditors.md`
- `Documentation/model-owner.md`

### Changes

- document the new manifest fields;
- document the new registration flow;
- document the new batch-creation flow;
- document acceptance as the slashability boundary;
- add one complete end-to-end example using the reference manifest.

## Workstream 8: Tests

### Contract Tests

Add or expand tests under:

- `foundry/test/`
- optionally `hardhat/test/`

Test cases should include:

- registration with and without capability profile reference;
- rejection when an eligible pool contains an unregistered validator;
- rejection when an eligible pool contains an inactive validator;
- successful batch creation from a filtered subset;
- acceptance gating before evaluation or aggregation starts;
- slashing only for accepted validators.

### Python Tests

Add tests under `tests/` for:

- manifest capability-spec parsing;
- local capability-profile normalization;
- matching logic for auditor and aggregator roles;
- selection-receipt generation;
- CLI registration gating behavior.

### Integration Tests

Add one end-to-end path that proves:

1. a weak validator is prevented from entering the compatible subset;
2. a strong validator is selected;
3. the selected validator must accept before slashability exists.

## Suggested Delivery Phases

### Phase A: Metadata And Tooling

- manifest schema
- local capability detection
- preflight commands
- docs and example manifest

This phase is low risk and should land first.

### Phase B: Eligible-Pool Selection

- `V2` registration methods
- profile references on-chain
- selection receipt generation
- `V2` batch-creation methods

This is the first phase that actually changes assignment behavior.

### Phase C: Acceptance And Slashing

- accept and decline methods
- phase-transition gating on accepted quorum
- slash-on-accept semantics

This is the phase that fixes the current accountability boundary.

### Phase D: Daemonization

- move selector logic from model-owner CLI into `dind`
- add availability tracking
- add reliability-aware ranking

This should come last because it builds on stable metadata and contract semantics.

## Migration Notes

Use feature detection rather than a flag day cutover.

Recommended approach:

- new manifests declare `capability_spec`;
- new contracts expose `V2` methods;
- `dincli` checks whether both are available;
- if either side is missing, the CLI falls back to legacy behavior only on explicitly allowed networks.

That avoids breaking old devnet flows while still giving a clear upgrade path.

## Definition Of Done

The implementation is complete when:

- model owners can publish a capability spec in the manifest;
- validators can generate a capability profile and register with its reference;
- model-owner tooling can produce a compatible subset and selection receipt;
- contracts can build batches only from that compatible subset;
- validators must accept assignments before they become slashable;
- tests cover both the happy path and the refusal path.
