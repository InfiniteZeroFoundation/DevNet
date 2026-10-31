#!/usr/bin/env python3
"""
scripts/dp_noise_multiplier_sweep.py — reproduces Finding 2 of
Documentation/technical/audits/dp-clipping-norm-verification.md: at the
manifest default noise_multiplier (0.5), Gaussian DP noise collapses model
utility regardless of clipping_norm, because the noise's *aggregate* L2 norm
scales with sqrt(num_parameters), not just noise_multiplier * clipping_norm.

Uses the exact same training fixture as tests/test_cache_client_dp.py's
_build_and_train_reference() (the committed cache_model_0/dataset/test/
test_dataset.pt, seed=42, n_samples=2000, 20 epochs, lr=0.01), so the
post-training/delta norms here are directly comparable to that test's pinned
values (~9.44 / ~3.62) -- no network access or extra dependencies beyond
what the repo already requires for tests/test_cache_client_dp.py (torch).

Usage:
    python3 scripts/dp_noise_multiplier_sweep.py
"""
from __future__ import annotations

import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import torch
import torch.nn as nn

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CACHE_MODEL_0 = _REPO_ROOT / "cache_model_0"


def _load_module(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_model_module():
    return _load_module("cache_model_0_model", _CACHE_MODEL_0 / "services" / "model.py")


def load_client_module():
    return _load_module("cache_model_0_client", _CACHE_MODEL_0 / "services" / "client.py")


def load_test_dataset():
    """Load cache_model_0/dataset/test/test_dataset.pt without torchvision.

    Mirrors tests/test_cache_client_dp.py's _load_test_dataset(): stubs the
    torchvision classes referenced by the pickle so the raw tensors can be
    recovered with only torch installed.
    """

    class _VD:
        def __setstate__(self, d):
            self.__dict__.update(d)

    class _MNIST(_VD):
        pass

    class _ST(_VD):
        pass

    class _Compose(_VD):
        pass

    class _ToTensor(_Compose):
        pass

    class _Normalize(_Compose):
        pass

    stub_specs = [
        ("torchvision", {}),
        ("torchvision.datasets", {}),
        ("torchvision.datasets.mnist", {"MNIST": _MNIST}),
        ("torchvision.datasets.vision", {"StandardTransform": _ST}),
        ("torchvision.transforms", {}),
        ("torchvision.transforms.transforms", {"Compose": _Compose, "ToTensor": _ToTensor, "Normalize": _Normalize}),
    ]
    added = {}
    for mod_name, attrs in stub_specs:
        if mod_name not in sys.modules:
            m = types.ModuleType(mod_name)
            m.__path__ = []
            m.__package__ = mod_name
            for attr, cls in attrs.items():
                setattr(m, attr, cls)
            sys.modules[mod_name] = m
            added[mod_name] = m

    try:
        dataset_path = _CACHE_MODEL_0 / "dataset" / "test" / "test_dataset.pt"
        obj = torch.load(dataset_path, weights_only=False)
        x = obj.data.float().unsqueeze(1) / 255.0
        y = obj.targets.clone()
        return x, y
    finally:
        for mod_name in added:
            sys.modules.pop(mod_name, None)


def build_and_train_reference(n_samples=2000, num_epochs=20, lr=0.01, seed=42):
    """Same fixture as tests/test_cache_client_dp.py's _build_and_train_reference()."""
    model_module = load_model_module()
    criterion = nn.CrossEntropyLoss()

    x_all, y_all = load_test_dataset()
    rng_sample = torch.Generator().manual_seed(seed)
    idx = torch.randperm(len(x_all), generator=rng_sample)[:n_samples]
    x_sub, y_sub = x_all[idx], y_all[idx]

    n_train = int(0.8 * n_samples)
    x_train, y_train = x_sub[:n_train], y_sub[:n_train]
    x_test, y_test = x_sub[n_train:], y_sub[n_train:]

    torch.manual_seed(seed)
    model = model_module.ModelArchitecture()
    ref_sd = {k: v.detach().clone() for k, v in model.state_dict().items()}

    batch_size = 32
    rng_train = torch.Generator().manual_seed(seed)
    for _ in range(num_epochs):
        perm = torch.randperm(len(x_train), generator=rng_train)
        for start in range(0, len(x_train) - batch_size + 1, batch_size):
            batch_idx = perm[start:start + batch_size]
            loss = criterion(model(x_train[batch_idx]), y_train[batch_idx])
            loss.backward()
            with torch.no_grad():
                for p in model.parameters():
                    if p.grad is not None:
                        p -= lr * p.grad
                        p.grad.zero_()

    trained_sd = {k: v.detach().clone() for k, v in model.state_dict().items()}
    return ref_sd, trained_sd, x_test, y_test


def evaluate_accuracy(model_module, state_dict, x, y):
    m = model_module.ModelArchitecture()
    m.load_state_dict(state_dict)
    m.eval()
    with torch.no_grad():
        preds = m(x).argmax(dim=1)
    return (preds == y).float().mean().item()


def combined_l2_norm(state_dict):
    total_sq = 0.0
    for value in state_dict.values():
        if torch.is_tensor(value) and torch.is_floating_point(value):
            total_sq += torch.norm(value).item() ** 2
    return total_sq ** 0.5


def main():
    client = load_client_module()
    model_module = load_model_module()

    ref_sd, trained_sd, x_test, y_test = build_and_train_reference()

    baseline_acc = evaluate_accuracy(model_module, trained_sd, x_test, y_test)
    post_training_norm = combined_l2_norm(trained_sd)
    local_delta = client.compute_state_dict_delta(trained_sd, ref_sd)
    delta_norm = combined_l2_norm(local_delta)

    print(f"Baseline (no DP) holdout accuracy: {baseline_acc:.4f}")
    print(f"Post-training combined L2 norm:     {post_training_norm:.2f}")
    print(f"One-round delta L2 norm:             {delta_norm:.2f}")
    print()
    print("noise_multiplier sweep (update_gaussian, clipping_norm fixed at the")
    print("measured delta norm so no clipping distortion is introduced):")
    print(f"{'noise_multiplier':>18} | accuracy")
    print("-" * 32)

    for noise_multiplier in [0.5, 0.1, 0.01, 0.001, 0.0005, 0.0]:
        dp_config = {
            "enabled": True,
            "mechanism": "update_gaussian",
            "parameters": {
                "clipping_norm": delta_norm,
                "noise_multiplier": noise_multiplier,
                "clip_scope": "global",
            },
        }
        out = client.apply_dp_mechanism(trained_sd, dp_config, reference_state_dict=ref_sd)
        acc = evaluate_accuracy(model_module, out, x_test, y_test)
        print(f"{noise_multiplier:>18} | {acc:.4f}")


if __name__ == "__main__":
    main()
