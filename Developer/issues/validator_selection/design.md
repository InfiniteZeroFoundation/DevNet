# Validator Selection Design

## Goals

This design is meant to solve a specific operational failure:

- a validator can truthfully want to participate;
- the protocol can still assign work the validator could never complete;
- the failure is only detected after assignment, at the slashing stage.

The design goals are:

- make role requirements explicit and machine-readable;
- separate registration intent from assignment eligibility;
- keep detailed capability logic off-chain where hardware inspection is possible;
- keep assignment accountability on-chain;
- preserve randomization and fairness within the compatible subset;
- avoid forcing the contracts to parse or validate rich hardware metadata.

## Non-Goals

This design does not try to provide:

- cryptographic proof of hardware claims;
- exact runtime prediction for every node;
- perfect scheduling under arbitrary local operator behavior;
- a full reputation market in the first release.

## Current Constraints In This Repository

The proposal needs to fit the current codebase rather than an abstract future system.

Today:

- `DINTaskCoordinator.registerDINaggregator(uint)` only checks stake;
- `DINTaskAuditor.registerDINAuditor(uint)` only checks stake;
- `DINTaskAuditor.createAuditorsBatches(uint)` shuffles the full auditor pool;
- `DINTaskCoordinator.autoCreateTier1AndTier2(uint)` shuffles the full aggregator pool;
- the model owner CLI already drives batch creation through `dincli/cli/modelownerd/auditor_batches.py` and `dincli/cli/modelownerd/aggregation.py`;
- the manifest is already anchored through `DINModelRegistry.manifestCID`.

The current off-chain workload shape also matters:

- the auditor service loads one model plus one test shard at a time;
- the aggregator service currently downloads all assigned models and loads all state dicts before averaging.

That means the protocol should model auditor and aggregator feasibility separately instead of treating both as generic validator work.

## Proposed Architecture

The design introduces four artifacts.

### 1. Task Capability Spec

This is the model-owner-authored description of workload requirements for each role.

For `v1`, it should live inside the manifest under a new `capability_spec` block.

Why inline first:

- it is automatically versioned by the existing manifest CID;
- it avoids adding a second metadata fetch path before the format stabilizes;
- `dincli` already loads the manifest as its runtime configuration object.

### 2. Validator Capability Profile

This is a validator-authored snapshot of local resources and operator limits.

It should include:

- measured hardware facts such as RAM, disk, CPU, GPU, and bandwidth;
- operator-declared constraints such as max concurrent tasks or unsupported roles;
- a generated-at timestamp;
- a signature or wallet binding for auditability.

The profile can be stored locally and optionally uploaded to IPFS. The on-chain registration only needs a compact reference to it.

### 3. Selection Receipt

This is the auditable explanation for how a compatible subset was built.

It should record:

- the GI and role;
- the full registered pool;
- the capability spec hash or manifest version used;
- each validator profile reference used for evaluation;
- exclusion reasons for hard mismatches;
- the compatible subset;
- the randomness seed used for the final batch order;
- the final batch composition.

The selection receipt is important because once selection logic moves off-chain, the protocol still needs a way to inspect whether the model owner or daemon filtered the pool fairly.

### 4. Assignment Acceptance

This is the explicit on-chain acknowledgement that a validator accepts a concrete batch and its deadline.

This acceptance is the point where slashability should begin.

## Data Placement

Use the following split.

| Artifact | Location | Reason |
|---|---|---|
| `capability_spec` | manifest JSON | already anchored by `DINModelRegistry` |
| validator capability profile | local file, optionally IPFS | rich hardware metadata is off-chain by nature |
| selection receipt | IPFS plus on-chain hash or CID | auditable without bloating storage |
| assignment acceptance | on-chain transaction | clear accountability boundary |

## Capability Spec Shape

The initial manifest shape should be explicit rather than inferred from prose.

Example:

```json
"capability_spec": {
  "spec_version": 1,
  "selection_policy": {
    "match_mode": "hard_fail",
    "randomization": "shuffle_within_compatible_subset",
    "selection_receipt_required": true,
    "acceptance_required": true,
    "profile_ttl_seconds": 86400
  },
  "roles": {
    "clients": {
      "training": {
        "gpu_required": false,
        "min_ram_bytes": 4294967296,
        "min_disk_bytes": 8589934592,
        "expected_upload_bytes": 26214400,
        "estimated_wall_clock_seconds": 1800
      }
    },
    "auditors": {
      "batch": {
        "auditors_per_batch": 3,
        "models_per_batch": 3,
        "serialized_evaluation": true,
        "test_dataset_bytes": 104857600,
        "max_model_artifact_bytes": 52428800
      },
      "resources": {
        "min_ram_bytes": 8589934592,
        "min_disk_bytes": 21474836480,
        "gpu_required": false,
        "deadline_seconds": 3600
      }
    },
    "aggregators": {
      "tier1": {
        "aggregators_per_batch": 3,
        "models_per_batch": 3,
        "requires_full_in_memory_aggregation": true,
        "max_model_artifact_bytes": 52428800,
        "workspace_bytes": 268435456
      },
      "tier2": {
        "aggregators_per_batch": 3,
        "inputs_per_batch": 3,
        "requires_full_in_memory_aggregation": true,
        "max_model_artifact_bytes": 52428800,
        "workspace_bytes": 268435456
      },
      "resources": {
        "min_ram_bytes": 17179869184,
        "min_disk_bytes": 32212254720,
        "gpu_required": false,
        "deadline_seconds": 3600
      }
    }
  }
}
```

The exact field names can still evolve, but the design should preserve these principles:

- role-specific blocks rather than one generic validator block;
- static workload facts separate from minimum resource requirements;
- explicit selection policy rather than implicit CLI behavior.

## Validator Capability Profile Shape

Example:

```json
{
  "spec_version": 1,
  "validator": "0xabc123...",
  "generated_at": 1748041200,
  "resources": {
    "ram_bytes": 34359738368,
    "free_disk_bytes": 214748364800,
    "cpu_cores": 16,
    "gpu_present": false,
    "gpu_vram_bytes": 0,
    "download_mbps": 400,
    "upload_mbps": 100
  },
  "limits": {
    "supported_roles": ["auditors", "aggregators"],
    "max_concurrent_assignments": 1,
    "supports_streaming_aggregation": false
  },
  "signature": "0x..."
}
```

Important point:

- this profile is not a trustless proof;
- it is an operational attestation used for filtering and later accountability.

## Matching Rules

The selector should treat fields as either hard constraints or soft ranking inputs.

### Hard constraints

These should exclude a validator from the eligible pool:

- not an active staked validator;
- wrong role or role not supported;
- manifest requires GPU and validator has none;
- RAM below minimum;
- disk below minimum;
- profile older than the allowed TTL;
- declared concurrency limit already exhausted;
- aggregation requires full in-memory processing and the validator cannot satisfy that mode.

### Soft inputs

These should rank validators inside the compatible subset, but not automatically exclude them:

- extra RAM or disk headroom above the minimum;
- bandwidth above the expected transfer volume;
- historical success rate;
- recent availability;
- optional stake weighting if DIN decides to use it later.

For the first release, randomization should remain simple:

1. filter to the compatible subset;
2. shuffle within that subset;
3. build batches from the shuffled list.

That preserves fairness while avoiding assignment to known-mismatched nodes.

## Role-Specific Feasibility Logic

### Auditors

Auditor feasibility should assume serialized evaluation unless the manifest says otherwise.

The minimum estimate should include:

- one model artifact;
- one loaded model instance;
- one test dataset shard;
- inference workspace;
- temporary download and extraction space.

### Aggregators

Aggregator feasibility should be stricter because the current service loads all assigned model state dicts before averaging.

For the current implementation, the peak memory estimate should scale with:

- number of assigned model artifacts;
- decoded in-memory model state;
- base model state;
- aggregation workspace.

That is the main reason aggregators should have their own capability threshold rather than sharing the auditor threshold.

## Contract Design

The contracts should enforce accountability boundaries, not parse hardware descriptions.

### Registration

