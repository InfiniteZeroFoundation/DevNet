from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

DEFAULT_SCORING_POLICY: dict[str, Any] = {
    "spec_version": 1,
    "scenario": "labeled_holdout_classification",
    "admission_mode": "holdout_delta",
    "contribution_mode": "none",
    "fallback_mode": "screening_only",
    "eligibility_checks": {
        "require_loadable_model": True,
        "require_architecture_match": True,
        "reject_nan_tensors": True,
        "max_update_norm": 100.0,
        "max_abs_weight": 100.0,
        "min_eval_examples": 1,
        # Cosine-to-consensus (run_cosine_to_consensus_check): shadow-mode by
        # default. min_cosine_to_consensus=-1.0 means "never flag" (cosine
        # similarity is always >= -1), matching the S3-style pattern of
        # shipping new anomaly signals settable-but-non-gating until
        # empirically validated (task_210726_6 §1d).
        "min_consensus_peers": 3,
        "min_cosine_to_consensus": -1.0,
    },
    "metrics": {
        "primary": ["accuracy", "loss", "macro_f1", "baseline_delta"],
        "thresholds": {
            "min_accuracy": 50.0,
            "min_baseline_delta_bps": 0,
            "max_anomaly_score_bps": 5000,
        },
    },
    "normalization": {
        "contract_score_scale": "percent_0_100",
        "utility_scale": "basis_points",
        "max_utility": 10000,
    },
}


@dataclass
class EligibilityResult:
    eligible: bool
    anomaly_score_bps: int
    tags: list[str]
    update_norm: float | None
    max_abs_weight: float | None


@dataclass
class ClassificationMetrics:
    accuracy: float
    loss: float
    macro_f1: float
    total_examples: int


@dataclass
class AuditScoringResult:
    eligible: bool
    accepted: bool
    contract_score: int
    utility_score_bps: int
    baseline_delta_bps: int
    anomaly_score_bps: int
    metric_bundle_cid: str | None
    metric_bundle_path: str
    tags: list[str]
    raw_metrics: dict[str, Any]


def load_scoring_policy(model_base_dir: str | Path) -> dict[str, Any]:
    """Load the manifest scoring policy while preserving a safe default.

    Custom service files are executed as standalone Python modules by `dincli`.
    They currently receive `model_base_dir` but not a full runtime context, so
    the reference auditor service resolves `manifest.json` from the model
    directory here. This keeps the first scoring implementation compatible with
    the existing CLI and contract while still making policy machine-readable.
    """

    manifest_path = Path(model_base_dir) / "manifest.json"
    if not manifest_path.exists():
        return DEFAULT_SCORING_POLICY

    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    policy = manifest.get("scoring_policy")
    if not isinstance(policy, dict):
        return DEFAULT_SCORING_POLICY

    # Merge only one level deep. The policy is intentionally simple for this
    # first pass, and explicit defaults make older manifests keep working.
    merged = dict(DEFAULT_SCORING_POLICY)
    for key, value in policy.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _iter_floating_tensors(state_dict: dict[str, torch.Tensor]):
    """Yield only floating tensors because update norms are numeric ML signals.

    PyTorch state dictionaries can also include integer buffers, counters, or
    other non-floating tensors. Those should be checked for shape compatibility
    but not included in an L2 update norm or finite-weight anomaly score.
    """

    for name, tensor in state_dict.items():
        if torch.is_tensor(tensor) and torch.is_floating_point(tensor):
            yield name, tensor


