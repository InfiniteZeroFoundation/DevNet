"""Client-side local training service for the DevNet reference model.

This module is loaded dynamically by `dincli` for the manifest entry
`train_client_model`. The function exposed at the bottom of
the file is responsible for:

1. Fetching the genesis or latest global model from mount
2. Loading the client dataset from the cache directory.
3. Training a local model for the current round.
4. Optionally applying a manifest-selected differential privacy mechanism.
5. Generate the local model

The DP helpers are deliberately kept framework-light and pure PyTorch so the
service can run without extra privacy libraries such as Opacus. The current
mechanisms are post-training mechanisms rather than full DP-SGD; that makes the
service easier to ship in DevNet, but it also means the privacy guarantees are
more limited than a production privacy stack.
"""

import os
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from rich.console import Console
from torch.utils.data import DataLoader
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# The genesis model file stores the serialized model object. Importing the class
# here ensures `torch.load(...)` can resolve that symbol when deserializing.
from model import ModelArchitecture  # noqa: F401

console = Console()

# The service currently supports three manifest-selectable DP mechanisms:
# - post_training_gaussian: perturb final weights directly with Gaussian noise
# - post_training_laplace: perturb final weights directly with Laplace noise
# - update_gaussian: perturb the local model delta, then reconstruct weights
SUPPORTED_DP_MECHANISMS = {
    "post_training_gaussian",
    "post_training_laplace",
    "update_gaussian",
}

# These aliases keep the manifest ergonomic while mapping everything back to a
# small canonical set of mechanism names.
DP_MECHANISM_ALIASES = {
    "gaussian": "post_training_gaussian",
    "post-training-gaussian": "post_training_gaussian",
    "laplace": "post_training_laplace",
    "post-training-laplace": "post_training_laplace",
    "update": "update_gaussian",
    "update-gaussian": "update_gaussian",
}

# Several common disabled spellings are normalized to keep the main training
# path simple.
DISABLED_DP_MODES = {"disabled", "none", "off", "false"}


def add_gaussian_noise(weights, sigma):
    """Return a copy of `weights` with zero-mean Gaussian noise applied.

    `sigma` is used directly as the standard deviation of the sampled tensor.
    A non-positive value intentionally becomes a no-op so manifests can disable
    noise without needing a separate code path.
    """

    if sigma <= 0:
        return weights.detach().clone()
    return weights + (torch.randn_like(weights) * sigma)


def add_laplace_noise(weights, scale):
    """Return a copy of `weights` with Laplace noise applied.

    The implementation uses inverse-CDF sampling from uniform noise because
    that keeps the helper self-contained and avoids depending on a separate
    distribution object.
    """

    if scale <= 0:
        return weights.detach().clone()

    # Sample from U(-0.5, 0.5) and transform it into Laplace noise.
    uniform = torch.rand_like(weights) - 0.5
    noise = -scale * torch.sign(uniform) * torch.log1p(-2 * torch.abs(uniform))
    return weights + noise


def clip_weights(weights, clipping_norm):
    """Clip a tensor to an L2 norm bound and return the clipped copy.

    This helper is used for per-layer clipping. If the tensor already fits
    inside the clipping radius, it is simply cloned and returned unchanged.
    """

    if clipping_norm <= 0:
        return weights.detach().clone()

    norm = torch.norm(weights)
    if not torch.isfinite(norm) or norm <= clipping_norm:
        return weights.detach().clone()

    scale = clipping_norm / (norm + 1e-12)
    return weights * scale


def clone_state_dict(state_dict):
    """Deep-clone a state_dict while preserving its concrete mapping type.

    That matters because PyTorch commonly uses `OrderedDict` for state_dicts,
    and preserving that structure avoids surprising downstream behavior.
    """

    cloned_state_dict = state_dict.__class__()
    for key, value in state_dict.items():
        if torch.is_tensor(value):
            cloned_state_dict[key] = value.detach().clone()
        else:
            cloned_state_dict[key] = value
    return cloned_state_dict


