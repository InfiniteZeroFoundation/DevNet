# Auditor Scoring Mechanism

## Summary

DIN should stop treating scoring as:

- one test shard
- one accuracy number
- one average threshold

That works for the current demo path, but it is too narrow for production evaluation and it does not support different task scenarios cleanly.

The protocol needs a scenario-driven scoring system where:

1. eligibility is separated from utility;
2. utility scoring changes by task type and data availability;
3. contribution scoring is treated as a separate plane from admission scoring;
4. no-label tasks fall back to screening rather than pretending to have a real performance score.

The near-term DevNet decision is to score local model updates on the validator side, not client training samples. Validators receive local models or model deltas, run deterministic checks and validation evaluation, publish compact score reports, and the network aggregates validator reports with majority or median rules.

TKNN-Shapley is not the right validator-side tool for this architecture. It values individual training samples and requires access to the client data points. DIN validators do not receive raw client samples, and the design should not add MPC, TEE, ZKP, or raw data disclosure just to make TKNN-Shapley executable. Its useful idea is marginal contribution, not the specific sample-level algorithm.

## Problem Restated

The current stack is locked to one very specific path:

- model owner creates a small test shard per auditor batch;
- auditor computes top-1 accuracy;
- `DINTaskAuditor.sol` averages scores;
- approval is `eligible && avg(score) >= passScore`.

That creates three design failures:

- the protocol mixes conformance, utility, and reward logic into one scalar;
- the contract assumes dataset-based scoring is always available;
- different task scenarios cannot swap in a different scoring method without changing code by hand.

## Core Design Direction

Scoring should be organized into three separate planes.

### 1. Eligibility and admission barrier

This decides whether a submitted local model is safe and useful enough to enter aggregation.

Examples:

- conformance checks
- architecture and tensor-shape match
- finite tensor values
- bounded update norm
- optional cosine or distance check against the consensus update
- holdout utility score
- baseline delta
- auditor agreement bounds

Local models that fail this barrier are not scored for reward and are not accepted into final aggregation.

### 2. Reward or contribution scoring

This decides how much credit or reward a client should receive after the round.

Examples:

- leave-one-out contribution
- post-aggregation marginal utility
- Monte-Carlo marginal gain over accepted updates
- (Rejected for validator-side use: TKNN-Shapley, because validators do not have raw client samples)

### 3. Screening and anomaly scoring

This is the fallback when utility cannot be measured honestly.

Examples:

- malformed model detection
- update norm checks
- peer deviation or anomaly signals

## Scenario-Based Decision Summary

### 1. Trusted labeled holdout exists

Use dataset-based utility scoring, but make it policy-driven and robust:

- stratified shards, not hardcoded `5%`;
- multiple metrics, not only accuracy;
- robust aggregation across auditors, not raw mean.

### 2. Task is imbalanced or metric-sensitive

Use task-specific metrics as first-class policy inputs.

- classification: macro-F1, balanced accuracy, loss, calibration
- regression: MAE, RMSE, R2
- ranking or retrieval: NDCG, MAP, recall@k

### 3. Task has no trusted labeled evaluation set

Do not claim real performance scoring.

Use:

- conformance checks
- anomaly or agreement signals
- `screened` semantics instead of `performance-validated`

### 4. Task needs contribution-aware rewards

Use a separate contribution layer after or alongside admission scoring.

This is where:

- leave-one-out
- marginal global-model delta
- approximate Shapley-style methods

belong.

### 5. Data-quality or privacy-sensitive scenario

In settings where client data privacy is relaxed and raw training data is shared, TKNN-Shapley could be used for data-quality diagnostics and contribution estimation. However, under standard Federated Learning constraints where clients do not share raw training data, TKNN-Shapley is rejected as it cannot execute.

For DIN's current validator model, TKNN-Shapley can only be a client-side curation aid or an offline research diagnostic. It cannot be the production validator scoring mechanism.

## Local Model Scoring Flow

Validators should score a submitted local model update in four steps.

### 1. First barrier: eligibility

Before any expensive validation pass, each validator checks:

- model loads successfully;
- declared architecture, tensor names, shapes, and dtype match the task manifest;
- tensors contain no NaN or Inf values;
- update norm is below the task's configured cap;
- update direction is not an obvious outlier against the round's consensus direction when enough candidate updates exist;
- model artifact and metadata match the expected CID, signer, round, and task.

This is a hard gate. A local model that fails eligibility is rejected before utility scoring.

### 2. Admission score: utility delta on validation data

For labeled tasks, the default validator score is the marginal utility of applying the local update to the current global model:

```text
score_i = metric(global_model + update_i, D_val) - metric(global_model, D_val)
```

The metric is policy-driven. MNIST-like classification can use accuracy, loss, macro-F1, and baseline delta. Imbalanced tasks should use balanced accuracy or macro-F1. Regression and ranking tasks should use their own metric families.

The important detail is that validators should score the update's effect on the current global model, not a standalone local model in isolation.

### 3. Fairness controls for validation shards

A small validation shard is useful for DevNet, but it should not be treated as universally fair or fully general. To keep the score defensible:

- use stratified sampling where labels exist;
- rotate or resample validation shards across rounds;
- publish `evaluationSpecCID` and `metricBundleCID` so results are auditable;
- use multiple validators and median score aggregation;
- include confidence, variance, or disagreement bounds;
- keep no-label tasks in `screening_only` mode rather than inventing a performance score.

