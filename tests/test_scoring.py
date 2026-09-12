"""Coverage for cache_model_0/services/scoring.py per task_210726_6 §1b.

Scope, per the §1a spec-to-code mapping posted to issue #39 before this file
was written: `eligibility_anomaly_gate` and `holdout_delta_score` already
existed and are tested against their existing behavior. `mc_marginal_gain_score`
(fold-in + permutation averaging) and the cosine-to-consensus check did not
exist in the codebase at all; both are new, minimal reference implementations
added alongside this test file (see scoring.py) rather than a full production
contribution-scoring plane, per the task's explicit instruction not to
silently over-build inside this budget.

Tests operate on small synthetic state_dicts (not real MNIST models/datasets)
so the suite runs fast and exercises the actual decision logic in scoring.py
directly, rather than the full training/evaluation pipeline. Where a test
needs a "model evaluation" signal (marginal-gain scoring, holdout-delta
scoring), it either supplies a synthetic `evaluate_fn` callable or constructs
`ClassificationMetrics` directly with chosen values -- this is documented
per-test so it's clear which layer is under test.
"""

from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

try:
    import torch
except ImportError as exc:
    raise ImportError("torch is required for tests/test_scoring.py but is not installed in this environment") from exc


def load_scoring_module():
    scoring_path = Path(__file__).resolve().parents[1] / "cache_model_0" / "services" / "scoring.py"
    spec = spec_from_file_location("cache_model_0_scoring", scoring_path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    # scoring.py uses `from __future__ import annotations` + @dataclass;
    # dataclasses resolves string annotations via sys.modules[cls.__module__],
    # so the module must be registered there before its class bodies execute.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scoring = load_scoring_module()


def make_state(a: float, b: float) -> dict[str, torch.Tensor]:
    """A small two-tensor synthetic "model" state_dict, cheap to compute over."""
    return {
        "layer.weight": torch.full((4, 4), a, dtype=torch.float32),
        "layer.bias": torch.full((4,), b, dtype=torch.float32),
    }


BASE_STATE = make_state(0.0, 0.0)
DEFAULT_POLICY = scoring.DEFAULT_SCORING_POLICY


# ─────────────────────────────────────────────────────────────────────────
# Poison detection via run_eligibility_anomaly_gate (structural/norm-bound plane)
# ─────────────────────────────────────────────────────────────────────────


class TestEligibilityAnomalyGate:
    def test_clean_small_update_is_eligible(self):
        result = scoring.run_eligibility_anomaly_gate(
            base_state=BASE_STATE, candidate_state=make_state(0.01, 0.01), policy=DEFAULT_POLICY
        )
        assert result.eligible is True
        assert result.anomaly_score_bps < 100

    def test_garbage_update_nan_tensors_rejected(self):
        candidate = make_state(0.0, 0.0)
        candidate["layer.weight"][0, 0] = float("nan")
        result = scoring.run_eligibility_anomaly_gate(base_state=BASE_STATE, candidate_state=candidate, policy=DEFAULT_POLICY)
        assert result.eligible is False
        assert any("non_finite_tensor" in tag for tag in result.tags)

    def test_garbage_update_inf_tensors_rejected(self):
        candidate = make_state(0.0, 0.0)
        candidate["layer.bias"][0] = float("inf")
        result = scoring.run_eligibility_anomaly_gate(base_state=BASE_STATE, candidate_state=candidate, policy=DEFAULT_POLICY)
        assert result.eligible is False

    def test_architecture_mismatch_rejected(self):
        candidate = {"layer.weight": torch.zeros(4, 4)}  # missing layer.bias
        result = scoring.run_eligibility_anomaly_gate(base_state=BASE_STATE, candidate_state=candidate, policy=DEFAULT_POLICY)
        assert result.eligible is False
        assert any("missing_tensor" in tag for tag in result.tags)

    def test_shape_mismatch_rejected(self):
        candidate = make_state(0.0, 0.0)
        candidate["layer.weight"] = torch.zeros(8, 8)
        result = scoring.run_eligibility_anomaly_gate(base_state=BASE_STATE, candidate_state=candidate, policy=DEFAULT_POLICY)
        assert result.eligible is False
        assert any("shape_mismatch" in tag for tag in result.tags)

    @pytest.mark.parametrize("norm_cap", [1.0, 10.0, 100.0])
    def test_scaling_attack_rejected_at_multiple_norm_caps(self, norm_cap):
        """A scaling-attack update (huge uniform multiplier) should be rejected
        once its L2 norm exceeds the configured cap, at every cap tested --
        the eligibility gate's response should scale with the policy, not be
        hard-coded to one threshold."""
        policy = {**DEFAULT_POLICY, "eligibility_checks": {**DEFAULT_POLICY["eligibility_checks"], "max_update_norm": norm_cap}}
        # Delta L2 norm = sqrt(16*a^2 + 4*b^2); pick a well past any tested cap.
        candidate = make_state(a=norm_cap * 10, b=norm_cap * 10)
        result = scoring.run_eligibility_anomaly_gate(base_state=BASE_STATE, candidate_state=candidate, policy=policy)
        assert result.eligible is False
        assert "update_norm_exceeds_cap" in result.tags
        assert result.anomaly_score_bps == 10000  # clamped at the cap

    @pytest.mark.parametrize("norm_cap", [1.0, 10.0, 100.0])
    def test_update_within_norm_cap_accepted_at_multiple_caps(self, norm_cap):
        policy = {**DEFAULT_POLICY, "eligibility_checks": {**DEFAULT_POLICY["eligibility_checks"], "max_update_norm": norm_cap}}
        # Small delta relative to the cap.
        candidate = make_state(a=norm_cap * 1e-4, b=norm_cap * 1e-4)
        result = scoring.run_eligibility_anomaly_gate(base_state=BASE_STATE, candidate_state=candidate, policy=policy)
        assert result.eligible is True


# ─────────────────────────────────────────────────────────────────────────
# Poison detection via normalize_holdout_delta_score (utility plane) --
# label-flip / sign-flip attacks generally pass structural checks (finite,
# in-norm) but tank utility, so they must be caught here, not by the
# eligibility gate. Metrics are constructed directly rather than run through
# a real model+dataset, since this layer's job is the accept/reject decision
# logic, not re-testing evaluate_classification_model's arithmetic.
# ─────────────────────────────────────────────────────────────────────────


def eligible_result():
    return scoring.EligibilityResult(eligible=True, anomaly_score_bps=0, tags=["eligible"], update_norm=0.5, max_abs_weight=0.5)


class TestHoldoutDeltaScore:
    def test_genuinely_useful_update_is_accepted(self):
        baseline = scoring.ClassificationMetrics(accuracy=70.0, loss=0.9, macro_f1=68.0, total_examples=100)
        candidate = scoring.ClassificationMetrics(accuracy=85.0, loss=0.4, macro_f1=83.0, total_examples=100)
        result = scoring.normalize_holdout_delta_score(
            candidate_metrics=candidate, baseline_metrics=baseline, eligibility=eligible_result(), policy=DEFAULT_POLICY
        )
        assert result.accepted is True
        assert result.baseline_delta_bps > 0

    @pytest.mark.parametrize("candidate_accuracy", [10.0, 30.0, 49.0])
    def test_label_flip_style_degradation_rejected_at_multiple_epsilons(self, candidate_accuracy):
        """Label-flip / sign-flip poisoning tends to produce near-random or
        worse accuracy than the baseline -- test several degraded-accuracy
        scenarios (multiple epsilon values below the default 50.0 min_accuracy
        threshold) rather than just one, per the task's "multiple epsilon
        values" instruction."""
        baseline = scoring.ClassificationMetrics(accuracy=70.0, loss=0.9, macro_f1=68.0, total_examples=100)
        candidate = scoring.ClassificationMetrics(
            accuracy=candidate_accuracy, loss=3.0, macro_f1=candidate_accuracy * 0.9, total_examples=100
        )
        result = scoring.normalize_holdout_delta_score(
            candidate_metrics=candidate, baseline_metrics=baseline, eligibility=eligible_result(), policy=DEFAULT_POLICY
        )
        assert result.accepted is False
        assert "accuracy_below_policy_threshold" in result.tags

    @pytest.mark.parametrize("min_accuracy_threshold", [50.0, 60.0, 75.0])
    def test_threshold_is_policy_driven_not_hardcoded(self, min_accuracy_threshold):
        """Same candidate result, different policy threshold -- the accept
        decision must track the policy, confirming min_accuracy isn't
        hard-coded anywhere along this path."""
        policy = {**DEFAULT_POLICY, "metrics": {**DEFAULT_POLICY["metrics"], "thresholds": {**DEFAULT_POLICY["metrics"]["thresholds"], "min_accuracy": min_accuracy_threshold}}}
        baseline = scoring.ClassificationMetrics(accuracy=55.0, loss=0.9, macro_f1=53.0, total_examples=100)
        candidate = scoring.ClassificationMetrics(accuracy=65.0, loss=0.5, macro_f1=63.0, total_examples=100)
        result = scoring.normalize_holdout_delta_score(
            candidate_metrics=candidate, baseline_metrics=baseline, eligibility=eligible_result(), policy=policy
        )
        assert result.accepted == (65.0 >= min_accuracy_threshold)

    def test_ineligible_update_never_accepted_regardless_of_accuracy(self):
        """Eligibility is a hard gate -- a structurally-failed update can't buy
        its way to acceptance with a good accuracy number."""
        baseline = scoring.ClassificationMetrics(accuracy=70.0, loss=0.9, macro_f1=68.0, total_examples=100)
        candidate = scoring.ClassificationMetrics(accuracy=99.0, loss=0.01, macro_f1=99.0, total_examples=100)
        failed_eligibility = scoring.EligibilityResult(
            eligible=False, anomaly_score_bps=10000, tags=["update_norm_exceeds_cap"], update_norm=999.0, max_abs_weight=999.0
        )
        result = scoring.normalize_holdout_delta_score(
            candidate_metrics=candidate, baseline_metrics=baseline, eligibility=failed_eligibility, policy=DEFAULT_POLICY
        )
        assert result.accepted is False


# ─────────────────────────────────────────────────────────────────────────
# Cosine-to-consensus (new; did not exist per §1a mapping)
# ─────────────────────────────────────────────────────────────────────────


class TestCosineToConsensus:
    def test_default_policy_never_flags_shadow_mode(self):
        """min_cosine_to_consensus defaults to -1.0 -- always non-gating, per
        the S3-style shadow-mode pattern this task establishes elsewhere."""
        candidate = make_state(a=5.0, b=5.0)  # a wild outlier direction
        peers = [make_state(a=0.01, b=0.01) for _ in range(5)]
        batch = [candidate, *peers]
        result = scoring.run_cosine_to_consensus_check(
            base_state=BASE_STATE, candidate_state=candidate, batch_candidate_states=batch, policy=DEFAULT_POLICY
        )
        assert result.computed is True
        assert result.outlier is False  # shadow mode: computed, but never gates by default

    def test_insufficient_peers_not_computed(self):
        candidate = make_state(a=0.1, b=0.1)
        batch = [candidate, make_state(a=0.1, b=0.1)]  # only 1 peer, default min is 3
        result = scoring.run_cosine_to_consensus_check(
            base_state=BASE_STATE, candidate_state=candidate, batch_candidate_states=batch, policy=DEFAULT_POLICY
        )
        assert result.computed is False
        assert "insufficient_batch_peers" in result.reason

    def test_aligned_update_high_cosine_similarity(self):
        candidate = make_state(a=1.0, b=1.0)
        peers = [make_state(a=1.0 + noise, b=1.0 + noise) for noise in (0.01, -0.01, 0.02, -0.02)]
        result = scoring.run_cosine_to_consensus_check(
            base_state=BASE_STATE, candidate_state=candidate, batch_candidate_states=[candidate, *peers], policy=DEFAULT_POLICY
        )
        assert result.computed is True
        assert result.cosine_similarity == pytest.approx(1.0, abs=0.05)

    @pytest.mark.parametrize("min_cosine", [0.9, 0.5, 0.0])
    def test_outlier_direction_flagged_once_threshold_tightened(self, min_cosine):
        """Same clearly-outlier candidate, three different (non-shadow-mode)
        thresholds -- should be flagged at every one tested, since the
        candidate points in the opposite direction from consensus (cosine
        near -1), well below all three tested epsilons."""
        policy = {**DEFAULT_POLICY, "eligibility_checks": {**DEFAULT_POLICY["eligibility_checks"], "min_cosine_to_consensus": min_cosine}}
        candidate = make_state(a=-1.0, b=-1.0)  # opposite direction from peers
        peers = [make_state(a=1.0, b=1.0) for _ in range(4)]
        result = scoring.run_cosine_to_consensus_check(
            base_state=BASE_STATE, candidate_state=candidate, batch_candidate_states=[candidate, *peers], policy=policy
        )
        assert result.computed is True
        assert result.cosine_similarity == pytest.approx(-1.0, abs=0.01)
        assert result.outlier is True

    def test_zero_update_not_computed(self):
        """A candidate identical to the base model has no direction to compare
        -- must not silently report a fabricated similarity."""
        candidate = make_state(0.0, 0.0)  # == BASE_STATE, zero delta
        peers = [make_state(a=1.0, b=1.0) for _ in range(4)]
        result = scoring.run_cosine_to_consensus_check(
            base_state=BASE_STATE, candidate_state=candidate, batch_candidate_states=[candidate, *peers], policy=DEFAULT_POLICY
        )
        assert result.computed is False
        assert result.reason == "zero_norm_vector"


# ─────────────────────────────────────────────────────────────────────────
# mc_marginal_gain_score -- fold-in + permutation averaging (new; did not
# exist per §1a mapping). evaluate_fn is a synthetic utility function so
# these tests run in milliseconds and isolate the fold-in/averaging logic
# itself from real model training.
# ─────────────────────────────────────────────────────────────────────────


def sum_of_weights_metric(state: dict[str, torch.Tensor]) -> float:
    """A synthetic 'utility' that increases monotonically as more of a given
    update is folded in -- stands in for a real accuracy/loss metric so the
    fold-in arithmetic can be tested independently of ML training."""
    return float(state["layer.weight"].sum().item())


class TestMcMarginalGainScore:
    def test_empty_batch_returns_empty(self):
        assert scoring.mc_marginal_gain_score(base_state=BASE_STATE, candidate_states=[], evaluate_fn=sum_of_weights_metric, n_perms=1) == []

    def test_single_candidate_gets_full_marginal_gain(self):
        candidate = make_state(a=2.0, b=0.0)
        [contribution] = scoring.mc_marginal_gain_score(
            base_state=BASE_STATE, candidate_states=[candidate], evaluate_fn=sum_of_weights_metric, n_perms=1
        )
        expected = sum_of_weights_metric(candidate) - sum_of_weights_metric(BASE_STATE)
        assert contribution == pytest.approx(expected)

    def test_duplicate_scores_near_zero_after_first_fold_in_at_n_perms_1(self):
        """The 'cheap detection baseline' property from scoring-mechanism.md
        §6: with n_perms=1, whichever identical copy is folded in FIRST
        captures the real gain; the copy folded in SECOND contributes ~0,
        since aggregating a duplicate of what's already present barely moves
        the running average. By symmetry (both candidates identical) this
        holds regardless of which specific index goes first -- no fixed seed
        needed."""
        original = make_state(a=4.0, b=0.0)
        duplicate = make_state(a=4.0, b=0.0)  # exact copy
        contributions = scoring.mc_marginal_gain_score(
            base_state=BASE_STATE, candidate_states=[original, duplicate], evaluate_fn=sum_of_weights_metric, n_perms=1
        )
        low, high = sorted(contributions)
        assert low == pytest.approx(0.0, abs=1e-6)
        assert high > 0.5  # the "first" copy captured (approximately) the full gain

    def test_permutation_averaging_splits_credit_fairly_for_duplicates(self):
        """Contrast with the n_perms=1 case above: averaging over many random
        orderings should converge toward each identical duplicate getting
        roughly HALF the total gain (the Shapley-fair outcome), not the
        all-or-nothing split n_perms=1 produces. This is exactly the
        'increase n_perms when reward attribution fairness matters' tradeoff
        the scoring-mechanism issue describes."""
        original = make_state(a=4.0, b=0.0)
        duplicate = make_state(a=4.0, b=0.0)
        contributions = scoring.mc_marginal_gain_score(
            base_state=BASE_STATE, candidate_states=[original, duplicate], evaluate_fn=sum_of_weights_metric, n_perms=200, seed=42
        )
        total_gain = sum_of_weights_metric(duplicate) - sum_of_weights_metric(BASE_STATE)
        for contribution in contributions:
            assert contribution == pytest.approx(total_gain / 2, rel=0.15)

    def test_novel_update_scores_higher_than_duplicate_of_included_update(self):
        """A genuinely distinct, higher-value update should out-score a
        duplicate of an update that's already been folded in -- duplicate
        discounting shouldn't just suppress duplicates uniformly, it should
        still reward real novel contribution."""
        useful = make_state(a=4.0, b=0.0)
        duplicate_of_useful = make_state(a=4.0, b=0.0)
        genuinely_novel = make_state(a=8.0, b=0.0)  # distinct AND more valuable
        contributions = scoring.mc_marginal_gain_score(
            base_state=BASE_STATE,
            candidate_states=[useful, duplicate_of_useful, genuinely_novel],
            evaluate_fn=sum_of_weights_metric,
            n_perms=100,
            seed=7,
        )
        novel_contribution = contributions[2]
        duplicate_contribution = contributions[1]
        assert novel_contribution > duplicate_contribution

    @pytest.mark.parametrize("n_perms", [1, 5, 50])
    def test_efficiency_property_contributions_sum_to_total_value(self, n_perms):
        """Cooperative-game-theory efficiency axiom: sum of all marginal
        contributions must equal v(full set) - v(empty set) exactly, for any
        n_perms, since each individual permutation's contributions telescope
        to that same total and averaging preserves the sum. A strong
        correctness invariant for the fold-in/averaging implementation
        itself, independent of what evaluate_fn measures."""
        states = [make_state(a=1.0, b=0.0), make_state(a=2.0, b=1.0), make_state(a=-1.0, b=3.0)]
        contributions = scoring.mc_marginal_gain_score(
            base_state=BASE_STATE, candidate_states=states, evaluate_fn=sum_of_weights_metric, n_perms=n_perms, seed=1
        )
        total_value = sum_of_weights_metric(scoring._aggregate_subset(BASE_STATE, states)) - sum_of_weights_metric(BASE_STATE)
        assert sum(contributions) == pytest.approx(total_value, abs=1e-4)

    def test_poison_update_scores_low_or_negative_marginal_contribution(self):
        """Poison-detection framing for the contribution plane: an update that
        actively drags the aggregate's utility down (adversarial direction)
        should score a non-positive marginal contribution, distinguishing it
        from genuinely useful updates even when it might have passed the
        structural eligibility gate."""
        helpful = make_state(a=3.0, b=0.0)
        adversarial = make_state(a=-10.0, b=0.0)  # actively harmful direction
        contributions = scoring.mc_marginal_gain_score(
            base_state=BASE_STATE, candidate_states=[helpful, adversarial], evaluate_fn=sum_of_weights_metric, n_perms=50, seed=3
        )
        helpful_contribution, adversarial_contribution = contributions
        assert adversarial_contribution < 0
        assert helpful_contribution > adversarial_contribution

    def test_deterministic_given_seed(self):
        states = [make_state(a=1.0, b=0.0), make_state(a=2.0, b=1.0)]
        run_a = scoring.mc_marginal_gain_score(base_state=BASE_STATE, candidate_states=states, evaluate_fn=sum_of_weights_metric, n_perms=10, seed=99)
        run_b = scoring.mc_marginal_gain_score(base_state=BASE_STATE, candidate_states=states, evaluate_fn=sum_of_weights_metric, n_perms=10, seed=99)
        assert run_a == run_b