def run_eligibility_anomaly_gate(
    *,
    base_state: dict[str, torch.Tensor],
    candidate_state: dict[str, torch.Tensor],
    policy: dict[str, Any],
) -> EligibilityResult:
    """Run the first auditor-side eligibility algorithm.

    The gate is deliberately conservative and contract-compatible:

    1. confirm the local model is structurally the same model as the genesis or
       current global reference model;
    2. reject NaN/Inf tensors because they can poison aggregation immediately;
    3. compute a global update norm so extreme scaling attacks are filtered;
    4. compute a bounded anomaly score that can later be submitted through a V2
       audit-result method.

    The current contract can only receive `(score, eligible)`, so this function
    returns rich details for the metric bundle and a single boolean for today's
    on-chain path.
    """

    checks = policy.get("eligibility_checks", {})
    require_architecture_match = bool(checks.get("require_architecture_match", True))
    reject_nan_tensors = bool(checks.get("reject_nan_tensors", True))
    max_update_norm = checks.get("max_update_norm")
    max_abs_weight = checks.get("max_abs_weight")

    eligible = True
    tags: list[str] = []

    if not isinstance(candidate_state, dict):
        return EligibilityResult(
            eligible=False,
            anomaly_score_bps=10000,
            tags=["candidate_state_not_dict"],
            update_norm=None,
            max_abs_weight=None,
        )

    base_keys = set(base_state.keys())
    candidate_keys = set(candidate_state.keys())

    if require_architecture_match and base_keys != candidate_keys:
        eligible = False
        tags.append("state_dict_keys_mismatch")

    squared_update_norm = 0.0
    observed_max_abs = 0.0

    # Iterate over the base model keys so missing or extra keys are reported in
    # a deterministic order. This makes metric bundles easier to compare across
    # validators during dispute analysis.
    for name, base_tensor in base_state.items():
        candidate_tensor = candidate_state.get(name)

        if candidate_tensor is None:
            eligible = False
            tags.append(f"missing_tensor:{name}")
            continue

        if not torch.is_tensor(candidate_tensor):
            eligible = False
            tags.append(f"non_tensor:{name}")
            continue

        if require_architecture_match and tuple(base_tensor.shape) != tuple(candidate_tensor.shape):
            eligible = False
            tags.append(f"shape_mismatch:{name}")
            continue

        if torch.is_floating_point(candidate_tensor):
            if reject_nan_tensors and not torch.isfinite(candidate_tensor).all().item():
                eligible = False
                tags.append(f"non_finite_tensor:{name}")
                continue

            observed_max_abs = max(observed_max_abs, float(candidate_tensor.detach().abs().max().item()))

            # Cast to float32 for stable arithmetic across CPU/GPU tensor dtypes.
            # The update is measured relative to the reference model because a
            # large-but-valid local model can still be harmful if its delta is
            # far outside the expected FL round behavior.
            delta = candidate_tensor.detach().float() - base_tensor.detach().float()
            squared_update_norm += float(torch.sum(delta * delta).item())

    update_norm = math.sqrt(squared_update_norm)

    if max_update_norm is not None and update_norm > float(max_update_norm):
        eligible = False
        tags.append("update_norm_exceeds_cap")

    if max_abs_weight is not None and observed_max_abs > float(max_abs_weight):
        eligible = False
        tags.append("weight_abs_exceeds_cap")

    # Convert the continuous anomaly signal into basis points so the same value
    # can later fit a compact V2 audit result. 0 means no anomaly pressure, and
    # 10000 means at or beyond the configured cap.
    anomaly_ratio = 0.0
    if max_update_norm:
        anomaly_ratio = max(anomaly_ratio, update_norm / float(max_update_norm))
    if max_abs_weight:
        anomaly_ratio = max(anomaly_ratio, observed_max_abs / float(max_abs_weight))
    anomaly_score_bps = int(round(min(anomaly_ratio, 1.0) * 10000))

    if eligible and not tags:
        tags.append("eligible")

    return EligibilityResult(
        eligible=eligible,
        anomaly_score_bps=anomaly_score_bps,
        tags=tags,
        update_norm=update_norm,
        max_abs_weight=observed_max_abs,
    )


@dataclass
class ConsensusDeviationResult:
    computed: bool
    cosine_similarity: float | None
    outlier: bool
    reason: str


def _flatten_update_vector(
    base_state: dict[str, torch.Tensor], candidate_state: dict[str, torch.Tensor]
) -> torch.Tensor:
    """Flatten a candidate's delta from the base model into one 1-D vector.

    Shared by cosine-to-consensus and marginal-gain scoring so both compare
    updates in the same coordinate space. Only floating tensors are included
    for the same reason `run_eligibility_anomaly_gate`'s norm computation
    excludes integer buffers/counters.
    """

    pieces = []
    for name, base_tensor in _iter_floating_tensors(base_state):
        candidate_tensor = candidate_state.get(name)
        if candidate_tensor is None or not torch.is_tensor(candidate_tensor):
            continue
        delta = candidate_tensor.detach().float() - base_tensor.detach().float()
        pieces.append(delta.reshape(-1))
    if not pieces:
        return torch.zeros(1)
    return torch.cat(pieces)


