# Scoring Mechanism Design

## Goals

This design solves a specific mismatch in the current DIN evaluation model:

- the repo has one auditor contract path;
- real tasks need different scoring behavior depending on labels, task type, and reward policy;
- the current interface only carries one scalar score and one boolean eligibility vote.

The design goals are:

- make scoring mode explicit and scenario-driven;
- separate admission scoring from reward or contribution scoring;
- support dataset-based and dataset-free flows without lying about what the score means;
- define which local models are eligible for scoring and final aggregation;
- keep rich metrics off-chain while making compact decisions on-chain;
- document rejected ideas (e.g., TKNN-Shapley) to ensure future iterations avoid incompatible valuation designs.

## Non-Goals

This design does not try to provide:

- perfect universal metrics for every ML task;
- trustless verification of every off-chain evaluation artifact;
- a complete reward-distribution mechanism in the first iteration;
- per-round exact Shapley valuation for arbitrarily large deep models.

## Current Constraints In This Repository

The design has to fit the code that exists today.

Today:

- `cache_model_0/services/auditor.py` and `dincli/services/auditor.py` return `(score, eligible)`;
- `cache_model_0/services/modelowner.py` and `dincli/services/modelowner.py` generate one test shard CID per batch;
- `DINTaskAuditor.setAuditScorenEligibility(...)` accepts one scalar score and one boolean vote;
- `DINTaskAuditor.finalizeEvaluation(...)` uses mean score and `passScore`;
- `DINTaskAuditor.AuditBatch` stores `testDataCID`, not a richer evaluation spec.

That means the scoring redesign should keep the same broad auditor flow, but widen the artifacts and summary objects that pass through it.

## Scoring Planes

The most important design decision is to stop calling everything "score."

DIN needs three separate scoring planes.

### 1. Eligibility Plane

This answers:

- does the model load;
- does it match the expected architecture;
- are tensor shapes correct;
- are there NaNs or invalid weights;
- is the update obviously corrupted or out of policy;
- is the update inside the configured norm and consensus-distance bounds.

This is a gate, not a reward score.

A model that fails the eligibility plane is not considered for utility scoring, rewards, or final aggregation.

### 2. Utility Plane

This answers:

- how useful is this local model for admission to aggregation;
- how well does it perform on a trusted evaluation mechanism for this task scenario.

This is the score that most directly determines aggregation approval.

### 3. Contribution Plane

This answers:

- how much useful signal did the client or shard contribute relative to others;
- how should rewards, reputation, or diagnostics be weighted.

This is where leave-one-out and marginal delta belong (TKNN-Shapley was rejected due to FL privacy constraints).

## Validator-Side Local Model Lifecycle

Each submitted local model or model delta should move through the same lifecycle on every validator.

| Stage | Question | Output | Aggregation effect |
|---|---|---|---|
| eligibility | is this artifact valid and in policy | `eligible: bool`, anomaly tags | failed models are dropped immediately |
| admission utility | does this update improve the current global model on the evaluation spec | normalized utility and delta metrics | accepted only if score clears threshold |
| validator consensus | do validators agree on this update | majority accept, median score, disagreement | only majority-accepted updates survive |
| final model aggregation | how should surviving updates be combined | accepted update set and optional weights | updates enter FL aggregation |
| contribution | how much credit should each accepted update get | contribution report | later rewards/reputation |

This means local models accepted for final aggregation are exactly the ones that pass eligibility, pass utility thresholding, and survive cross-validator consensus. A good standalone local model is not enough; the score should measure its effect when applied to the current global model.

## Scenario Matrix

The protocol should select scoring mode from scenario, not from one default metric.

| Scenario | Main question | Recommended admission mode | Recommended contribution mode |
|---|---|---|---|
| labeled holdout classification | is the submitted model good enough to aggregate | stratified holdout metrics plus baseline delta | optional post-round delta or leave-one-out |
| imbalanced classification | does the model help across minority classes | macro-F1, balanced accuracy, loss | optional reward reweighting by class-sensitive delta |
| regression | does the model reduce prediction error | MAE, RMSE, R2 | optional leave-one-out or marginal delta |
| ranking or retrieval | does the model improve ranking quality | NDCG, MAP, recall@k | optional contribution on ranking delta |
| no trusted labels | can the model be screened safely | conformance plus anomaly-only screening | reward disabled or weak heuristic |
| data quality diagnostics | which clients or shards are noisy or mislabeled | keep admission separate | leave-one-out or marginal delta (TKNN-Shapley rejected) |
| privacy-sensitive contribution analysis | how can DIN value updates without exposing raw examples | keep admission simple | DP-compatible marginal update scoring |