Prefer versioned registration methods instead of replacing the existing ABI immediately.

Recommended additions:

- `registerDINaggregatorV2(uint gi, bytes32 capabilityProfileCID)`
- `registerDINAuditorV2(uint gi, bytes32 capabilityProfileCID)`

New storage:

- `aggregatorCapabilityProfileCID[gi][validator]`
- `auditorCapabilityProfileCID[gi][validator]`
- optional registration timestamp for profile freshness checks off-chain

Why versioned methods:

- existing deployments and ABIs keep working;
- old manifests can continue to use legacy registration in dev mode;
- new manifests can require the `V2` path.

### Batch Creation

The key contract change is to stop blind pool-wide shuffling.

Recommended additions:

- `createAuditorsBatchesV2(uint gi, address[] calldata eligibleAuditors, bytes32 selectionReceiptCID)`
- `createTier1AndTier2V2(uint gi, address[] calldata eligibleTier1Aggregators, address[] calldata eligibleTier2Aggregators, bytes32 selectionReceiptCID)`

Contract validation should remain simple:

- each address in the eligible array must already be registered for that GI;
- each address must still satisfy stake and active-validator checks;
- the contract stores the selection receipt reference and emits it in an event.

The contract does not need to verify the capability logic itself. That stays in the selector.

### Assignment Acceptance

Assignment acceptance should be layered on top of the current state machine rather than forcing a full GI-state rewrite.

Recommended additions:

- `acceptAuditorBatch(uint gi, uint batchId)`
- `declineAuditorBatch(uint gi, uint batchId)`
- `acceptTier1Batch(uint gi, uint batchId)`
- `declineTier1Batch(uint gi, uint batchId)`
- `acceptTier2Batch(uint gi, uint batchId)`
- `declineTier2Batch(uint gi, uint batchId)`

Recommended storage:

- per-batch validator acceptance status;
- optional acceptance deadline;
- optional accepted-count per batch.

Recommended gating:

- `startLMsubmissionsEvaluation()` should require each audit batch to have enough accepted auditors to satisfy quorum;
- `startT1Aggregation()` should require each T1 batch to have enough accepted aggregators;
- `startT2Aggregation()` should require the T2 batch to have enough accepted aggregators.

This approach keeps most GI states intact and treats acceptance as a prerequisite to phase transition.

### Slashing

Slashing should change from "assigned and failed" to "accepted and failed."

That means:

- non-accepted validators are not slashed for missing submissions;
- accepted validators are slashed for no-show or invalid submission exactly as before;
- repeated registration with stale or false capability data can later become a separate penalty path, but that is not required for the first version.

## CLI And Daemon Design

The first selector should live in `dincli`, because the current model-owner CLI already owns batch creation.

Recommended flow:

1. model owner publishes a manifest with `capability_spec`;
2. validator runs `preflight` locally;
3. validator uploads or stores a capability profile and registers with its CID;
4. model owner CLI loads the registered pool and matching profiles;
5. model owner CLI builds a compatible subset and selection receipt;
6. model owner CLI calls the `V2` batch-creation function;
7. assigned validators accept or decline;
8. aggregation or evaluation starts only after accepted quorum exists.

Later, the same logic can move behind `dind` without changing the contract model.

## Trust Model

This design accepts that capability checking is initially honest-but-verifiable, not trustless.

That is still useful because:

- local auto-detection is much better than no detection;
- capability profiles are reviewable after the fact;
- selection receipts make exclusion decisions inspectable;
- post-acceptance slashing stops the protocol from punishing obvious preflight failures.

The protocol should prefer auditability over pretending to have strong on-chain hardware verification that it does not actually have.

## Recommended Release Shape

The design is intentionally staged.

### Phase 1

- add manifest capability spec;
- add validator capability profile handling;
- add eligible-pool batch creation;
- add selection receipts.

### Phase 2

- add assignment acceptance;
- gate phase transitions on accepted quorum;
- slash only accepted workers.

### Phase 3

- move matching to `dind`;
- add availability and historical reliability inputs;
- add more sophisticated ranking inside the compatible subset.