def run_cosine_to_consensus_check(
    *,
    base_state: dict[str, torch.Tensor],
    candidate_state: dict[str, torch.Tensor],
    batch_candidate_states: list[dict[str, torch.Tensor]],
    policy: dict[str, Any],
) -> ConsensusDeviationResult:
    """Second eligibility signal: is this update's direction an outlier vs. the batch?

    `scoring-mechanism.md` §1 describes this as "update direction is not an
    obvious outlier against the round's consensus direction **when enough
    candidate updates exist**" — the conditional matters. With too few peers,
    a "consensus direction" is not a meaningful signal (e.g. one other
    submission just IS the direction, not a consensus), so this returns
    `computed=False` rather than fabricating a decision from noise.

    Consensus direction is the mean of all *other* candidates' update vectors
    in the batch (self excluded, so a lone attacker can't drag the consensus
    toward themselves). Deviation is `1 - cosine_similarity`; the caller
    decides eligibility impact via `policy["eligibility_checks"]
    ["min_cosine_to_consensus"]` — kept as a separate, explicitly-optional
    signal (not folded into `run_eligibility_anomaly_gate`'s `eligible` output)
    because, like the S3 deviation threshold in task_210726_6 §1d, this needs
    empirical validation before it gates anything. Ships informational-only
    until a threshold is validated; wiring it into `eligible` is a follow-up.
    """

    checks = policy.get("eligibility_checks", {})
    min_peers = int(checks.get("min_consensus_peers", 3))

    peers = [s for s in batch_candidate_states if s is not candidate_state]
    if len(peers) < min_peers:
        return ConsensusDeviationResult(
            computed=False,
            cosine_similarity=None,
            outlier=False,
            reason=f"insufficient_batch_peers:{len(peers)}<{min_peers}",
        )

    candidate_vec = _flatten_update_vector(base_state, candidate_state)

    consensus_vec = torch.zeros_like(candidate_vec)
    counted = 0
    for peer_state in peers:
        peer_vec = _flatten_update_vector(base_state, peer_state)
        if peer_vec.shape != candidate_vec.shape:
            # A peer that fails architecture match is not part of a meaningful
            # consensus direction; skip rather than error the whole check.
            continue
        consensus_vec += peer_vec
        counted += 1

    if counted < min_peers:
        return ConsensusDeviationResult(
            computed=False,
            cosine_similarity=None,
            outlier=False,
            reason=f"insufficient_shape_matched_peers:{counted}<{min_peers}",
        )

    consensus_vec /= counted

    candidate_norm = float(torch.linalg.vector_norm(candidate_vec).item())
    consensus_norm = float(torch.linalg.vector_norm(consensus_vec).item())
    if candidate_norm == 0.0 or consensus_norm == 0.0:
        # A zero update (or zero consensus, degenerate batch) has no direction
        # to compare; treat as non-computable rather than a forced 0 or 1.
        return ConsensusDeviationResult(
            computed=False,
            cosine_similarity=None,
            outlier=False,
            reason="zero_norm_vector",
        )

    cosine_similarity = float(torch.dot(candidate_vec, consensus_vec).item() / (candidate_norm * consensus_norm))
    min_cosine = float(checks.get("min_cosine_to_consensus", -1.0))
    outlier = cosine_similarity < min_cosine

    return ConsensusDeviationResult(
        computed=True,
        cosine_similarity=cosine_similarity,
        outlier=outlier,
        reason="ok",
    )


