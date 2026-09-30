"""Coverage for cache_model_0/services/modelowner.py's test-set resampling
policy (task_210726_6 §2c): a fixed ~40% reserved pool, resampled to half
per round, with the full reserved pool exposed only on the final round.

modelowner.py imports from `dincli.services.ipfs` / `dincli.cli.utils` at
module level, which pulls in `typer` -- not installed in this environment
(same as the rest of dincli's dependency tree). Rather than mocking around
the real functions under test, this stubs just enough of `dincli` in
sys.modules for modelowner.py's imports to succeed, then loads and tests the
actual shipped code, not a reimplementation of it.
"""

from __future__ import annotations

import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

try:
    import torch
except ImportError as exc:
    raise ImportError("torch is required for tests/test_resampling_policy.py but is not installed in this environment") from exc


def _stub_dincli_if_missing():
    """Insert minimal fake dincli.services.ipfs / dincli.cli.utils modules so
    modelowner.py's top-level imports succeed, only if the real dincli isn't
    importable (i.e. `typer` isn't installed) -- if the real package is
    present, do nothing and let it be used as-is."""
    try:
        import dincli.cli.utils  # noqa: F401
        return
    except ImportError:
        pass

    dincli_pkg = types.ModuleType("dincli")
    dincli_services_pkg = types.ModuleType("dincli.services")
    dincli_cli_pkg = types.ModuleType("dincli.cli")
    dincli_services_ipfs = types.ModuleType("dincli.services.ipfs")
    dincli_cli_utils = types.ModuleType("dincli.cli.utils")

    dincli_services_ipfs.upload_to_ipfs = lambda *args, **kwargs: "stub-cid"
    dincli_services_ipfs.retrieve_from_ipfs = lambda *args, **kwargs: None
    dincli_cli_utils.CONFIG_DIR = Path("/tmp")

    sys.modules["dincli"] = dincli_pkg
    sys.modules["dincli.services"] = dincli_services_pkg
    sys.modules["dincli.cli"] = dincli_cli_pkg
    sys.modules["dincli.services.ipfs"] = dincli_services_ipfs
    sys.modules["dincli.cli.utils"] = dincli_cli_utils


