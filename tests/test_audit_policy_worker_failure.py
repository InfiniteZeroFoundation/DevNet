"""Worker-level regression coverage for invalid audit scoring policies (#330)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from dincli.docker.worker import worker


def _copy_reference_services(cache_model: str, model_dir: Path) -> None:
    source = Path(__file__).resolve().parents[1] / cache_model / "services"
    destination = model_dir / "services"
    destination.mkdir(parents=True)
    for name in ("auditor.py", "model.py", "scoring.py"):
        shutil.copy2(source / name, destination / name)


def _run_auditor_worker(model_dir: Path, manifest: dict, tmp_path: Path) -> tuple[int, dict]:
    (model_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    output_path = tmp_path / "worker-result.json"
    job_path = tmp_path / "worker-job.json"
    job_path.write_text(
        json.dumps(
            {
                "network": "local",
                "model_base_dir": str(model_dir),
                "manifest_path": str(model_dir / "manifest.json"),
                "service_path": "services/auditor.py",
                "function_name": "Score_model_by_auditor",
                "args": [0, "genesis", 0, 0, "auditor", "test", "local-model", str(model_dir)],
                "output_path": str(output_path),
                "role": "auditor",
            }
        ),
        encoding="utf-8",
    )

    # The auditor service intentionally imports siblings by short names.
    # Do not let a previous parameterization's copied service mask this one.
    sys.modules.pop("model", None)
    sys.modules.pop("scoring", None)
    status = worker.run(job_path)
    return status, json.loads(output_path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("cache_model", ["cache_model_0", "cache_model_1"])
@pytest.mark.parametrize(
    "policy",
    [
        {
            "audit_scoring_policy": {"metrics": {"thresholds": {"min_accuracy": 70.0}}},
            "scoring_policy": {"metrics": {"thresholds": {"min_accuracy": 80.0}}},
        },
        {"audit_scoring_policy": {"metrics": {"thresholds": []}}},
    ],
)
def test_invalid_audit_policy_is_a_worker_failure(tmp_path, cache_model, policy):
    """Configuration must not be serialized as a zero/rejected candidate vote."""
    model_dir = tmp_path / cache_model
    _copy_reference_services(cache_model, model_dir)

    exit_code, result = _run_auditor_worker(model_dir, policy, tmp_path)

    assert exit_code == 1
    assert result["status"] == "error"
    assert "result" not in result
    assert "manifest" in result["error"] or "audit scoring policy" in result["error"]