def evaluate_classification_model(
    model: torch.nn.Module,
    dataset,
    *,
    batch_size: int = 32,
    device: torch.device | None = None,
) -> ClassificationMetrics:
    """Evaluate a classifier without sklearn or task-specific dependencies."""

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
    loss_fn = nn.CrossEntropyLoss(reduction="sum")

    total = 0
    correct = 0
    total_loss = 0.0

    # Keep a tiny confusion table as plain Python integers. This gives us
    # macro-F1 without importing sklearn inside dynamic service files.
    true_positive: dict[int, int] = {}
    false_positive: dict[int, int] = {}
    false_negative: dict[int, int] = {}

    model.to(device)
    model.eval()

    with torch.no_grad():
        for data, target in loader:
            data = data.to(device)
            target = target.to(device)

            output = model(data)
            predicted = torch.argmax(output, dim=1)

            total += int(target.numel())
            correct += int((predicted == target).sum().item())
            total_loss += float(loss_fn(output, target).item())

            for actual, guess in zip(target.detach().cpu().tolist(), predicted.detach().cpu().tolist()):
                actual = int(actual)
                guess = int(guess)
                if actual == guess:
                    true_positive[actual] = true_positive.get(actual, 0) + 1
                else:
                    false_positive[guess] = false_positive.get(guess, 0) + 1
                    false_negative[actual] = false_negative.get(actual, 0) + 1

    if total <= 0:
        raise ValueError("Cannot score an empty evaluation dataset.")

    classes = set(true_positive) | set(false_positive) | set(false_negative)
    f1_values = []
    for label in classes:
        tp = true_positive.get(label, 0)
        fp = false_positive.get(label, 0)
        fn = false_negative.get(label, 0)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        f1_values.append(f1)

    return ClassificationMetrics(
        accuracy=100.0 * correct / total,
        loss=total_loss / total,
        macro_f1=100.0 * (sum(f1_values) / len(f1_values) if f1_values else 0.0),
        total_examples=total,
    )


def normalize_holdout_delta_score(
    *,
    candidate_metrics: ClassificationMetrics,
    baseline_metrics: ClassificationMetrics,
    eligibility: EligibilityResult,
    policy: dict[str, Any],
) -> AuditScoringResult:
    """Map raw metrics into today's contract score and tomorrow's V2 fields."""

    thresholds = policy.get("metrics", {}).get("thresholds", {})
    min_accuracy = float(thresholds.get("min_accuracy", 0.0))
    min_baseline_delta_bps = int(thresholds.get("min_baseline_delta_bps", -10000))
    max_anomaly_score_bps = int(thresholds.get("max_anomaly_score_bps", 10000))

    baseline_delta = candidate_metrics.accuracy - baseline_metrics.accuracy
    baseline_delta_bps = int(round(baseline_delta * 100))
    utility_score_bps = int(round(max(0.0, min(candidate_metrics.accuracy, 100.0)) * 100))
    contract_score = int(round(max(0.0, min(candidate_metrics.accuracy, 100.0))))

    accepted = (
        eligibility.eligible
        and candidate_metrics.accuracy >= min_accuracy
        and baseline_delta_bps >= min_baseline_delta_bps
        and eligibility.anomaly_score_bps <= max_anomaly_score_bps
    )

    tags = list(eligibility.tags)
    if candidate_metrics.accuracy < min_accuracy:
        tags.append("accuracy_below_policy_threshold")
    if baseline_delta_bps < min_baseline_delta_bps:
        tags.append("baseline_delta_below_policy_threshold")
    if eligibility.anomaly_score_bps > max_anomaly_score_bps:
        tags.append("anomaly_score_above_policy_threshold")

    return AuditScoringResult(
        eligible=eligibility.eligible,
        accepted=accepted,
        contract_score=contract_score,
        utility_score_bps=utility_score_bps,
        baseline_delta_bps=baseline_delta_bps,
        anomaly_score_bps=eligibility.anomaly_score_bps,
        metric_bundle_cid=None,
        metric_bundle_path="",
        tags=tags,
        raw_metrics={
            "candidate": asdict(candidate_metrics),
            "baseline": asdict(baseline_metrics),
            "update_norm": eligibility.update_norm,
            "max_abs_weight": eligibility.max_abs_weight,
        },
    )


def _aggregate_subset(
    base_state: dict[str, torch.Tensor], candidate_states: list[dict[str, torch.Tensor]]
) -> dict[str, torch.Tensor]:
    """Uniform FedAvg of the base model plus zero or more candidate updates.

    Mirrors `aggregator.py`'s `_average_state_dicts`, but operates on in-memory
    state dicts (no file I/O) since `mc_marginal_gain_score` calls this once
    per coalition size per permutation and needs it fast. An empty
    `candidate_states` returns the base model unchanged — this is `v(∅)`, the
    characteristic function's baseline in the permutation game below.
    """

    if not candidate_states:
        return {k: v.clone() for k, v in base_state.items()}

    agg: dict[str, torch.Tensor] = {}
    for key, base_tensor in base_state.items():
        if torch.is_tensor(base_tensor) and torch.is_floating_point(base_tensor):
            acc = torch.zeros_like(base_tensor, dtype=torch.float32)
            for state in candidate_states:
                acc += state[key].detach().float()
            agg[key] = (acc / len(candidate_states)).to(base_tensor.dtype)
        else:
            agg[key] = base_tensor.clone()
    return agg


