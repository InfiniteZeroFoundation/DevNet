# Scoring Mechanism Implementation Plan

## Implementation Strategy

DIN should implement scoring in phases, not as one monolithic rewrite.

The right order is:

1. move scoring policy into explicit configuration;
2. widen the service and CLI interfaces so auditors can produce richer outputs;
3. add compact `V2` contract storage for normalized summaries;
4. add contribution backends such as leave-one-out.

This preserves the current flow while removing the hardcoded assumptions that make it brittle.

## Workstream 1: Manifest-Level Scoring Policy

### Goal

Make the task’s scoring scenario explicit and machine-readable.

### Files To Update

- `Documentation/technical/manifest.md`
- `cache_model_0/manifest.json`
- optionally `Documentation/auditors.md`, `Documentation/model-owner.md`, and `Developer/tooling/model-owner-services.md`

### Changes

- add a `scoring_policy` block to the manifest;
- define scenario, admission mode, contribution mode, fallback mode, metric family, and aggregation policy;
- document how normalized utility scores are derived from raw metrics;
- add one concrete default policy for the current MNIST-style task.

### Why This Comes First

Without explicit policy, the rest of the implementation would still rely on hidden service code decisions.

## Workstream 2: Shared Scoring Runtime

### Goal

Create one reusable scoring layer instead of scattering scoring rules across `auditor.py` and `modelowner.py`.

### Recommended New Modules

- `dincli/services/scoring.py`
- optionally `dincli/services/contribution.py`

### Responsibilities

- load `scoring_policy` from the manifest;
- normalize raw task metrics into a contract-friendly utility score;
- calculate robust aggregates such as median or trimmed mean;
- define typed result objects for eligibility, utility, anomaly, and contribution;
- expose mode-specific evaluators such as `holdout_delta` and `screening_only`.

### Existing Files To Update

- `dincli/services/runtime.py`
- `dincli/cli/utils.py`

So they can surface policy configuration cleanly to service code.

## Workstream 3: Model-Owner Evaluation Specs

### Goal

Replace the current hardcoded per-batch dataset shard behavior with policy-driven evaluation-spec generation.

### Existing Files To Update

- `dincli/services/modelowner.py`
- `cache_model_0/services/modelowner.py`
- `dincli/cli/modelownerd/auditor_batches.py`

### Changes

- evolve `create_audit_testDataCIDs(...)` into an evaluation-spec generator rather than a pure test-shard generator;
- allow stratified sampling, repeated shards, or screening-only mode;
- make shard size, repetition count, and sampling policy configurable from `scoring_policy`;
- emit `evaluationSpec` artifacts that may include dataset shard CIDs, baseline model CID, metric list, and screening flags.

### Recommended Interface Direction

Instead of returning only:

- `list[testDataCID]`

move toward returning:

- `list[evaluationSpecCID]`

where a spec may still contain dataset shard CIDs for holdout modes.

## Workstream 4: Auditor Service Result Object

### Goal

Widen the auditor service interface from one scalar plus one boolean to a richer normalized summary.

### Existing Files To Update

- `dincli/services/auditor.py`
- `cache_model_0/services/auditor.py`
- `dincli/cli/auditor.py`

### Current Limitation

Today `Score_model_by_auditor(...)` returns:

- `score`
- `eligible`

and the CLI passes those directly to `setAuditScorenEligibility(...)`.

### Recommended New Result Shape

Move toward a dict or dataclass such as:

```python
{
    "eligible": True,
    "utility_score_bps": 7120,
    "baseline_delta_bps": 180,
    "anomaly_score_bps": 250,
    "screening_only": False,
    "metric_bundle_cid": "bafy..."
}
```

### Service Responsibilities

- compute raw scenario-specific metrics;
- normalize them through the shared scoring runtime;
- upload the full metric bundle to IPFS;
- return compact summary values for on-chain submission.

### CLI Responsibilities

Update `dincli/cli/auditor.py` so that:

1. it loads the batch evaluation spec;
2. it invokes the selected scoring mode;
3. it prints both raw and normalized results to the operator;
4. it submits the normalized summary through a `V2` contract method.

## Workstream 5: Task-Auditor Contract V2

### Goal

Support multiple scoring scenarios on chain without teaching the contract every raw metric family.

### Contracts To Update

- `foundry/src/DINTaskAuditor.sol`
- `foundry/src/DINShared.sol`
- mirrored files in `hardhat/contracts/`

### Recommended Structural Changes

#### 1. Replace or supplement `testDataCID`

Current `AuditBatch` is too narrow:

- `bytes32 testDataCID`

Recommended direction:

- `bytes32 evaluationSpecCID`

or keep both temporarily during migration.

#### 2. Add `V2` submission method

Recommended shape:

- `setAuditResultV2(uint gi, uint batchId, uint modelIndex, bool eligible, uint16 utilityScoreBps, int32 baselineDeltaBps, uint16 anomalyScoreBps, bool screeningOnly, bytes32 metricBundleCID)`

The exact types can still be tuned, but the method should accept normalized summary fields plus a CID for the full report.

#### 3. Extend stored final result

`LMSubmission` or adjacent storage should hold:

- final normalized utility score;
- final agreement or variance summary;
- screening-only flag;
- optional final report CID.

#### 4. Add robust aggregation

`finalizeEvaluationV2()` should:

- aggregate utility scores by median or trimmed mean;
- compute disagreement or variance;
- finalize approval from policy-compatible thresholds.

