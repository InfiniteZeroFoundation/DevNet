"""Regression coverage for standalone encrypted audit shards (#329)."""

from __future__ import annotations

import io
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
import torch
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _stub_dincli_if_missing():
    """Provide only the IPFS imports needed to load the shipped services."""
    try:
        import dincli.services.ipfs  # noqa: F401
    except ImportError:
        dincli_pkg = types.ModuleType("dincli")
        services_pkg = types.ModuleType("dincli.services")
        ipfs_module = types.ModuleType("dincli.services.ipfs")
        ipfs_module.upload_to_ipfs = lambda *args, **kwargs: "stub-cid"
        ipfs_module.retrieve_from_ipfs = lambda *args, **kwargs: None
        sys.modules.setdefault("dincli", dincli_pkg)
        sys.modules.setdefault("dincli.services", services_pkg)
        sys.modules.setdefault("dincli.services.ipfs", ipfs_module)


def _load_modelowner(cache_model: str):
    _stub_dincli_if_missing()
    path = Path(__file__).resolve().parents[1] / cache_model / "services" / "modelowner.py"
    spec = spec_from_file_location(f"{cache_model}_audit_shard_modelowner", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["cache_model_0", "cache_model_1"])
def modelowner(request):
    return _load_modelowner(request.param)


def _expected_indices(modelowner, sample_count: int, gi: int, batch_id: int) -> list[int]:
    reserved = modelowner._select_reserved_pool(sample_count)
    round_pool = modelowner._resample_round_pool(reserved, gi, is_final_round=False)
    generator = torch.Generator().manual_seed(batch_id)
    batch_size = int(sample_count * 0.05)
    local_indices = torch.randperm(len(round_pool), generator=generator)[:batch_size]
    return round_pool[local_indices].tolist()


def _load_saved_bytes(raw_bytes: bytes):
    return torch.load(io.BytesIO(raw_bytes), weights_only=False)


class _NestedTensorViewDataset(torch.utils.data.Dataset):
    """Samples whose nested label contains a view into a much larger tensor."""

    def __init__(self, sample_count: int):
        self.inputs = torch.arange(sample_count * 4, dtype=torch.float32).reshape(sample_count, 4)
        # 2,000 rows × 256 bytes: retaining this view's storage would expose
        # all 512,000 bytes in each supposedly small audit shard.
        self.label_backing = torch.arange(sample_count * 64, dtype=torch.int32).reshape(sample_count, 64)

    def __len__(self):
        return len(self.inputs)

    def __getitem__(self, index):
        return (
            self.inputs[index],
            {"label": [self.label_backing[index : index + 1]]},
        )