def mc_marginal_gain_score(
    *,
    base_state: dict[str, torch.Tensor],
    candidate_states: list[dict[str, torch.Tensor]],
    evaluate_fn: Callable[[dict[str, torch.Tensor]], float],
    n_perms: int = 1,
    seed: int | None = None,
) -> list[float]:
    """Permutation-averaged Monte Carlo Shapley via sequential fold-in.

    The third validator-side algorithm scoring-mechanism.md §6 specifies
    (`mc_marginal_gain_score`) and which task_210726_6 §1a found genuinely
    absent from this codebase. Implements the `truncated_MC` pattern from
    `LabeliaLabs/distributed-learning-contributivity`
    (`mplc/contributivity.py`) that `scoring-auditing-references.md` points
    at: for each of `n_perms` random orderings of the batch's candidates,
    fold them in one at a time (`M = M ⊕ u_i`, via `_aggregate_subset`),
    measure `evaluate_fn`'s marginal delta at each step, and average each
    candidate's marginal contribution across permutations.

    `n_perms=1` is the cheap detection baseline the scoring-mechanism issue
    describes ("increase only when reward attribution fairness matters") —
    at n_perms=1 this is plain sequential fold-in with no permutation
    averaging yet, which is enough to validate duplicate discounting cheaply.

    `evaluate_fn` is injected rather than hard-coded to `evaluate_classification_model`
    so this stays testable without a real model/dataset (see the scoring
    tests) and reusable for non-classification metric families later, per
    scoring-mechanism.md's task-type-specific metric guidance.

    Returns one contribution score per `candidate_states` entry, in the same
    order as the input list, NOT yet normalized into bps or clamped to
    non-negative — normalization is `normalize_holdout_delta_score`'s pattern
    to follow once this is wired into a real submission path, out of scope
    for this reference implementation.
    """

    n = len(candidate_states)
    if n == 0:
        return []

    rng = random.Random(seed)
    contributions = [0.0] * n
    base_value = evaluate_fn(_aggregate_subset(base_state, []))

    for _ in range(n_perms):
        order = list(range(n))
        rng.shuffle(order)

        included: list[dict[str, torch.Tensor]] = []
        prev_value = base_value
        for idx in order:
            included.append(candidate_states[idx])
            new_value = evaluate_fn(_aggregate_subset(base_state, included))
            contributions[idx] += new_value - prev_value
            prev_value = new_value

    return [c / n_perms for c in contributions]


def write_metric_bundle(
    *,
    result: AuditScoringResult,
    policy: dict[str, Any],
    output_dir: str | Path,
    gi: int,
    batch_id: int,
    model_index: int,
    auditor_address: str,
    test_data_cid: str | None,
    local_model_cid: str,
) -> AuditScoringResult:
    """Persist the detailed audit evidence bundle locally.

    The current contract has no place to store `metricBundleCID`. Uploading
    the bundle to IPFS (if desired) is dincli's responsibility on the host
    after this function returns, since no network access happens in here; the
    file still lands on disk and can be inspected by the auditor/operator.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    bundle_path = output_path / f"audit_metric_bundle_gi{gi}_batch{batch_id}_lm{model_index}.json"

    payload = {
        "spec_version": 1,
        "gi": gi,
        "batch_id": batch_id,
        "model_index": model_index,
        "auditor_address": auditor_address,
        "test_data_cid": test_data_cid,
        "local_model_cid": local_model_cid,
        "policy": policy,
        "result": {
            "eligible": result.eligible,
            "accepted": result.accepted,
            "contract_score": result.contract_score,
            "utility_score_bps": result.utility_score_bps,
            "baseline_delta_bps": result.baseline_delta_bps,
            "anomaly_score_bps": result.anomaly_score_bps,
            "tags": result.tags,
            "raw_metrics": result.raw_metrics,
        },
    }

    with bundle_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)

    # Uploading is dincli's job on the host (best-effort), not this function's;
    # leave metric_bundle_cid unset here.
    result.metric_bundle_path = str(bundle_path)
    return result