def clip_state_dict(state_dict, clipping_norm, clip_scope="per_layer"):
    """Clip all floating tensors in a state_dict.

    `clip_scope` controls whether clipping happens:
    - per_layer: each floating tensor is clipped independently.
    - global: one shared scale factor is computed across all floating tensors.

    Non-floating tensors such as counters or integer buffers are copied through
    unchanged because noise/clipping semantics for them would be ill-defined.
    """

    if clipping_norm <= 0:
        return clone_state_dict(state_dict)

    clipped_state_dict = state_dict.__class__()
    float_items = [
        (key, value)
        for key, value in state_dict.items()
        if torch.is_tensor(value) and torch.is_floating_point(value)
    ]

    if clip_scope == "global" and float_items:
        # Compute one global L2 norm across all floating tensors, then scale
        # every floating tensor by the same factor.
        global_norm_sq = sum(torch.norm(value).item() ** 2 for _, value in float_items)
        global_norm = global_norm_sq ** 0.5
        scale = min(1.0, clipping_norm / (global_norm + 1e-12))

        for key, value in state_dict.items():
            if torch.is_tensor(value):
                clipped_state_dict[key] = value.detach().clone()
                if torch.is_floating_point(value):
                    clipped_state_dict[key] = value * scale
            else:
                clipped_state_dict[key] = value
        return clipped_state_dict

    # Default path: clip each floating tensor independently.
    for key, value in state_dict.items():
        if torch.is_tensor(value):
            if torch.is_floating_point(value):
                clipped_state_dict[key] = clip_weights(value, clipping_norm)
            else:
                clipped_state_dict[key] = value.detach().clone()
        else:
            clipped_state_dict[key] = value
    return clipped_state_dict


def add_noise_to_state_dict(state_dict, noise_kind, noise_scale):
    """Apply the requested noise distribution to every floating tensor.

    This helper centralizes tensor traversal so the mechanism-specific logic can
    focus on *what* is being privatized rather than *how* every tensor is
    visited.
    """

    noisy_state_dict = state_dict.__class__()

    for key, value in state_dict.items():
        if torch.is_tensor(value):
            if not torch.is_floating_point(value):
                noisy_state_dict[key] = value.detach().clone()
                continue

            if noise_kind == "gaussian":
                noisy_state_dict[key] = add_gaussian_noise(value, noise_scale)
            elif noise_kind == "laplace":
                noisy_state_dict[key] = add_laplace_noise(value, noise_scale)
            else:
                raise ValueError(f"Unsupported noise kind: {noise_kind}")
        else:
            noisy_state_dict[key] = value

    return noisy_state_dict


def compute_state_dict_delta(trained_state_dict, reference_state_dict):
    """Compute the floating-point delta between trained and reference weights.

    This is the core primitive for `update_gaussian`. We perturb the update
    rather than the final weights, then reconstruct a full state_dict afterward
    because the existing aggregator expects complete model weights.
    """

    delta_state_dict = trained_state_dict.__class__()

    for key, value in trained_state_dict.items():
        if torch.is_tensor(value):
            if torch.is_floating_point(value):
                delta_state_dict[key] = value - reference_state_dict[key]
            else:
                delta_state_dict[key] = value.detach().clone()
        else:
            delta_state_dict[key] = value

    return delta_state_dict


def reconstruct_state_dict_from_delta(reference_state_dict, delta_state_dict, trained_state_dict):
    """Rebuild a full state_dict by adding a privatized delta to a reference.

    Non-floating tensors are copied from the trained model because they are not
    part of the additive DP update path.
    """

    reconstructed_state_dict = trained_state_dict.__class__()

    for key, value in trained_state_dict.items():
        if torch.is_tensor(value):
            if torch.is_floating_point(value):
                reconstructed_state_dict[key] = reference_state_dict[key] + delta_state_dict[key]
            else:
                reconstructed_state_dict[key] = value.detach().clone()
        else:
            reconstructed_state_dict[key] = value

    return reconstructed_state_dict


def normalize_dp_mode(dp_mode):
    """Normalize the DP mode read from the nested manifest block."""

    if dp_mode is None:
        return "disabled"

    normalized_mode = str(dp_mode).strip()
    normalized_mode_lower = normalized_mode.lower()
    if normalized_mode_lower in DISABLED_DP_MODES:
        return "disabled"
    if normalized_mode_lower in {"aftertraining", "after_training"}:
        return "afterTraining"
    return normalized_mode


def normalize_dp_mechanism(dp_mechanism):
    """Map short mechanism names to the canonical manifest names."""

    normalized_mechanism = str(dp_mechanism).strip().lower()
    return DP_MECHANISM_ALIASES.get(normalized_mechanism, normalized_mechanism)


