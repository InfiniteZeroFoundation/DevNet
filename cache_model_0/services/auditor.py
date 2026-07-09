import os
import sys
from pathlib import Path

import torch
from rich import console

# Dynamic service loading means this file may be imported from a task cache
# directory rather than as part of a normal Python package. Adding the service
# directory to `sys.path` keeps sibling-module imports (`model`, `scoring`)
# working for the reference task while still allowing model owners to ship
# custom services.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from model import ModelArchitecture  # noqa: E402,F401
from scoring import (  # noqa: E402
    evaluate_classification_model,
    load_scoring_policy,
    normalize_holdout_delta_score,
    run_eligibility_anomaly_gate,
    write_metric_bundle,
)


console = console.Console()


def _load_artifacts(test_data_path, genesis_model_path, local_model_path):
    """Load PyTorch artifacts and keep failure modes explicit.

    A malformed local model should become `eligible=False`, not crash the whole
    auditor process without evidence. The caller catches exceptions and returns
    the legacy `(0, False)` pair, while successful loads continue into anomaly
    and utility scoring.
    """

    testdata = torch.load(test_data_path, weights_only=False)

    # The genesis artifact in this reference task is a serialized model object.
    # We evaluate it as the baseline, then load the submitted state_dict into
    # the same architecture for candidate scoring.
    baseline_model = torch.load(genesis_model_path, weights_only=False)
    candidate_model = torch.load(genesis_model_path, weights_only=False)

    # Local model submissions are expected to be full state_dict payloads. This
    # is compatible with the existing aggregator, which averages state_dicts
    # rather than applying custom delta objects.
    candidate_state = torch.load(local_model_path, weights_only=True)

    return testdata, baseline_model, candidate_model, candidate_state


def Score_model_by_auditor(gi, genesis_model_cid, batch_id, model_index, auditor_address, testDataCID, lm_cid, model_base_dir):
    """Score one local model submission for one audit batch.

    This is the first implementation of the scoring design in
    `Developer/issues/scoring-mechanism/`:

    1. read `scoring_policy` from the manifest;
    2. run `eligibility_anomaly_gate` against the submitted state_dict;
    3. evaluate baseline and candidate models on the holdout shard;
    4. normalize the result into today's contract score plus future V2 fields;
    5. write a metric bundle for auditability;
    6. return `(score, eligible)` for the current `setAuditScorenEligibility`
       contract method.

    The current chain path only accepts a 0-100 integer score and a boolean. The
    richer fields are intentionally preserved in the metric bundle so that the
    service can migrate to `setAuditResultV2(...)` without changing the scoring
    math again.

    `genesis_model_cid`/`testDataCID`/`lm_cid` are kept as parameters purely for
    provenance (recorded into the metric bundle); dincli fetches the actual
    artifacts via IPFS before invoking this function and places them at the
    deterministic local paths derived below, so no network access happens here.
    """

    try:
        policy = load_scoring_policy(model_base_dir)

        base_dir = Path(model_base_dir)
        test_data_path = base_dir / "dataset" / "auditor" / "TestDatasets" / f"auditorDataset_{gi}_{batch_id}.pt"
        genesis_model_path = base_dir / "models" / "genesis_model.pth"
        local_model_path = base_dir / "models" / "auditor" / f"lm_{gi}_{model_index}.pth"

        testdata, baseline_model, candidate_model, candidate_state = _load_artifacts(
            test_data_path,
            genesis_model_path,
            local_model_path,
        )

        checks = policy.get("eligibility_checks", {})
        min_eval_examples = int(checks.get("min_eval_examples", 1))
        if hasattr(testdata, "__len__") and len(testdata) < min_eval_examples:
            console.print(
                f"[bold red]Evaluation dataset too small: {len(testdata)} < {min_eval_examples}[/bold red]"
            )
            return 0, False

        base_state = baseline_model.state_dict()

        # Step 1: hard eligibility and anomaly screening. This catches malformed
        # submissions, NaN/Inf tensors, incompatible architectures, and extreme
        # update norms before we let a model into aggregation.
        eligibility = run_eligibility_anomaly_gate(
            base_state=base_state,
            candidate_state=candidate_state,
            policy=policy,
        )

        # A model that fails the gate can still have a metric bundle. We avoid
        # evaluating it if the state_dict is structurally unsafe to load.
        if not eligibility.eligible:
            console.print(f"[bold red]Local model failed eligibility: {eligibility.tags}[/bold red]")
            return 0, False

        # Safe after the architecture gate: strict loading now confirms PyTorch
        # agrees with our state_dict checks before scoring the candidate.
        candidate_model.load_state_dict(candidate_state)

        batch_size = int(policy.get("evaluation", {}).get("batch_size", 32))
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Step 2: holdout-delta scoring. The reference MNIST task uses ordinary
        # classification metrics. The result is intentionally computed against
        # the genesis/current reference model so the score measures marginal
        # utility, not just standalone local-model quality.
        baseline_metrics = evaluate_classification_model(
            baseline_model,
            testdata,
            batch_size=batch_size,
            device=device,
        )
        candidate_metrics = evaluate_classification_model(
            candidate_model,
            testdata,
            batch_size=batch_size,
            device=device,
        )

        result = normalize_holdout_delta_score(
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            eligibility=eligibility,
            policy=policy,
        )

        # Step 3: persist full evidence. Today's contract cannot store this CID,
        # but the local JSON gives auditors and model owners a concrete artifact
        # to compare when investigating score disagreements.
        result = write_metric_bundle(
            result=result,
            policy=policy,
            output_dir=Path(model_base_dir) / "audits" / "metric_bundles" / str(auditor_address),
            gi=gi,
            batch_id=batch_id,
            model_index=model_index,
            auditor_address=auditor_address,
            test_data_cid=testDataCID,
            local_model_cid=lm_cid,
        )

        console.print(f"Audit contract score: {result.contract_score}")
        console.print(f"Audit accepted by policy: {result.accepted}")
        console.print(f"Audit utility score bps: {result.utility_score_bps}")
        console.print(f"Audit baseline delta bps: {result.baseline_delta_bps}")
        console.print(f"Audit anomaly score bps: {result.anomaly_score_bps}")
        console.print(f"Audit metric bundle path: {result.metric_bundle_path}")
        if result.metric_bundle_cid:
            console.print(f"Audit metric bundle CID: {result.metric_bundle_cid}")

        # Legacy compatibility note: submit `accepted` as the current boolean
        # eligibility vote. This lets the old contract gate aggregation while
        # still honoring both eligibility checks and utility thresholds.
        return result.contract_score, result.accepted

    except Exception as e:
        print("can not score model", e)
        return 0, False
