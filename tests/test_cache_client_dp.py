from collections import OrderedDict
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

try:
    import torch
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
]


def build_small_state_dict(num_elements=20000):
    """Build a state_dict whose L2 norm sits well inside every clipping norm
    used below, so clipping is a no-op and the only difference between input
    and output is the noise itself."""
    return OrderedDict(
        {
            "weight": torch.full((num_elements,), 1e-3, dtype=torch.float32),
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
def test_noise_is_zero_when_clipping_norm_is_zero(mechanism):
    """A non-positive `clipping_norm` disables clipping, which leaves no
    sensitivity bound for the noise to be calibrated against. The scaled noise
    is zero there, so the mechanism is a documented no-op rather than a silent
    privacy claim over unclipped weights."""
    client = load_client_module()

    assert measure_noise_std(client, mechanism, clipping_norm=0.0) == 0.0


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
