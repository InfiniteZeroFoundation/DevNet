import copy
import json
import math
from collections import OrderedDict
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

try:
    import torch
    import torch.nn as nn
except ImportError as exc:
    raise ImportError(
        "torch is required for tests/test_cache_client_dp.py but is not installed "
        "in this environment"
    ) from exc


def load_client_module():
    client_path = Path(__file__).resolve().parents[1] / "cache_model_0" / "services" / "client.py"
    spec = spec_from_file_location("cache_model_0_client", client_path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DummyRuntime:
    def __init__(self, manifest):
        self.manifest = manifest

    def get_manifest_key(self, key, default=None):
        return self.manifest.get(key, default)


def test_resolve_dp_config_uses_nested_manifest():
    client = load_client_module()
    runtime = DummyRuntime(
        {
            "dp": {
                "enabled": True,
                "mode": "afterTraining",
                "mechanism": "update_gaussian",
                "parameters": {
                    "clipping_norm": 2.0,
                    "noise_multiplier": 0.0,
                    "clip_scope": "global",
                },
            },
        }
    )

    dp_config = client.resolve_dp_config(runtime=runtime)

    assert dp_config["enabled"] is True
    assert dp_config["mode"] == "afterTraining"
    assert dp_config["mechanism"] == "update_gaussian"
    assert dp_config["parameters"]["clipping_norm"] == 2.0
    assert dp_config["parameters"]["clip_scope"] == "global"


@pytest.mark.parametrize(
    "mechanism",
    [
        "post_training_gaussian",
        "post_training_laplace",
    ],
)
def test_post_training_mechanisms_preserve_weights_when_noise_is_zero(mechanism):
    client = load_client_module()
    trained_state_dict = OrderedDict(
        {
            "weight": torch.tensor([1.5, -0.5], dtype=torch.float32),
            "counter": torch.tensor([3], dtype=torch.long),
        }
    )
    dp_config = {
        "enabled": True,
        "mode": "afterTraining",
        "mechanism": mechanism,
        "parameters": {
            "clipping_norm": 100.0,
            "noise_multiplier": 0.0,
            "laplace_scale": 0.0,
            "clip_scope": "per_layer",
        },
    }

    private_state_dict = client.apply_dp_mechanism(trained_state_dict, dp_config)

    assert torch.equal(private_state_dict["weight"], trained_state_dict["weight"])
    assert torch.equal(private_state_dict["counter"], trained_state_dict["counter"])


def test_update_gaussian_preserves_weights_when_noise_is_zero():
    client = load_client_module()
    reference_state_dict = OrderedDict(
        {
            "weight": torch.tensor([0.2, 0.4], dtype=torch.float32),
            "counter": torch.tensor([1], dtype=torch.long),
        }
    )
    trained_state_dict = OrderedDict(
        {
            "weight": torch.tensor([0.8, 1.0], dtype=torch.float32),
            "counter": torch.tensor([2], dtype=torch.long),
        }
    )
    dp_config = {
        "enabled": True,
        "mode": "afterTraining",
        "mechanism": "update_gaussian",
        "parameters": {
            "clipping_norm": 100.0,
            "noise_multiplier": 0.0,
            "clip_scope": "global",
        },
    }

    private_state_dict = client.apply_dp_mechanism(
        trained_state_dict,
        dp_config,
        reference_state_dict=reference_state_dict,
    )

    assert torch.equal(private_state_dict["weight"], trained_state_dict["weight"])
    assert torch.equal(private_state_dict["counter"], trained_state_dict["counter"])


def test_laplace_noise_is_finite_at_the_uniform_lower_bound(monkeypatch):
    """torch.rand_like samples [0, 1), so a draw of exactly 0.0 is attainable.

    Before the clamp, that produced log1p(-1) = -inf for every affected
    element. For float32 the draw has probability 2**-24, which is roughly
    0.6 expected occurrences per noising pass on a 10M-parameter model.
    """

    client = load_client_module()
    monkeypatch.setattr(client.torch, "rand_like", lambda t, **kw: torch.zeros_like(t))

    noised = client.add_laplace_noise(torch.ones(8, dtype=torch.float32), 0.35)

    assert torch.isfinite(noised).all()
    assert not torch.isnan(noised).any()


def test_laplace_noise_is_finite_over_real_sampling():
    client = load_client_module()
    torch.manual_seed(0)

    noised = client.add_laplace_noise(torch.zeros(100_000, dtype=torch.float32), 0.35)

    assert torch.isfinite(noised).all()

DP_MECHANISMS = [
    "post_training_gaussian",
    "post_training_laplace",
    "update_gaussian",
    "update_laplace",
]


def build_small_state_dict(num_elements=20000):
    """Build a state_dict whose L1 *and* L2 norm sit well inside every
    clipping norm used below, so clipping is a no-op and the only difference
    between input and output is the noise itself. The L1 norm is the binding
    constraint here (it is `num_elements * magnitude`, with no sqrt to shrink
    it), which is why the per-element magnitude is much smaller than the L2
    case alone would need."""
    return OrderedDict(
        {
            "weight": torch.full((num_elements,), 1e-6, dtype=torch.float32),
            "counter": torch.tensor([7], dtype=torch.long),
        }
    )


def measure_noise_std(client, mechanism, clipping_norm, noise_multiplier=0.25, seed=0):
    """Run one mechanism and return the standard deviation of what it added."""
    trained_state_dict = build_small_state_dict()
    reference_state_dict = OrderedDict(
        {
            "weight": torch.zeros_like(trained_state_dict["weight"]),
            "counter": torch.tensor([7], dtype=torch.long),
        }
    )
    dp_config = {
        "enabled": True,
        "mode": "afterTraining",
        "mechanism": mechanism,
        "parameters": {
            "clipping_norm": clipping_norm,
            "noise_multiplier": noise_multiplier,
            "laplace_scale": noise_multiplier,
            "clip_scope": "global",
        },
    }

    torch.manual_seed(seed)
    private_state_dict = client.apply_dp_mechanism(
        trained_state_dict,
        dp_config,
        reference_state_dict=reference_state_dict,
    )
    difference = private_state_dict["weight"] - trained_state_dict["weight"]
    return difference.std().item()


@pytest.mark.parametrize("mechanism", DP_MECHANISMS)
def test_noise_scales_with_clipping_norm(mechanism):
    """`noise_multiplier` scales the sensitivity, and for these mechanisms the
    sensitivity is the clipping norm. Quadrupling `clipping_norm` at a fixed
    multiplier must quadruple the noise. When the two were independent this
    ratio was 1.0, so the configured privacy level moved without the noise
    following it."""
    client = load_client_module()

    std_at_1 = measure_noise_std(client, mechanism, clipping_norm=1.0)
    std_at_4 = measure_noise_std(client, mechanism, clipping_norm=4.0)

    assert std_at_1 > 0.0
    assert std_at_4 / std_at_1 == pytest.approx(4.0, rel=0.05)


@pytest.mark.parametrize("mechanism", DP_MECHANISMS)
@pytest.mark.parametrize("clipping_norm", [0.0, -1.0])
def test_non_positive_clipping_norm_is_rejected(mechanism, clipping_norm):
    """A non-positive `clipping_norm` disables clipping, which leaves no
    sensitivity for the noise to be calibrated against. Running the mechanism
    anyway produces either unbounded weights with noise on top or a silent
    no-op, depending on the version, and neither is a privacy guarantee. It is
    rejected rather than interpreted."""
    client = load_client_module()

    with pytest.raises(ValueError, match="clipping_norm"):
        measure_noise_std(client, mechanism, clipping_norm=clipping_norm)


@pytest.mark.parametrize("clipping_norm", [0.0, -1.0])
def test_resolve_dp_config_rejects_non_positive_clipping_norm(clipping_norm):
    """The same rejection happens when the manifest is resolved, so a bad
    clipping norm is caught before any training output reaches a mechanism."""
    client = load_client_module()
    runtime = DummyRuntime(
        {
            "dp": {
                "enabled": True,
                "mode": "afterTraining",
                "mechanism": "update_gaussian",
                "parameters": {"clipping_norm": clipping_norm},
            },
        }
    )

    with pytest.raises(ValueError, match="clipping_norm"):
        client.resolve_dp_config(runtime=runtime)


def test_laplace_requires_an_explicit_scale():
    """`laplace_scale` used to fall back to `noise_multiplier`. The two carry
    different units and are calibrated differently, so inheriting one for the
    other silently produced a scale nobody chose."""
    client = load_client_module()
    trained_state_dict = build_small_state_dict()
    dp_config = {
        "enabled": True,
        "mode": "afterTraining",
        "mechanism": "post_training_laplace",
        "parameters": {"clipping_norm": 1.0, "noise_multiplier": 0.25},
    }

    with pytest.raises(ValueError, match="laplace_scale"):
        client.apply_dp_mechanism(trained_state_dict, dp_config)


def test_resolve_dp_config_requires_laplace_scale():
    """A Laplace manifest without its own scale is rejected at resolution
    rather than silently borrowing the Gaussian multiplier."""
    client = load_client_module()
    runtime = DummyRuntime(
        {
            "dp": {
                "enabled": True,
                "mode": "afterTraining",
                "mechanism": "post_training_laplace",
                "parameters": {"clipping_norm": 1.0, "noise_multiplier": 0.25},
            },
        }
    )

    with pytest.raises(ValueError, match="laplace_scale"):
        client.resolve_dp_config(runtime=runtime)


def test_global_clip_scope_bounds_the_combined_norm():
    """Clipping n tensors independently to `clipping_norm` bounds the combined
    L2 norm at clipping_norm * sqrt(n), not at clipping_norm. Only `global`
    produces the bound the noise is calibrated against, and the gap widens as
    model depth grows."""
    client = load_client_module()
    num_tensors = 16
    clipping_norm = 1.0
    state_dict = OrderedDict(
        {
            f"layer_{index}.weight": torch.full((4,), 1.0, dtype=torch.float32)
            for index in range(num_tensors)
        }
    )

    def combined_norm(candidate_state_dict):
        squared = sum(
            torch.norm(value).item() ** 2 for value in candidate_state_dict.values()
        )
        return squared ** 0.5

    per_layer_state_dict = client.clip_state_dict(state_dict, clipping_norm, "per_layer")
    global_state_dict = client.clip_state_dict(state_dict, clipping_norm, "global")

    assert combined_norm(per_layer_state_dict) == pytest.approx(
        clipping_norm * num_tensors ** 0.5, rel=1e-4
    )
    assert combined_norm(global_state_dict) == pytest.approx(clipping_norm, rel=1e-4)


def test_global_clip_scope_bounds_the_combined_l1_norm():
    """Same composition gap as the L2 case above, but for norm_type='l1'
    (used by update_laplace, issue #279 F4): clipping n tensors independently
    to L1 norm `clipping_norm` bounds the combined L1 norm at
    `clipping_norm * n` (no sqrt -- L1 is exactly additive across tensors),
    not at `clipping_norm`. Only `global` produces the L1 bound the Laplace
    mechanism is actually calibrated against."""
    client = load_client_module()
    num_tensors = 16
    clipping_norm = 1.0
    state_dict = OrderedDict(
        {
            f"layer_{index}.weight": torch.full((4,), 1.0, dtype=torch.float32)
            for index in range(num_tensors)
        }
    )

    def combined_l1_norm(candidate_state_dict):
        return sum(torch.sum(torch.abs(value)).item() for value in candidate_state_dict.values())

    per_layer_state_dict = client.clip_state_dict(state_dict, clipping_norm, "per_layer", norm_type="l1")
    global_state_dict = client.clip_state_dict(state_dict, clipping_norm, "global", norm_type="l1")

    assert combined_l1_norm(per_layer_state_dict) == pytest.approx(
        clipping_norm * num_tensors, rel=1e-4
    )
    assert combined_l1_norm(global_state_dict) == pytest.approx(clipping_norm, rel=1e-4)


def test_update_laplace_preserves_weights_when_noise_is_zero():
    client = load_client_module()
    reference_state_dict = OrderedDict(
        {
            "weight": torch.tensor([0.2, 0.4], dtype=torch.float32),
            "counter": torch.tensor([1], dtype=torch.long),
        }
    )
    trained_state_dict = OrderedDict(
        {
            "weight": torch.tensor([0.8, 1.0], dtype=torch.float32),
            "counter": torch.tensor([2], dtype=torch.long),
        }
    )
    dp_config = {
        "enabled": True,
        "mode": "afterTraining",
        "mechanism": "update_laplace",
        "parameters": {
            "clipping_norm": 100.0,
            "laplace_scale": 0.0,
            "clip_scope": "global",
        },
    }

    private_state_dict = client.apply_dp_mechanism(
        trained_state_dict,
        dp_config,
        reference_state_dict=reference_state_dict,
    )

    assert torch.equal(private_state_dict["weight"], trained_state_dict["weight"])
    assert torch.equal(private_state_dict["counter"], trained_state_dict["counter"])


def test_update_laplace_requires_a_reference_state_dict():
    client = load_client_module()
    trained_state_dict = build_small_state_dict()
    dp_config = {
        "enabled": True,
        "mode": "afterTraining",
        "mechanism": "update_laplace",
        "parameters": {"clipping_norm": 1.0, "laplace_scale": 0.25},
    }

    with pytest.raises(ValueError, match="reference_state_dict"):
        client.apply_dp_mechanism(trained_state_dict, dp_config)


def test_update_laplace_requires_an_explicit_scale():
    """Same requirement as post_training_laplace -- update_laplace's noise is
    also Laplace-distributed, so it needs its own scale rather than
    inheriting noise_multiplier."""
    client = load_client_module()
    trained_state_dict = build_small_state_dict()
    reference_state_dict = OrderedDict(
        {
            "weight": torch.zeros_like(trained_state_dict["weight"]),
            "counter": torch.tensor([7], dtype=torch.long),
        }
    )
    dp_config = {
        "enabled": True,
        "mode": "afterTraining",
        "mechanism": "update_laplace",
        "parameters": {"clipping_norm": 1.0, "noise_multiplier": 0.25},
    }

    with pytest.raises(ValueError, match="laplace_scale"):
        client.apply_dp_mechanism(trained_state_dict, dp_config, reference_state_dict=reference_state_dict)


def test_resolve_dp_config_requires_laplace_scale_for_update_laplace():
    client = load_client_module()
    runtime = DummyRuntime(
        {
            "dp": {
                "enabled": True,
                "mode": "afterTraining",
                "mechanism": "update_laplace",
                "parameters": {"clipping_norm": 1.0},
            },
        }
    )

    with pytest.raises(ValueError, match="laplace_scale"):
        client.resolve_dp_config(runtime=runtime)


def test_resolve_dp_config_does_not_warn_for_update_laplace(capsys):
    client = load_client_module()
    runtime = DummyRuntime(
        {
            "dp": {
                "enabled": True,
                "mode": "afterTraining",
                "mechanism": "update_laplace",
                "parameters": {"clipping_norm": 1.0, "laplace_scale": 0.25},
            },
        }
    )

    client.resolve_dp_config(runtime=runtime)

    captured = capsys.readouterr()
    assert "experimental" not in captured.out.lower()


def test_resolve_dp_config_defaults_clip_scope_to_global():
    """A manifest that does not set `clip_scope` gets the scope whose clip
    matches the sensitivity the noise assumes."""
    client = load_client_module()
    runtime = DummyRuntime(
        {
            "dp": {
                "enabled": True,
                "mode": "afterTraining",
                "mechanism": "update_gaussian",
            },
        }
    )

    dp_config = client.resolve_dp_config(runtime=runtime)

    assert dp_config["parameters"]["clip_scope"] == "global"


@pytest.mark.parametrize("mechanism", DP_MECHANISMS)
def test_noise_scales_with_noise_multiplier(mechanism):
    """The noise is the multiplier times the sensitivity, so it must track the
    multiplier as well as the clip. Testing only the clip would still pass if
    the multiplier were dropped and the clipping norm used on its own."""
    client = load_client_module()

    std_at_low = measure_noise_std(
        client, mechanism, clipping_norm=1.0, noise_multiplier=0.25
    )
    std_at_high = measure_noise_std(
        client, mechanism, clipping_norm=1.0, noise_multiplier=1.0
    )

    assert std_at_low > 0.0
    assert std_at_high / std_at_low == pytest.approx(4.0, rel=0.05)


# ---------------------------------------------------------------------------
# Real-weight norm tests (BL-23 / issue #247)
# Functions live in cache_model_0/services/client.py and
# cache_model_0/services/model.py.
# ---------------------------------------------------------------------------

def load_model_module():
    model_path = (
        Path(__file__).resolve().parents[1] / "cache_model_0" / "services" / "model.py"
    )
    spec = spec_from_file_location("cache_model_0_model", model_path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _combined_norm(state_dict):
    """Global L2 norm across all floating tensors in a state_dict."""
    return math.sqrt(
        sum(
            torch.norm(v).item() ** 2
            for v in state_dict.values()
            if torch.is_tensor(v) and torch.is_floating_point(v)
        )
    )


def _build_and_train(num_epochs=3, num_batches=30, lr=0.01, seed=42):
    """Build the ModelArchitecture net and train briefly on synthetic
    MNIST-shaped data (28×28 pixels, 10 classes, batch_size=32).

    Uses manual gradient updates to avoid torch.optim dependencies that
    require optional packages (sympy) not present in all environments.
    Returns (reference_state_dict, trained_state_dict) — both detached.

    Measured norms (seed=42, 3 epochs × 30 batches × 32 samples):
      post-training combined L2 norm  ≈  8.21
      one-round delta L2 norm         ≈  0.18
    These numbers justify clipping_norm=10.0 for post_training_* mechanisms
    and confirm that clipping_norm=1.0 is safe for update_gaussian (delta well
    below 1.0 so no clipping occurs).
    """
    model_module = load_model_module()
    criterion = nn.CrossEntropyLoss()

    torch.manual_seed(seed)
    model = model_module.ModelArchitecture()
    ref_sd = {k: v.detach().clone() for k, v in model.state_dict().items()}

    torch.manual_seed(seed)
    for _ in range(num_epochs):
        for _ in range(num_batches):
            x = torch.randn(32, 1, 28, 28)
            y = torch.randint(0, 10, (32,))
            loss = criterion(model(x), y)
            loss.backward()
            with torch.no_grad():
                for p in model.parameters():
                    if p.grad is not None:
                        p -= lr * p.grad
                        p.grad.zero_()

    trained_sd = {k: v.detach().clone() for k, v in model.state_dict().items()}
    return ref_sd, trained_sd


def _load_manifest_dp():
    """Return a deep copy of the manifest's dp block with enabled=True for testing."""
    manifest_path = Path(__file__).resolve().parents[1] / "cache_model_0" / "manifest.json"
    dp = copy.deepcopy(json.loads(manifest_path.read_text())["dp"])
    dp["enabled"] = True
    return dp


def _load_test_dataset():
    """Load cache_model_0/dataset/test/test_dataset.pt without torchvision.

    Stubs the five torchvision classes referenced in the pickle so the raw
    tensors can be recovered without the torchvision package being installed
    (CI only installs torch).  Returns (x, y): x float32 (N, 1, 28, 28)
    normalised to [0, 1], y int64 (N,).
    """
    import sys
    import types

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
        ("torchvision",                           {}),
        ("torchvision.datasets",                  {}),
        ("torchvision.datasets.mnist",            {"MNIST": _MNIST}),
        ("torchvision.datasets.vision",           {"StandardTransform": _ST}),
        ("torchvision.transforms",                {}),
        ("torchvision.transforms.transforms",     {"Compose": _Compose, "ToTensor": _ToTensor, "Normalize": _Normalize}),
    ]
    added = {}
    for name, attrs in stub_specs:
        if name not in sys.modules:
            m = types.ModuleType(name)
            m.__path__ = []
            m.__package__ = name
            for attr, cls in attrs.items():
                setattr(m, attr, cls)
            sys.modules[name] = m
            added[name] = m

    try:
        dataset_path = (
            Path(__file__).resolve().parents[1]
            / "cache_model_0" / "dataset" / "test" / "test_dataset.pt"
        )
        obj = torch.load(dataset_path, weights_only=False)
        x = obj.data.float().unsqueeze(1) / 255.0
        y = obj.targets.clone()
        return x, y
    finally:
        for name in added:
            sys.modules.pop(name, None)


def _evaluate_accuracy(model_module, state_dict, x, y):
    """Return fraction of correct predictions (correct / total)."""
    m = model_module.ModelArchitecture()
    m.load_state_dict(state_dict)
    m.eval()
    with torch.no_grad():
        preds = m(x).argmax(dim=1)
    return (preds == y).float().mean().item()


def _build_and_train_reference(n_samples=2000, num_epochs=20, lr=0.01, seed=42):
    """Train on a seeded subset of cache_model_0/dataset/test/test_dataset.pt.

    Loads the committed MNIST test split (10 000 images), draws n_samples with
    a fixed seed, uses 80 % for training and 20 % for held-out evaluation.
    Returns (ref_sd, trained_sd, x_test, y_test).

    Measured (seed=42, n_samples=2000, 20 epochs, lr=0.01,
    from dataset/test/test_dataset.pt):
      post-training combined L2 norm  ≈  9.44
      one-round delta L2 norm         ≈  3.62
      baseline accuracy               ≈  0.86
    """
    model_module = load_model_module()
    criterion = nn.CrossEntropyLoss()

    x_all, y_all = _load_test_dataset()
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


def _prediction_agreement(model_module, sd_a, sd_b, x):
    """Fraction of inputs where sd_a and sd_b produce identical argmax predictions."""
    def _predict(sd):
        m = model_module.ModelArchitecture()
        m.load_state_dict(sd)
        m.eval()
        with torch.no_grad():
            return m(x).argmax(dim=1)
    return (_predict(sd_a) == _predict(sd_b)).float().mean().item()


def test_real_weights_combined_norm_fits_manifest_clipping_norm():
    """The manifest's clipping_norm must cover the model's real post-training
    combined L2 norm so that post_training_* mechanisms do not over-clip.

    With the old value of 1.0 the scale factor was ≈ 0.12 (88% of each
    weight discarded).  With 10.0 the trained model passes through unclipped.

    This test loads clipping_norm directly from cache_model_0/manifest.json.
    Reverting the manifest to clipping_norm=1.0 causes this test to fail,
    which is the regression it guards.
    """
    client = load_client_module()
    dp = _load_manifest_dp()
    manifest_clipping_norm = dp["parameters"]["clipping_norm"]
    clip_scope = dp["parameters"]["clip_scope"]

    _ref_sd, trained_sd = _build_and_train()
    pre_norm = _combined_norm(trained_sd)

    assert pre_norm < manifest_clipping_norm, (
        f"Combined L2 norm of trained weights ({pre_norm:.4f}) exceeds "
        f"manifest clipping_norm ({manifest_clipping_norm}). "
        "Raise clipping_norm in cache_model_0/manifest.json."
    )

    # Verify no over-clipping: clip at manifest value must leave norm unchanged.
    clipped_sd = client.clip_state_dict(trained_sd, manifest_clipping_norm, clip_scope)
    post_norm = _combined_norm(clipped_sd)

    assert post_norm == pytest.approx(pre_norm, rel=1e-4), (
        f"clip_state_dict with clipping_norm={manifest_clipping_norm} "
        f"scaled weights: pre={pre_norm:.4f}, post={post_norm:.4f}."
    )

    # Applying full dp_config (clip + noise at manifest parameters) must not
    # produce NaN or Inf in the output.
    torch.manual_seed(0)
    private_sd = client.apply_dp_mechanism(trained_sd, dp)
    for key, tensor in private_sd.items():
        if torch.is_tensor(tensor) and torch.is_floating_point(tensor):
            assert torch.isfinite(tensor).all(), f"Non-finite values in '{key}' after DP"


def test_clip_only_at_manifest_clipping_norm_preserves_model_outputs():
    """Clip-only at the manifest's clipping_norm must not degrade test accuracy
    (amendment No. 2-3 accuracy evidence, clip-only comparison).

    Trains on structured reference data (10 classes, linearly separable) and
    evaluates on a held-out labeled test split.  Since the trained combined
    norm (≈ 8.2) is below clipping_norm (10.0), clip_state_dict is a no-op
    and clip-only accuracy must match baseline accuracy exactly.

    With the old clipping_norm=1.0 the scale factor was ≈ 0.12 (88 % of each
    weight discarded), truncating the combined weight norm from ≈ 8.6 to 1.0.
    """
    client = load_client_module()
    model_module = load_model_module()
    dp = _load_manifest_dp()
    manifest_clipping_norm = dp["parameters"]["clipping_norm"]
    clip_scope = dp["parameters"]["clip_scope"]

    _ref_sd, trained_sd, x_test, y_test = _build_and_train_reference()

    baseline_acc = _evaluate_accuracy(model_module, trained_sd, x_test, y_test)
    assert baseline_acc > 0.85, (
        f"Reference training did not converge: baseline accuracy {baseline_acc:.3f}. "
        "Increase num_epochs in _build_and_train_reference."
    )

    clipped_sd = client.clip_state_dict(trained_sd, manifest_clipping_norm, clip_scope)
    clip_acc = _evaluate_accuracy(model_module, clipped_sd, x_test, y_test)

    assert clip_acc == pytest.approx(baseline_acc, abs=0.0), (
        f"Clip-only accuracy ({clip_acc:.3f}) differs from baseline ({baseline_acc:.3f}); "
        f"clipping_norm={manifest_clipping_norm} over-clips the trained model. "
        "The combined norm must be below clipping_norm."
    )

    print(
        f"\n[Clip accuracy report] baseline={baseline_acc:.3f}, "
        f"clip_only={clip_acc:.3f} (clipping_norm={manifest_clipping_norm})"
    )


def test_manifest_dp_full_noise_impact():
    """Documents the accuracy impact of the manifest's DP parameters
    (amendment No. 2-3 accuracy evidence, full-DP comparison).

    Trains on structured reference data and evaluates baseline, clip-only,
    and post-DP accuracy on a held-out labeled test split so the utility
    tradeoff is expressed as correct/total accuracy rather than prediction
    agreement between models.

    The manifest has dp.enabled=False; noise_multiplier=0.5 was chosen to
    keep σ=0.5 under the old clipping_norm=1.0 config.  At clipping_norm=10.0
    it gives σ=5.0 (noise_multiplier × clipping_norm), which dwarfs typical
    parameter magnitudes (≈ 0.025) and collapses accuracy to near-chance.

    Reducing noise_multiplier proportionally (to ~0.05) would restore σ≈0.5
    (noise_multiplier × clipping_norm); whether that preserves model utility
    is not evaluated here and requires a separate assessment.
    """
    client = load_client_module()
    model_module = load_model_module()
    dp = _load_manifest_dp()
    clipping_norm    = dp["parameters"]["clipping_norm"]
    noise_multiplier = dp["parameters"]["noise_multiplier"]
    noise_std        = noise_multiplier * clipping_norm

    _ref_sd, trained_sd, x_test, y_test = _build_and_train_reference()

    baseline_acc = _evaluate_accuracy(model_module, trained_sd, x_test, y_test)
    assert baseline_acc > 0.85, (
        f"Reference training did not converge: baseline accuracy {baseline_acc:.3f}."
    )

    clipped_sd = client.clip_state_dict(trained_sd, clipping_norm, dp["parameters"]["clip_scope"])
    clip_acc = _evaluate_accuracy(model_module, clipped_sd, x_test, y_test)

    torch.manual_seed(42)
    dp_sd = client.apply_dp_mechanism(trained_sd, dp)

    for key, tensor in dp_sd.items():
        if torch.is_tensor(tensor) and torch.is_floating_point(tensor):
            assert torch.isfinite(tensor).all(), f"Non-finite values in '{key}' after DP"

    dp_acc = _evaluate_accuracy(model_module, dp_sd, x_test, y_test)

    # With σ=5.0 (SNR ≪ 1) accuracy must drop well below baseline.
    assert dp_acc < baseline_acc - 0.3, (
        f"Expected σ={noise_std:.1f} to degrade accuracy by >30 pp, but "
        f"post-DP accuracy ({dp_acc:.3f}) is too close to baseline ({baseline_acc:.3f}). "
        "Review the manifest's noise_multiplier setting."
    )

    print(
        f"\n[DP accuracy report] noise_std={noise_std:.2f} "
        f"(noise_multiplier={noise_multiplier} × clipping_norm={clipping_norm}); "
        f"baseline={baseline_acc:.3f}, clip_only={clip_acc:.3f}, post_dp={dp_acc:.3f}"
    )


def test_update_gaussian_delta_norm_fits_clipping_norm_reference():
    """The one-round update delta for the reference model is measured using
    dataset/test/test_dataset.pt (seed=42, n_samples=2000, 20 epochs, lr=0.01).

    post_training_* clips absolute weights (combined norm ≈ 9.44, see
    test_real_weights_combined_norm_fits_manifest_clipping_norm) and needs
    clipping_norm ≥ 10.0.  update_gaussian clips the per-round delta; measured
    here as ≈ 3.62 for the reference training settings, so clipping_norm=4.0
    leaves the delta unclipped for that training configuration.

    The delta does not have to be below 1.0 — update_gaussian clips whatever
    delta the training produces.  The right clipping_norm depends on the
    training settings; this test documents the measured value for the reference
    configuration.
    """
    client = load_client_module()
    ref_sd, trained_sd, _x_test, _y_test = _build_and_train_reference()

    delta_norm = math.sqrt(
        sum(
            (trained_sd[k] - ref_sd[k]).norm().item() ** 2
            for k in trained_sd
            if torch.is_tensor(trained_sd[k]) and torch.is_floating_point(trained_sd[k])
        )
    )

    # Measured delta for the reference training is ≈ 3.62; verify the
    # calculation is stable to within 5 % across environments.
    assert delta_norm == pytest.approx(3.62, rel=0.05), (
        f"One-round delta norm ({delta_norm:.4f}) deviates from the expected "
        "≈ 3.62; re-run _build_and_train_reference and update this test."
    )

    # Verify that clipping at 4.0 leaves the delta intact (scale factor ≈ 1.0).
    clipped_delta_norm = _combined_norm(
        client.clip_state_dict(
            {k: trained_sd[k] - ref_sd[k] for k in trained_sd},
            4.0,
            "global",
        )
    )
    assert clipped_delta_norm == pytest.approx(delta_norm, rel=1e-4)


def test_update_laplace_binding_clipping_through_apply_dp_mechanism():
    """End-to-end through apply_dp_mechanism where the delta exceeds global L1 limit.

    Removing norm_type="l1" from the update_laplace branch would fall back to
    L2 clipping and leave a regression undetected by clip_state_dict-only tests.
    """
    client = load_client_module()
    torch = __import__("torch")

    reference_state_dict = {
        "w": torch.zeros(10),
        "b": torch.zeros(5),
        "counter": torch.tensor(7, dtype=torch.long),
    }
    # Large deltas per tensor so global L1 sum exceeds clipping_norm
    trained_state_dict = {
        "w": torch.ones(10) * 3.0,   # L1 contribution 30
        "b": torch.ones(5) * 2.0,    # L1 contribution 10
        "counter": torch.tensor(7, dtype=torch.long),
    }
    dp_config = {
        "enabled": True,
        "mechanism": "update_laplace",
        "parameters": {
            "clipping_norm": 10.0,
            "laplace_scale": 0.0,
            "clip_scope": "global",
        },
    }

    out = client.apply_dp_mechanism(trained_state_dict, dp_config, reference_state_dict=reference_state_dict)

    # Compute expected clipped delta with L1
    local_delta = client.compute_state_dict_delta(trained_state_dict, reference_state_dict)
    # L1 norms
    w_l1 = local_delta["w"].abs().sum().item()
    b_l1 = local_delta["b"].abs().sum().item()
    total_l1 = w_l1 + b_l1
    assert total_l1 > 10.0  # should trigger clipping

    scale = 10.0 / (total_l1 + 1e-12)
    expected_delta_w = local_delta["w"] * scale
    expected_delta_b = local_delta["b"] * scale
    expected_out_w = reference_state_dict["w"] + expected_delta_w
    expected_out_b = reference_state_dict["b"] + expected_delta_b

    torch.testing.assert_close(out["w"], expected_out_w)
    torch.testing.assert_close(out["b"], expected_out_b)
    # Integer buffer preserved
    assert out["counter"].item() == 7
    assert out["counter"].dtype == torch.long