### Keep Solidity Simple

The contract should not parse:

- accuracy versus F1 versus NDCG;
- regression-specific formulas;
- raw contribution backend internals.

Those stay off-chain. The contract should only consume normalized summaries.

## Workstream 6: Coordinator and Approval Semantics

### Goal

Make downstream approval and aggregation depend on richer evaluation outputs, not only `passScore`.

### Contracts To Update

- `foundry/src/DINTaskCoordinator.sol`
- `foundry/src/DINTaskAuditor.sol`

### Changes

- stop relying exclusively on `params.passScore` as the universal approval gate;
- add generic threshold fields such as `minUtilityScore` and optional disagreement bounds;
- keep current `approvedModelIndexes()` behavior, but drive it from richer evaluation results.

### Migration Note

For compatibility, `passScore` can initially remain as the threshold for normalized utility score in the `V2` path while the rest of the fields are added around it.

## Workstream 7: Contribution Scoring Backends

### Goal

Add reward-oriented contribution scoring without polluting the base admission path.

### Recommended New Module

- `dincli/services/contribution.py`

### Initial Backends

- `leave_one_out`
- `marginal_global_delta`

*(Note: `tknn_shapley` and `dp_tknn_shapley` were originally proposed but have been rejected due to FL privacy constraints. See [Rejected Ideas: TKNN-Shapley](../../rejected-ideas/tknn-shapley.md) for details.)*

### Important Scope Rule

These backends should produce:

- `contributionReportCID`
- client or local-model contribution scores

They should not replace the base admission path for current holdout-evaluated tasks.

## Workstream 8: Model-Owner and Reward Consumers

### Goal

Define where admission scores end and reward scores begin in the operational workflow.

### Existing Files To Update

- `dincli/cli/modelownerd/lms_evaluation.py`
- `dincli/cli/modelownerd/aggregation.py`
- later reward-related docs or logic once implemented

### Changes

- show normalized utility, disagreement, and screening flags instead of only final average score;
- optionally show contribution report references once contribution backends exist;
- ensure Tier 1 aggregation uses admitted models only;
- reserve reward weighting for a separate post-evaluation or post-aggregation step.

## Workstream 9: Documentation

### Goal

Make the new scenario-driven model understandable for contributors and model owners.

### Files To Update

- `Documentation/technical/DINTaskAuditor.md`
- `Documentation/technical/manifest.md`
- `Documentation/auditors.md`
- `Documentation/model-owner.md`
- `Developer/tooling/model-owner-services.md`
- optionally `Developer/tooling/model-owner-contracts.md`

### Changes

- document the `scoring_policy` block;
- document `evaluationSpec` artifacts;
- document `V2` audit-result submission;
- explain the difference between admission scoring and contribution scoring;
- document why TKNN-Shapley was rejected (referencing [Rejected Ideas: TKNN-Shapley](../../rejected-ideas/tknn-shapley.md)).

## Workstream 10: Tests

### Contract Tests

Add or expand tests under:

- `foundry/test/`
- optionally `hardhat/test/`

Test cases should include:

- `V2` audit submission with normalized summary fields;
- holdout evaluation approval using median or trimmed mean;
- rejection when disagreement exceeds bounds;
- screening-only evaluation path with no holdout dataset;
- backward compatibility with the legacy scalar score path during migration.

### Python Tests

Add tests under `tests/` for:

- `scoring_policy` parsing;
- stratified evaluation-spec generation;
- normalization from raw metrics to utility score;
- robust aggregation helpers;
- auditor-result object generation;
- contribution backend interfaces (like leave-one-out and marginal delta).

## Suggested Delivery Phases

### Phase A: Better Holdout Scoring

- add `scoring_policy`;
- replace hardcoded 5% behavior with policy-driven evaluation specs;
- compute richer holdout metrics;
- normalize them into one utility summary;
- keep contribution mode disabled.

This is the first practical upgrade for the current MNIST-style flow.

### Phase B: Contract V2

- add `evaluationSpecCID`;
- add `setAuditResultV2(...)`;
- add robust summary aggregation;
- keep legacy `setAuditScorenEligibility(...)` temporarily for migration.

This is where the protocol stops being hardcoded to one scalar score.

### Phase C: Separate Contribution Path

- add `leave_one_out` or marginal-delta contribution backends;
- generate `contributionReportCID`;
- surface contribution outputs in model-owner tooling.

This is the phase that cleanly separates reward logic from admission logic.

### Phase D: No-Label and Private Extensions

- add `screening_only` mode as a first-class path;
- later explore private client-side metric aggregation.

This is where DIN handles evaluation honesty in tasks with weak or absent labels.

## Migration Notes

Use feature detection rather than a flag day cutover.

Recommended approach:

- new manifests declare `scoring_policy`;
- new services produce normalized audit results;
- new contracts expose `V2` submission methods;
- `dincli` checks which path is available and only uses legacy scalar scoring when required.

This preserves the current demo path while giving contributors a clear upgrade target.

## Definition Of Done

The implementation is complete when:

- scoring scenario is declared in the manifest;
- model-owner tooling generates evaluation specs instead of hardcoded fixed-percentage shards;
- auditor services return normalized summary results plus full metric bundles;
- the contract accepts and finalizes richer `V2` audit results;
- admission and contribution logic are separate;
- DIN has a clean optional path for contribution analysis (like leave-one-out).