def resolve_dp_config(runtime=None):
    """Resolve DP configuration from the service runtime manifest.

    The preferred manifest schema is a nested `dp` object:

    {
        "dp": {
            "enabled": true,
            "mode": "afterTraining",
            "mechanism": "post_training_gaussian",
            "parameters": {...}
        }
    }
    """

    manifest_dp = runtime.get_manifest_key("dp", {}) if runtime is not None else {}
    manifest_dp = manifest_dp or {}

    if not manifest_dp:
        return {
            "enabled": False,
            "mode": "disabled",
            "mechanism": "none",
            "parameters": {},
        }

    nested_mode = manifest_dp.get("mode", "disabled")
    normalized_mode = normalize_dp_mode(nested_mode)

    enabled = manifest_dp.get("enabled")
    if enabled is True and normalized_mode == "disabled":
        normalized_mode = "afterTraining"

    # If the nested block explicitly disables DP, or the resolved mode is a
    # disabled spelling, return a compact disabled config immediately.
    if enabled is False or normalized_mode == "disabled":
        return {
            "enabled": False,
            "mode": "disabled",
            "mechanism": "none",
            "parameters": {},
        }

    dp_mechanism = manifest_dp.get("mechanism", "post_training_gaussian")
    dp_mechanism = normalize_dp_mechanism(dp_mechanism)

    if dp_mechanism not in SUPPORTED_DP_MECHANISMS:
        supported = ", ".join(sorted(SUPPORTED_DP_MECHANISMS))
        raise ValueError(f"Unsupported DP mechanism '{dp_mechanism}'. Supported mechanisms: {supported}")

    parameters = dict(manifest_dp.get("parameters", {}))

    parameters.setdefault("clipping_norm", 1.0)
    parameters.setdefault("noise_multiplier", 0.5)
    parameters.setdefault("laplace_scale", parameters["noise_multiplier"])
    parameters.setdefault("clip_scope", "per_layer")

    return {
        "enabled": True,
        "mode": normalized_mode if normalized_mode != "disabled" else "afterTraining",
        "mechanism": dp_mechanism,
        "parameters": parameters,
    }


def apply_dp_mechanism(trained_state_dict, dp_config, reference_state_dict=None):
    """Apply the configured DP mechanism to the trained model state.

    Mechanism summary:
    - post_training_gaussian: clip final weights, then add Gaussian noise.
    - post_training_laplace: clip final weights, then add Laplace noise.
    - update_gaussian: clip the local delta, add Gaussian noise to that delta,
      then reconstruct a full weight file from the privatized update.
    """

    mechanism = dp_config["mechanism"]
    params = dp_config["parameters"]
    clipping_norm = float(params.get("clipping_norm", 1.0))
    clip_scope = str(params.get("clip_scope", "per_layer")).strip().lower()

    if clip_scope not in {"per_layer", "global"}:
        raise ValueError("clip_scope must be either 'per_layer' or 'global'")

    if mechanism == "post_training_gaussian":
        clipped_state_dict = clip_state_dict(trained_state_dict, clipping_norm, clip_scope)
        return add_noise_to_state_dict(
            clipped_state_dict,
            noise_kind="gaussian",
            noise_scale=float(params.get("noise_multiplier", 0.5)),
        )

    if mechanism == "post_training_laplace":
        clipped_state_dict = clip_state_dict(trained_state_dict, clipping_norm, clip_scope)
        return add_noise_to_state_dict(
            clipped_state_dict,
            noise_kind="laplace",
            noise_scale=float(params.get("laplace_scale", params.get("noise_multiplier", 0.5))),
        )

    if mechanism == "update_gaussian":
        if reference_state_dict is None:
            raise ValueError("update_gaussian requires a reference_state_dict")

        # Compute the client update relative to the model the client started
        # from, then privatize that update before reconstructing full weights.
        local_delta = compute_state_dict_delta(trained_state_dict, reference_state_dict)
        clipped_delta = clip_state_dict(local_delta, clipping_norm, clip_scope)
        noisy_delta = add_noise_to_state_dict(
            clipped_delta,
            noise_kind="gaussian",
            noise_scale=float(params.get("noise_multiplier", 0.5)),
        )
        return reconstruct_state_dict_from_delta(reference_state_dict, noisy_delta, trained_state_dict)

    raise ValueError(f"Unsupported DP mechanism '{mechanism}'")