def test_audit_shard_contains_only_selected_standalone_samples(tmp_path, monkeypatch, modelowner):
    """The raw and encrypted artifacts must not retain a TensorDataset parent."""
    sample_count = 2_000
    inputs = torch.arange(sample_count * 32, dtype=torch.float32).reshape(sample_count, 32)
    labels = torch.arange(sample_count, dtype=torch.int64)
    parent = torch.utils.data.TensorDataset(inputs, labels)
    source_path = tmp_path / "test_dataset.pt"
    torch.save(parent, source_path)

    monkeypatch.setattr(modelowner, "upload_to_ipfs", lambda *args, **kwargs: "bafy-audit-shard")
    result = modelowner.create_audit_testDataCIDs(
        batch_counts=1,
        gi=7,
        base_path=tmp_path,
        test_data_path=source_path,
    )

    selected_indices = _expected_indices(modelowner, sample_count, gi=7, batch_id=0)
    artifact_dir = tmp_path / "dataset" / "auditor" / "TestDatasets"
    raw_path = artifact_dir / "auditorDataset_7_0.pt"
    encrypted_path = artifact_dir / "auditorDataset_7_0.pt.enc"
    raw_bytes = raw_path.read_bytes()
    shard = _load_saved_bytes(raw_bytes)
    safe_shard = torch.load(raw_path, weights_only=True)

    assert isinstance(shard, list)
    assert [label.item() for _, label in safe_shard] == [label.item() for _, label in shard]
    assert not hasattr(shard, "dataset")
    assert len(shard) == len(selected_indices)
    assert all(isinstance(sample, tuple) and len(sample) == 2 for sample in shard)
    assert [label.item() for _, label in shard] == selected_indices
    assert torch.equal(
        torch.stack([input_value for input_value, _ in shard]),
        inputs[selected_indices],
    )
    batched_inputs, batched_labels = next(iter(torch.utils.data.DataLoader(shard, batch_size=8)))
    assert torch.equal(batched_inputs, inputs[selected_indices[:8]])
    assert torch.equal(batched_labels, labels[selected_indices[:8]])

    # A serialized parent dataset is substantially larger than its 5% shard.
    parent_buffer = io.BytesIO()
    torch.save(parent, parent_buffer)
    assert len(raw_bytes) < len(parent_buffer.getvalue()) // 4

    # The ciphertext carries exactly the same standalone sequence.
    ciphertext = encrypted_path.read_bytes()
    key = result[0]["K"]
    decrypted = AESGCM(key).decrypt(ciphertext[:12], ciphertext[12:], None)
    decrypted_shard = _load_saved_bytes(decrypted)
    safe_decrypted_shard = torch.load(io.BytesIO(decrypted), weights_only=True)
    assert [label.item() for _, label in decrypted_shard] == selected_indices
    assert [label.item() for _, label in safe_decrypted_shard] == selected_indices

    # The serialized tensors must have their own storage, not aliases of the
    # parent dataset. Mutating the parent after serialization cannot alter it.
    inputs[selected_indices[0]].fill_(-1)
    assert shard[0][0][0].item() != -1


def test_audit_shard_recursively_clones_nested_tensor_views(tmp_path, monkeypatch, modelowner):
    sample_count = 2_000
    parent = _NestedTensorViewDataset(sample_count)
    source_path = tmp_path / "nested_test_dataset.pt"
    torch.save(parent, source_path)
    monkeypatch.setattr(modelowner, "upload_to_ipfs", lambda *args, **kwargs: "bafy-nested-shard")

    result = modelowner.create_audit_testDataCIDs(
        batch_counts=1,
        gi=3,
        base_path=tmp_path,
        test_data_path=source_path,
    )

    expected = _expected_indices(modelowner, sample_count, gi=3, batch_id=0)
    artifact_dir = tmp_path / "dataset" / "auditor" / "TestDatasets"
    raw_shard = torch.load(artifact_dir / "auditorDataset_3_0.pt", weights_only=False)
    nested_label = raw_shard[0][1]["label"][0]
    assert nested_label.tolist() == parent.label_backing[expected[0] : expected[0] + 1].tolist()
    assert nested_label.untyped_storage().nbytes() == nested_label.numel() * nested_label.element_size()
    unassigned_index = next(index for index in range(sample_count) if index not in expected)
    assert parent.label_backing[unassigned_index].tolist() not in nested_label.tolist()

    # The decrypted artifact must retain only the cloned nested view as well.
    ciphertext = (artifact_dir / "auditorDataset_3_0.pt.enc").read_bytes()
    decrypted = AESGCM(result[0]["K"]).decrypt(ciphertext[:12], ciphertext[12:], None)
    decrypted_label = _load_saved_bytes(decrypted)[0][1]["label"][0]
    assert decrypted_label.untyped_storage().nbytes() == decrypted_label.numel() * decrypted_label.element_size()

    # PyTorch's default collator can still batch the supported nested values.
    batched_inputs, batched_labels = next(iter(torch.utils.data.DataLoader(raw_shard, batch_size=4)))
    assert batched_inputs.shape == (4, 4)
    assert batched_labels["label"][0].shape == (4, 1, 64)


def test_audit_shard_rejects_unsupported_values_before_upload(modelowner):
    with pytest.raises(TypeError, match="unsupported audit sample value"):
        modelowner._clone_audit_value(object())