This matrix is the core reason DIN should not keep a one-size-fits-all `accuracy` path.

## Why TKNN-Shapley is Rejected

TKNN-Shapley is completely incompatible with the Federated Learning setting used in DIN. 

1. **Privacy Violation**: TKNN-Shapley requires direct, centralized access to training features and labels ($x_{train}, y_{train}$) to calculate pairwise distance bounds. Under FL constraints, this data is private and not shared with the auditor or coordinator.
2. **Target Mismatch**: TKNN-Shapley evaluates the marginal contribution of *individual data points*, not local models or clients.

Thus, TKNN-Shapley is rejected for DIN validator-side scoring. It can still be documented as a client-side data curation or offline diagnostic idea in settings where raw examples are deliberately available, but it should not appear in the validator admission or reward-critical path.

The useful property to keep is marginal contribution. DIN should implement that property over model updates, not over raw samples.

## Recommended Mode Library

DIN should define a small library of scoring modes instead of one hardcoded algorithm.

### Admission modes

- `holdout_metrics`
- `holdout_delta`
- `screening_only`

### Contribution modes

- `none`
- `leave_one_out`
- `marginal_global_delta`
- `mc_marginal_gain`
- (Rejected for validator-side use: `tknn_shapley`, `dp_tknn_shapley`)

### Aggregation modes for auditor reports

- `mean`
- `median`
- `trimmed_mean`

For production-oriented design, `median` or `trimmed_mean` should be preferred over `mean`.

## Required Scoring Algorithms

DIN should implement the following algorithms first. They are intentionally model-update based, validator executable, and compatible with the current privacy boundary.

### Algorithm 1: `eligibility_anomaly_gate`

Purpose: reject malformed, invalid, or obviously hostile local model updates before expensive scoring.

Inputs:

- current global model metadata;
- submitted local model or weight delta;
- task manifest architecture spec;
- optional set of candidate updates for consensus-direction checks;
- policy knobs: `max_update_norm`, `min_cosine_to_consensus`, dtype and tensor-shape rules.

Procedure:

```text
if artifact CID, signer, task, or round does not match: reject
if model cannot be loaded: reject
if architecture, tensor names, shapes, or dtype do not match: reject
if any tensor has NaN or Inf: reject
if norm(update) > max_update_norm: reject
if consensus direction is available and cosine(update, consensus) < min_cosine_to_consensus: reject
else eligible
```

Output:

- `eligible: bool`;
- `anomaly_score_bps`;
- diagnostic tags such as `shape_mismatch`, `nan_tensor`, `norm_outlier`, or `direction_outlier`.

Notes:

- DP clipping should share the same norm cap where possible.
- Under strong DP noise, cosine-to-consensus should be softened or disabled because privacy noise and malicious deviation can look similar.

### Algorithm 2: `holdout_delta_score`

Purpose: score whether a candidate update improves the current global model on trusted validation data.

Inputs:

- current global model `M_g`;
- candidate update `u_i`;
- evaluation spec and validation shard `D_val`;
- task metric family;
- thresholds such as `min_delta_bps`, `min_utility_score`, and `max_loss_increase`.

Procedure:

```text
baseline = metric(M_g, D_val)
candidate = metric(apply_update(M_g, u_i), D_val)
delta = candidate - baseline
utility_score = normalize(candidate, delta, policy)
accept = eligible && delta >= min_delta_bps && utility_score >= min_utility_score
```

Output:

- `accept: bool`;
- `utility_score_bps`;
- `baseline_delta_bps`;
- raw metrics in `metricBundleCID`.

Metric examples:

- classification: accuracy, loss, macro-F1, balanced accuracy;
- regression: MAE, RMSE, R2;
- ranking or retrieval: NDCG, MAP, recall@k.

Validation fairness controls:

- use stratified shards where labels exist;
- rotate or resample shards across rounds;
- publish evaluation specs and metric bundles by CID;
- report confidence, variance, or disagreement bounds;
- aggregate validator reports by median, not raw mean.

A small validation shard is acceptable for MVP detection, but it should not be overclaimed. The protocol should call the result `performance_validated` only when the evaluation spec is strong enough; otherwise use `screened` semantics.

### Algorithm 3: `mc_marginal_gain_score`

Purpose: estimate contribution and future reward weight by measuring each accepted update's marginal gain when folded into the current round model.

Inputs:

- current global model `M_g`;
- eligible candidate updates;
- validation data or evaluation function;
- `n_perms` random permutations;
- `min_gain_bps`.

Procedure:

```text
score[i] = 0
votes[i] = 0

for permutation in random_permutations(updates, n_perms):
    M = M_g
    for update i in permutation:
        gain = metric(apply_update(M, u_i), D_val) - metric(M, D_val)
        if gain > min_gain_bps:
            score[i] += gain
            votes[i] += 1
            M = apply_update(M, u_i)

score[i] = score[i] / n_perms
accept[i] = votes[i] > n_perms / 2
```

Output:

- contribution score per update;
- optional accept vote per update;
- duplicate and redundancy discounting because earlier accepted signal reduces later marginal gain.

Notes:

- `n_perms = 1` is enough for a cheap MVP admission aid.
- Higher `n_perms` is more useful when rewards are enabled and attribution fairness matters.
- This is a Monte-Carlo Shapley-like method over model updates, not TKNN-Shapley over data samples.

### Cross-Validator Aggregation

After validators independently run the selected algorithms:

```text
final_accept(i) = majority_vote(validators, accept_v[i])
final_score(i) = median(validators, score_v[i]) for accepted updates
```

The median score tolerates dishonest or noisy validators as long as fewer than half of the validators collude or fail in the same direction. Validator staking, reputation, and dispute handling belong around this aggregation layer.

### Final Update Aggregation

The accepted update set should then feed the normal FL aggregation path.

MVP options:

- clipped average over accepted updates;
- score-weighted average using `final_score` as weights.

Robust options:

- coordinate-wise median;
- trimmed mean;
- Krum or multi-Krum style selection when the round has enough participants.

The final aggregation algorithm is separate from scoring, but it must only consume updates that passed scoring.

## Policy Schema

The static configuration should live in the manifest as a `scoring_policy` block.

Example:

```json
"scoring_policy": {
  "spec_version": 1,
  "scenario": "labeled_holdout_classification",
  "admission_mode": "holdout_delta",
  "contribution_mode": "none",
  "fallback_mode": "screening_only",
  "normalization": {
    "utility_scale": "basis_points",
    "max_utility": 10000
  },
  "eligibility_checks": {
    "require_loadable_model": true,
    "require_architecture_match": true,
    "reject_nan_tensors": true,
    "max_update_norm": 25.0
  },
  "metrics": {
    "primary": ["accuracy", "macro_f1", "loss", "baseline_delta"],
    "thresholds": {
      "min_utility_score": 6500,
      "min_baseline_delta_bps": 0,
      "max_auditor_variance_bps": 800
    }
  },
  "aggregation": {
    "auditor_score_aggregation": "median",
    "require_variance_bound": true
  },
  "validator_consensus": {
    "acceptance_rule": "majority_vote",
    "score_rule": "median",
    "max_disagreement_bps": 800
  },
  "contribution": {
    "enabled": false,
    "backend": "none"
  }
}
```

This block should define what the task expects, but it should not contain per-round shard assignments or dynamic batch artifacts.

## Dynamic Evaluation Spec

The per-batch execution plan should be a separate off-chain artifact referenced during a GI.

Call it `evaluationSpec`.

Example:

```json
{
  "spec_version": 1,
  "gi": 4,
  "batch_id": 2,
  "mode": "holdout_delta",
  "screening_only": false,
  "dataset_shard_cids": [
    "bafy...",
    "bafy..."
  ],
  "baseline_model_cid": "bafy...",
  "metric_bundle": {
    "primary": ["accuracy", "macro_f1", "loss", "baseline_delta"],
    "normalization": "basis_points"
  },
  "sampling": {
    "strategy": "stratified",
    "repetitions": 2
  }
}
```

Why DIN needs this:

- batch-specific shard assignments are dynamic;
- some scenarios have no dataset shard at all;
- the baseline reference may change by GI;
- the auditor needs more context than a single `testDataCID`.

## On-Chain and Off-Chain Split

DIN should keep detailed evaluation data off-chain and only store compact summaries on-chain.

### Off-chain artifacts

- `scoring_policy` in manifest
- `evaluationSpec` per batch or GI
- full auditor metric bundle
- optional contribution report output

### On-chain summaries

- eligibility vote
- normalized utility score
- optional normalized baseline delta
- optional anomaly or disagreement score
- `metricBundleCID`
- evaluation mode or screening flag

This split keeps the contract practical while still making scoring auditable.

## Normalized Audit Result

To support scenario-specific raw metrics without exploding contract complexity, auditors should submit a normalized summary object.

Conceptually:

```text
AuditResult
- eligible: bool
- utility_score_bps: uint16
- baseline_delta_bps: int32
- anomaly_score_bps: uint16
- screening_only: bool
- metric_bundle_cid: bytes32
```

The rule is:

- raw task-specific metrics stay in the metric bundle;
- off-chain policy maps them into normalized scores;
- the contract only aggregates normalized summaries.

This is the cleanest way to support multiple scenarios without teaching Solidity every ML metric family.

## Robust Auditor Aggregation

The current average-based aggregation is too brittle.

DIN should aggregate auditor summaries using one of:

- median utility score;
- trimmed mean utility score;
- variance or disagreement bound.

Recommended approval policy:

- `eligible_quorum_met == true`
- `median_utility_score >= min_utility_score`
- `auditor_variance <= max_auditor_variance`
- if required, `baseline_delta >= min_delta`

This keeps the approval rule robust even when one auditor is noisy or dishonest.

## No-Label Scenario

When no trusted evaluation set exists, DIN should downgrade honestly.

Recommended semantics:

- do not generate a normal utility score;
- run only conformance and anomaly checks;
- set `screening_only = true`;
- mark submissions as `screened` rather than `performance_validated`.

That avoids the architectural mistake of turning weak proxy signals into false performance claims.

## Contribution Scoring Design

Contribution scoring should be a separate pipeline from admission scoring.

### Supported backends

- `leave_one_out`
- `marginal_global_delta`
- `mc_marginal_gain`

*(Note: Advanced backends like `tknn_shapley` and `dp_tknn_shapley` are rejected for validator-side scoring because validators do not receive raw client samples.)*

### Output form

Contribution backends should produce a separate `contributionReportCID` that maps:

- client address or local-model index;
- contribution score;
- confidence or privacy parameters;
- diagnostic tags such as noisy, low-value, or suspicious.

This report can later feed reward distribution or governance decisions without changing the admission path.

## Recommended DevNet Defaults

DIN should not try to enable every mode at once.

### Current MNIST-like path

Use:

- `scenario = labeled_holdout_classification`
- `admission_mode = holdout_delta`
- `contribution_mode = none`
- metrics: `accuracy`, `loss`, `macro_f1`, `baseline_delta`
- eligibility algorithm: `eligibility_anomaly_gate`
- score algorithm: `holdout_delta_score`
- validator aggregation: majority accept plus median score
- final update aggregation: clipped average over accepted updates

### First advanced extension

Add:

- `contribution_mode = mc_marginal_gain`
- score-weighted reward reports over accepted updates

### Later experimental extension

Add other privacy-preserving contribution modes as needed, ensuring they do not leak client training data. Leave-one-out can remain available for small rounds or offline analysis, but it is likely more expensive than Monte-Carlo marginal gain.

## Privacy and DP Interaction

Differential privacy on submitted updates is compatible with this design.

Recommended interpretation:

- DP clipping and `max_update_norm` should be aligned, because both cap per-client influence;
- DP noise can blur small utility deltas, so `min_delta_bps` must sit above the empirical noise floor;
- validators should report uncertainty or repeated-evaluation variance when DP is enabled;
- cosine-to-consensus checks should be downweighted under strong DP noise;
- median across validators still works because it aggregates reported scalar scores, even if those scores become noisier.

DP does not make TKNN-Shapley validator-executable. It protects model updates; it does not give validators the missing raw samples required by sample-level Shapley.

## Threat Model Boundaries

The default scoring path catches crude poisoning: malformed models, random updates, scaling attacks, sign flips, and updates that reduce clean validation performance.

It does not reliably catch clean-accuracy-preserving backdoors. If backdoors are in scope for MVP, DIN needs an additional model-inspection or adversarial-trigger evaluation layer, such as activation clustering, spectral signatures, pruning-based inspection, or task-specific backdoor probes. Those can still be validator-side defenses, but they are beyond the first scoring module.

## Contract Direction

The contract should stop assuming that scoring means "one scalar plus one test dataset."

Recommended changes:

- supplement or replace `testDataCID` with `evaluationSpecCID`;
- add a `V2` audit-result submission method that accepts normalized summary fields plus `metricBundleCID`;
- store final normalized utility and agreement summaries on `LMSubmission` or related storage;
- finalize approval from policy-compatible thresholds rather than only `avg(score) >= passScore`.

The contract should not parse metric families like F1, NDCG, or RMSE directly. Those stay off-chain.

## Trust Model

This design is still honest-but-auditable, not fully trustless.

That is acceptable for DevNet because:

- auditors already execute off-chain evaluation;
- metric bundles and evaluation specs can be published by CID;
- normalized summaries make the contract small;
- scenario-aware semantics are still far better than a misleading universal accuracy score.

The immediate goal is accuracy of system design, not pretending that every ML evaluation artifact is fully verifiable on chain.