The score is only as general as the evaluation spec. DIN should make that explicit instead of hiding it behind a single `passScore`.

### 4. Final aggregation acceptance

A local model update is accepted into final aggregation only if:

- it passes eligibility;
- its validator utility score clears the task threshold;
- a validator majority accepts it;
- the median validator score is within the configured disagreement bound;
- any configured anomaly limits are satisfied.

For MVP aggregation, accepted updates can be averaged using existing FL logic after clipping. For a more robust path, accepted updates should be aggregated with score weighting, coordinate-wise median, trimmed mean, or Krum-style selection depending on the task's threat model.

## Key Decisions

### 1. Scoring policy should live in the manifest

The manifest should declare:

- the scenario;
- the scoring mode for admission;
- the scoring mode for rewards;
- the fallback mode when no labels exist;
- the metric family and aggregation policy.

### 2. Batch evaluation should use an evaluation spec, not only a test dataset CID

The current `testDataCID` field is too narrow.

DIN should move toward an `evaluationSpecCID` that can describe:

- dataset shards when they exist;
- baseline model reference;
- metric list;
- normalization rules;
- screening-only mode when no evaluation set exists.

### 3. On-chain storage should stay compact

The contract should store normalized summary values and CIDs, not every raw metric.

The detailed report should remain off-chain in a metric bundle artifact.

### 4. Robust aggregation should replace raw average

For admission scoring, DIN should prefer:

- median;
- trimmed mean;
- explicit agreement or variance checks.

### 5. TKNN-Shapley is Rejected for Validator-Side Federated Scoring

Because the auditor/validator does not have access to client training features and labels ($x_{train}, y_{train}$), TKNN-Shapley cannot run. It has been rejected from the design.

The rejection is not because the paper is weak. It is because DIN's validator has model updates, not individual client samples. That is an information boundary, not an implementation gap.

### 6. Required scoring algorithms for implementation

The scoring module follows the BlockFLow design (MIT, 2020). BlockFLow operates at the model/update level rather than per sample, applies DP directly to shared weights, uses a median aggregator across evaluators tolerating up to ~50% malicious parties, and distributes rewards proportionally from a pooled bond. This aligns with our architecture point for point. The one BlockFLow mechanism we do not carry over is their evaluation-honesty second score — it exists because their agents score each other; our clients do not evaluate each other, and validator honesty is covered by staking and the cross-validator median.

The scoring module should implement at least three validator-side algorithms:

1. `eligibility_anomaly_gate`: conformance, finite tensors, norm cap, and cosine-to-consensus-direction screening. The norm cap also serves as the DP clipping bound, making it synergistic with differential privacy applied to weight updates.
2. `holdout_delta_score`: validation-set utility delta against the current global model — `metric(global + update_i, D_val) - metric(global, D_val)`. Gain above ε accepts the update.
3. `mc_marginal_gain_score`: sequential marginal contribution with fold-in (`M = M ⊕ u` for accepted updates), averaged over n_perms random orderings. n_perms=1 is the cheap detection baseline; increase only when reward attribution fairness matters. A duplicate update scores near zero once its first copy is folded in, providing duplicate-data discounting without extra machinery.

Cross-validator aggregation should use majority vote for acceptance and median score for the final normalized score across validators. Median tolerance: up to ~half of validators can be malicious.

## Recommended DevNet Default

For the current `mnist-digits` style path, the recommended near-term scoring mode is:

- scenario: `labeled_holdout_classification`
- eligibility: loadability, architecture match, finite tensors, bounded update norm
- utility metrics: accuracy, loss, macro-F1, baseline delta
- validator aggregation: majority accept plus median utility and disagreement bound
- final model aggregation: only eligible, accepted updates; start with clipped averaging, then add robust update aggregation if poisoning pressure increases
- approval: `eligible && utility >= threshold && disagreement <= bound`

Differential privacy can be layered onto the update submission path. DP clipping aligns with the norm cap and limits each client's influence. DP noise reduces score sharpness, so the policy must tune privacy parameters so genuine gains remain above the validation noise floor.

## Deliverables In This Folder

- [Design](scoring-mechanism/design.md): scoring planes, scenario matrix, policy schema, on-chain/off-chain split, and TKNN-Shapley rejection
- [Implementation Plan](scoring-mechanism/implementation.md): phased repo changes across manifest, services, CLI, contracts, and tests

## Definition Of Done

This issue is properly addressed when DIN can:

- choose scoring behavior by declared scenario instead of hardcoded accuracy logic;
- separate eligibility, utility, and contribution outputs;
- support labeled and no-label evaluation modes honestly;
- submit compact score summaries plus off-chain metric bundles;
- aggregate auditor outputs robustly;
- plug in contribution backends such as leave-one-out without rewriting the whole audit flow.

## Out Of Scope For Initial Delivery

The first proper version does not need:

- a full secure-aggregation validation network;
- cryptographic guarantees for private client-reported metrics;
- real-time contribution scoring on every deep-learning round;
- fully automated reward redistribution logic.

The immediate goal is to make scoring mode explicit, scenario-aware, and implementable in the current DevNet architecture.
