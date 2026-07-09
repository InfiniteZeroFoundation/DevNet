# Auditor Evaluation Mechanism

## Summary

Auditor rewards and slashing cannot depend only on whether an auditor submitted a score. They must depend on whether the auditor submitted an honest, reproducible, policy-compatible score.

The current DevNet path records:

- one score;
- one eligibility vote;
- one submission flag per auditor/model;
- final approval by quorum and score threshold.

That is enough for a demo, but it is not enough to safely reward or slash auditors. Once client rewards, validator rewards, and accepted aggregation depend on scoring, DIN needs an explicit mechanism for evaluating the auditors themselves.

## Problem Restated

Auditors are economically important because they decide which local model updates enter aggregation. A dishonest or careless auditor can:

- approve poisoned or malformed updates;
- reject useful updates;
- submit random scores to collect rewards;
- coordinate with clients to inflate scores;
- disagree maliciously with honest auditors to trigger disputes;
- avoid doing the actual evaluation while still submitting plausible-looking values.

If auditor rewards pay only for submission, low-quality scoring is rewarded. If slashing is too aggressive, honest auditors can be punished for nondeterminism, small validation shard variance, DP noise, or legitimate metric differences.

The mechanism therefore needs to separate:

1. completion rewards;
2. quality rewards;
3. warning or reputation penalties;
4. slashable misconduct.

## Relationship To Scoring

This issue depends on the scoring mechanism work.

Auditor evaluation should consume:

- `eligible` vote;
- normalized utility score;
- anomaly score;
- baseline delta;
- `metricBundleCID`;
- evaluation spec or test shard CID;
- validator consensus result;
- final accepted/rejected decision.

The auditor should be evaluated against the robust aggregate of other auditors, not against a single model-owner opinion.

## Recommended Auditor Quality Signals

### 1. Completion Signal

Did the auditor perform the assigned work?

Positive if:

- submitted every assigned score before the deadline;
- attached or locally produced a metric bundle;
- used the correct evaluation spec or test shard;
- did not submit duplicate or malformed results.

Failure cases:

- no submission;
- late submission;
- wrong batch/model index;
- missing metric bundle in V2;
- invalid score range.

This signal is safe for rewards and light penalties.

### 2. Consensus Agreement Signal

How close was the auditor to the robust validator aggregate?

For each audited local model:

```text
score_deviation_i = abs(score_auditor_i - median_score_i)
vote_match_i = auditor_accept_i == final_accept_i
```

Then per auditor:

```text
agreement_score = weighted average over assigned models
```

Use median, not mean, so one malicious auditor cannot define the target.

This signal is useful for rewards and reputation. It should not trigger slashing by itself unless the deviation is extreme and repeated.

### 3. Reproducibility Signal

Can another validator reproduce the submitted score from the same artifacts?

Inputs:

- local model CID;
- evaluation spec or test shard CID;
- scoring policy;
- metric bundle;
- service version or service CID.

A verifier reruns the scoring service and checks whether the recomputed result falls inside an allowed tolerance.

This signal is stronger than consensus because it checks the actual work, not only agreement with peers.

### 4. Anomaly Pattern Signal

Does the auditor show suspicious long-term behavior?

Examples:

- always approves every model;
- always rejects every model;
- consistently scores one client higher than the validator median;
- repeatedly omits metric bundles;
- repeatedly deviates near reward-critical thresholds;
- disagrees only when a specific client is involved.

This belongs mostly in reputation and monitoring at first.

## Reward Policy

Auditor rewards should be split into two parts.

### Base Completion Reward

Paid for finishing assigned work.

Requirements:

- submitted on time;
- submitted valid score fields;
- produced required evidence;
- did not fail basic reproducibility checks.

### Quality Multiplier

Adjusts the base reward by agreement and reproducibility.

Example:

```text
auditor_reward = base_reward * completion_factor * quality_factor
```

Where:

```text
completion_factor = completed_assignments / total_assignments
quality_factor = clamp(1 - median_deviation / max_allowed_deviation, min_quality, 1)
```

For DevNet, keep the quality factor simple and conservative. Reward suppression is safer than slashing while score variance is still being characterized.

## Slashing Policy

Slashing should be reserved for objective or strongly evidenced failures.

### Slashable In MVP Or Early Testnet

- accepted assignment and submitted nothing;
- submitted invalid data that cannot be decoded;
- submitted a score for an assignment the auditor did not have;
- submitted a metric bundle whose artifacts do not match the claimed model, batch, or evaluation spec;
- failed reproducibility by a large margin after dispute re-execution.

### Not Slashable By Default

- mild disagreement with the median;
- scoring variance caused by small validation shards;
- disagreement caused by DP noise;
- honest differences within configured tolerance;
- backdoor misses when the scoring policy only evaluates clean validation accuracy.

These should affect rewards or reputation first, not stake.

## Dispute Flow

Recommended flow:

1. auditor submits result and metric bundle;
2. contract or indexer computes robust aggregate after quorum;
3. any party can flag an outlier result within a dispute window;
4. a verifier reruns the scoring function from published artifacts;
5. if reproduced score is within tolerance, no penalty;
6. if not reproducible, suppress reward;
7. if deviation is extreme or repeated, slash according to policy.

For DevNet, this can be off-chain first with published reports. On-chain slashing should only be added after the re-execution path is stable.

## Recommended Data Model

Auditor evaluation should eventually produce an `auditorEvaluationReportCID` per GI.

Suggested report fields:

```json
{
  "spec_version": 1,
  "gi": 1,
  "auditor": "0x...",
  "assigned_count": 12,
  "submitted_count": 12,
  "valid_bundle_count": 12,
  "median_score_deviation_bps": 140,
  "accept_vote_match_rate_bps": 9200,
  "reproducibility_failures": 0,
  "reward_quality_factor_bps": 9600,
  "slash_recommended": false,
  "tags": ["completed", "within_consensus"]
}
```

## On-Chain And Off-Chain Split

### Off-chain

- metric bundle validation;
- score recomputation;
- auditor deviation reports;
- reputation history;
- dispute evidence.

### On-chain

- submitted result hash or CID;
- completion flag;
- rewardable flag;
- slashable fault result after dispute;
- compact final reward weight.

The contract should not recompute ML metrics.

## Recommended DevNet Default

For the first implementation:

- pay or mark auditors rewardable for timely valid submission;
- compute median deviation off-chain;
- publish metric bundles from auditor services;
- suppress rewards for missing or malformed outputs;
- do not slash for score disagreement yet;
- slash only for non-submission after accepted assignment or clearly invalid submissions.

## Definition Of Done

This mechanism is ready for first implementation when DIN can:

- collect per-auditor metric bundles;
- compute per-auditor deviation from median score;
- classify auditor outcomes as completed, late, missing, malformed, outlier, or non-reproducible;
- feed a reward quality factor into validator reward logic;
- define a conservative slashable-fault list;
- publish an auditor evaluation report per GI.

## Out Of Scope For Initial Delivery

- fully automated on-chain dispute resolution;
- ZK proofs of auditor execution;
- TEE-based scoring attestation;
- slashing for subtle ML-quality disagreement;
- backdoor-specific auditor evaluation.

