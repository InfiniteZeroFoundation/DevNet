from collections import OrderedDict
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")


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