def train_client_model(
    genesis_model_ipfs_hash,
    account_address,
    effective_network="local",
    initial_model_ipfs_hash=None,
    model_base_dir="",
    gi=None,
    runtime=None,
):
    """Train a client model for the current round and upload the result to IPFS.

    The service expects `dincli` to pass a `runtime` object that already knows
    the active manifest. DP configuration is therefore resolved at runtime from
    the manifest rather than being hardcoded into the service.
    """

    # Normalize the incoming model directory and resolve the effective privacy
    # configuration before doing any I/O.
    model_base_dir = Path(model_base_dir)
    dp_config = resolve_dp_config(runtime=runtime)

    genesis_model_path = model_base_dir / "models" / "genesis_model.pth"
    if not genesis_model_path.exists():
        raise FileNotFoundError(f"Genesis model not found at {genesis_model_path}")

    

    # Load the serialized model object, not just a raw state_dict. This matches
    # the existing DevNet model-owner flow where the genesis artifact is saved
    # as a full model object.

    model_architecture = ModelArchitecture()

    genesis_model = torch.load(model_base_dir / "models" / "genesis_model.pth", weights_only=False)
    model_architecture.load_state_dict(genesis_model.state_dict())

    console.print(
        "Genesis model with IPFS hash "
        + genesis_model_ipfs_hash
        + " loaded from path :  "
        + str(model_base_dir / "models" / "genesis_model.pth")
    )

    # Each client owns a dedicated dataset file keyed by wallet address.
    client_dataset_path = model_base_dir / "dataset" / "clients" / account_address / "data.pt"
    if not client_dataset_path.exists():
        raise Exception("Client dataset not found at " + str(client_dataset_path))

    client_dataset = torch.load(client_dataset_path, weights_only=False)
    console.print("Client dataset loaded from path :  " + str(client_dataset_path))

    # Start from the latest known global model when available; otherwise train
    # directly from the genesis model.
    starting_model_label = "genesis model"
    if initial_model_ipfs_hash:
        initial_model_path = model_base_dir / "models" / f"gm_{gi-1}.pt"
        if not initial_model_path.exists():
            raise FileNotFoundError(f"Initial global model not found at {initial_model_path}")
        model_architecture.load_state_dict(
            torch.load(initial_model_path, weights_only=True)
        )
        starting_model_label = "initial global model"
        console.print("Initial model loaded and weights initialized from GM")

    # Capture the exact starting point before local optimization so
    # `update_gaussian` can privatize the model delta relative to this state.
    reference_state_dict = clone_state_dict(model_architecture.state_dict())

    # Standard local training setup for the reference MNIST model.
    batch_size = 32
    data_loader = DataLoader(client_dataset, batch_size=batch_size, shuffle=True)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model_architecture.parameters(), lr=0.001)

    # Local training is intentionally simple in this reference service. The DP
    # mechanisms in this file operate after training rather than at each step.
    num_local_epochs = 10
    for _ in range(num_local_epochs):
        for inputs, labels in data_loader:
            optimizer.zero_grad()
            outputs = model_architecture(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

    # Persist the raw, non-private model first. This makes debugging easier and
    # preserves the existing file layout even when a DP mechanism is enabled.
    client_model_dir = model_base_dir / "models" / "clients" / account_address
    client_model_dir.mkdir(parents=True, exist_ok=True)

    raw_model_path = client_model_dir / f"lm_{gi}.pth"
    torch.save(model_architecture.state_dict(), raw_model_path)
    console.print(f"Client {account_address} model trained successfully at path :  {raw_model_path}")

    # If DP is disabled, the raw locally trained weights are the submission
    # artifact and we can upload them immediately.
    if not dp_config["enabled"]:
        return str(raw_model_path)

    # The current DevNet implementation only supports post-training privacy
    # application. Anything else should fail loudly rather than silently ignore
    # the manifest.
    if dp_config["mode"] != "afterTraining":
        raise ValueError(f"Unsupported DP mode '{dp_config['mode']}' for client training")

    console.print(
        "Applying DP mechanism "
        f"{dp_config['mechanism']} with parameters {dp_config['parameters']} "
        f"using {starting_model_label} as the reference."
    )

    # Produce a private state_dict according to the chosen mechanism.
    private_state_dict = apply_dp_mechanism(
        model_architecture.state_dict(),
        dp_config,
        reference_state_dict=reference_state_dict,
    )

    # Store the private artifact under a mechanism-specific name so operators
    # can tell which privacy strategy was used for a given client output.
    private_model_path = client_model_dir / f"lm_{gi}_{dp_config['mechanism']}.pth"
    torch.save(private_state_dict, private_model_path)
    console.print(
        f"Private client model ({dp_config['mechanism']}) saved successfully at path :  {private_model_path}"
    )

    # Upload the private artifact, not the raw one.
    return str(private_model_path)