def load_modelowner_module():
    _stub_dincli_if_missing()
    modelowner_path = Path(__file__).resolve().parents[1] / "cache_model_0" / "services" / "modelowner.py"
    spec = spec_from_file_location("cache_model_0_modelowner", modelowner_path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


modelowner = load_modelowner_module()

TOTAL_SAMPLES = 1000


class TestReservedPool:
    def test_reserved_pool_is_documented_fraction_of_total(self):
        pool = modelowner._select_reserved_pool(TOTAL_SAMPLES, reserved_pool_fraction=0.4, seed=0)
        assert len(pool) == 400

    def test_reserved_pool_is_deterministic_across_calls(self):
        """Fixed seed -- the reserved pool must be IDENTICAL every time it's
        computed, not just the same size. This is what makes 'resampling'
        from it meaningful (a stable underlying reservation, not a fresh
        random subset masquerading as one)."""
        pool_a = modelowner._select_reserved_pool(TOTAL_SAMPLES)
        pool_b = modelowner._select_reserved_pool(TOTAL_SAMPLES)
        assert torch.equal(pool_a, pool_b)

    def test_reserved_pool_has_no_duplicate_indices(self):
        pool = modelowner._select_reserved_pool(TOTAL_SAMPLES)
        assert len(torch.unique(pool)) == len(pool)

    def test_different_seed_gives_different_pool(self):
        pool_a = modelowner._select_reserved_pool(TOTAL_SAMPLES, seed=0)
        pool_b = modelowner._select_reserved_pool(TOTAL_SAMPLES, seed=1)
        assert not torch.equal(pool_a, pool_b)


class TestRoundResampling:
    def test_final_round_returns_full_reserved_pool_unchanged(self):
        reserved = modelowner._select_reserved_pool(TOTAL_SAMPLES)
        round_pool = modelowner._resample_round_pool(reserved, gi=5, is_final_round=True)
        assert torch.equal(round_pool, reserved)

    def test_non_final_round_returns_half_the_reserved_pool(self):
        reserved = modelowner._select_reserved_pool(TOTAL_SAMPLES)
        round_pool = modelowner._resample_round_pool(reserved, gi=1, is_final_round=False, resample_fraction=0.5)
        assert len(round_pool) == len(reserved) // 2

    def test_round_pool_is_subset_of_reserved_pool(self):
        """Every index exposed this round must actually belong to the
        reserved pool -- the resample must never introduce indices outside
        the task's originally-reserved 40%, which would defeat the entire
        point of bounding cumulative exposure."""
        reserved = modelowner._select_reserved_pool(TOTAL_SAMPLES)
        round_pool = modelowner._resample_round_pool(reserved, gi=3, is_final_round=False)
        reserved_set = set(reserved.tolist())
        assert all(idx in reserved_set for idx in round_pool.tolist())

    def test_different_gi_gives_different_resample(self):
        """The whole point of 'resampled half per round' is that it's a
        FRESH half each round, not the same half repeated -- otherwise
        auditors converge on knowing the same subset every round, same
        leakage risk as no resampling at all."""
        reserved = modelowner._select_reserved_pool(TOTAL_SAMPLES)
        round1 = modelowner._resample_round_pool(reserved, gi=1, is_final_round=False)
        round2 = modelowner._resample_round_pool(reserved, gi=2, is_final_round=False)
        assert not torch.equal(round1, round2)

    def test_same_gi_gives_same_resample_deterministic(self):
        """Calling with the same gi twice (e.g. a retried transaction) must
        not silently produce a different test set the second time."""
        reserved = modelowner._select_reserved_pool(TOTAL_SAMPLES)
        round_a = modelowner._resample_round_pool(reserved, gi=7, is_final_round=False)
        round_b = modelowner._resample_round_pool(reserved, gi=7, is_final_round=False)
        assert torch.equal(round_a, round_b)

    @pytest.mark.parametrize("fraction", [0.25, 0.5, 0.75])
    def test_resample_fraction_is_respected(self, fraction):
        reserved = modelowner._select_reserved_pool(TOTAL_SAMPLES)
        round_pool = modelowner._resample_round_pool(reserved, gi=1, is_final_round=False, resample_fraction=fraction)
        assert len(round_pool) == int(len(reserved) * fraction)


class TestCreateAuditTestDataCIDsIntegration:
    """End-to-end through create_audit_testDataCIDs itself (real file I/O to
    tmp_path, IPFS upload stubbed), confirming the wiring -- not just the
    two helper functions in isolation."""

    def _write_test_dataset(self, tmp_path: Path, n: int = TOTAL_SAMPLES) -> Path:
        data = torch.utils.data.TensorDataset(torch.randn(n, 4), torch.randint(0, 2, (n,)))
        dataset_dir = tmp_path / "dataset" / "test"
        dataset_dir.mkdir(parents=True)
        dataset_path = dataset_dir / "test_dataset.pt"
        torch.save(data, dataset_path)
        return dataset_path

    def test_final_round_batches_can_draw_from_full_reserved_pool(self, tmp_path, monkeypatch):
        self._write_test_dataset(tmp_path)
        monkeypatch.setattr(modelowner, "upload_to_ipfs", lambda *a, **k: "stub-cid")

        cids = modelowner.create_audit_testDataCIDs(
            batch_counts=2, gi=1, base_path=str(tmp_path), is_final_round=True
        )
        assert len(cids) == 2

        batch0 = torch.load(tmp_path / "dataset" / "auditor" / "TestDatasets" / "auditorDataset_1_0.pt", weights_only=False)
        # 5% of 1000 = 50 samples per batch, well within the full 400-sample
        # reserved pool available on the final round.
        assert len(batch0) == 50

    def test_default_is_final_round_false_matches_existing_dincli_call_site(self, tmp_path, monkeypatch):
        """The real dincli call site (dincli/cli/modelownerd/auditor_batches.py)
        calls this with exactly 4 positional args today and does not pass
        is_final_round -- confirming that exact call shape still works
        unchanged is what makes this a non-breaking addition to the hook."""
        self._write_test_dataset(tmp_path)
        monkeypatch.setattr(modelowner, "upload_to_ipfs", lambda *a, **k: "stub-cid")

        cids = modelowner.create_audit_testDataCIDs(2, 1, str(tmp_path), None)
        assert len(cids) == 2
