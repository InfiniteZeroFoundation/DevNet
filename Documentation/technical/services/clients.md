# Client Service

Technical documentation for the DevNet reference client service at [cache_model_0/services/client.py](../../../cache_model_0/services/client.py).

## Overview

The client service trains and saves a local model artifact for one client and one global iteration. `dincli client train-lms` prepares inputs and runs this service in a worker container; the separate `dincli client submit-lm` command uploads the saved artifact to IPFS and submits its CID on-chain.

Its job is to:

1. read the active manifest through the injected runtime context;
2. load the starting model from files staged by the host CLI;
3. load the client dataset from the local cache;
4. run local training;
5. optionally apply a manifest-selected differential privacy mechanism;
6. save the resulting `state_dict` locally and return its file path.

The public entrypoint is:

```python
train_client_model(
    genesis_model_ipfs_hash,
    account_address,
    effective_network="local",
    initial_model_ipfs_hash=None,
    model_base_dir="",
    gi=None,
    runtime=None,
)
```

## Invocation Path

The service is normally invoked by `dincli`, not by importing it directly.

Relevant call path:

- CLI entrypoint: [dincli/cli/client.py](../../../dincli/cli/client.py)
- Runtime builder: [dincli/services/runtime.py](../../../dincli/services/runtime.py)
- Manifest service entry: [cache_model_0/manifest.json](../../../cache_model_0/manifest.json)

Flow summary:

1. `dincli client train-lms <model_id>` builds a host-side `ServiceRuntimeContext` and reads the model manifest.
2. The CLI resolves the `train_client_model` service entry and stages the service, model architecture, genesis model, and (when available after GI 1) latest global model from IPFS in the host cache.
3. The CLI creates a worker job naming `train_client_model` and starts a container with the model cache mounted at `/din/model`.
4. The [worker runner](../../../dincli/docker/worker/worker.py) loads the mounted manifest and service, then injects a `WorkerRuntime` into `train_client_model(...)`. This runtime exposes manifest access through `runtime.get_manifest_key(...)`.
5. The service reads the mounted inputs, trains, saves raw weights and optionally a separate private artifact, and returns the selected artifact's path as a string.
6. The worker writes that path in `result.json` with `status: "ok"`. The host CLI checks the result, maps the `/din/model/...` path back to its model cache, and prints the local path.
7. A separate `dincli client submit-lm <model_id>` resolves the local artifact using the manifest's DP configuration, uploads it to IPFS, and sends its CID and GI to the task auditor's `submitLocalModel(...)` function.

Run the commands in order for the same model and client wallet:

```bash
dincli client train-lms <model_id>
dincli client submit-lm <model_id>
```

Both commands accept `--gi <gi_index>`; training requires the current GI, while submission defaults to the current GI and also accepts an earlier GI. The transaction must still satisfy the contract's submission rules. Training finishes with a local file; upload and on-chain submission happen only when `submit-lm` runs.

## Inputs And Local Files

### Required runtime inputs

| Input | Purpose |
|---|---|
| `genesis_model_ipfs_hash` | identifies the genesis model object staged by the host CLI |
| `account_address` | client wallet address; also used to locate the dataset |
| `effective_network` | network name passed by the CLI; local file paths use `model_base_dir` |
| `initial_model_ipfs_hash` | when present after GI 1, selects the host-staged latest global model weights |
| `model_base_dir` | root of staged inputs and local outputs; `/din/model` in the worker |
| `gi` | global iteration index |
| `runtime` | manifest-aware `WorkerRuntime` injected by the worker runner |

### Expected local file layout

The host model cache is rooted at:

```text
<CACHE_DIR>/<network>/model_<model_id>/
```

The worker sees this directory as `/din/model`. The model directory is mounted read-only, with the client's model output subdirectory mounted read-write. Paths below are relative to that root.

Important paths:

| Path | Purpose |
|---|---|
| `models/genesis_model.pth` | cached serialized genesis model object |
| `models/gm_<gi-1>.pt` | cached latest global model weights |
| `dataset/clients/<account_address>/data.pt` | client training dataset |
| `models/clients/<account_address>/lm_<gi>.pth` | raw local model weights |
| `models/clients/<account_address>/lm_<gi>_<mechanism>.pth` | private local model weights |

## Training Flow

The service training path is intentionally simple:

1. read the host-staged genesis model from the mounted cache;
2. deserialize the model object;
3. optionally load the latest global model weights into that model;
4. keep a clone of the starting state for update-based privacy;
5. train with a `DataLoader`, `CrossEntropyLoss`, and `Adam`;
6. save raw local weights;
7. if DP is enabled, save a separate private artifact and return its path; otherwise return the raw weights path.

The current implementation applies privacy after local training. It does not implement DP-SGD or per-step privacy accounting.

## Manifest-Driven DP Configuration

The service reads DP configuration from the nested `dp` object in the manifest.

Example:

```json
{
  "dp": {
    "enabled": true,
    "mode": "afterTraining",
    "mechanism": "update_gaussian",
    "parameters": {
      "clipping_norm": 1.0,
      "noise_multiplier": 0.5,
      "laplace_scale": 0.35,
      "clip_scope": "global"
    }
  }
}
```

Resolution rules:

- `dp.enabled: false` disables privacy;
- if the `dp` block is absent, privacy is treated as disabled;
- unsupported mechanisms raise an error instead of silently falling back.

## Supported DP Mechanisms

### `post_training_gaussian` — experimental, no formal privacy guarantee

Behavior:

1. clip floating tensors in the final trained state;
2. add Gaussian noise tensor-by-tensor;
3. save the resulting private `state_dict` locally.

**Experimental baseline (issue #279, dp-mechanism-review.md F5):** this clips
*absolute trained weights*, not the per-client *update*, so it does not bound
the quantity an attacker observing successive rounds actually cares about.
`resolve_dp_config` logs a warning whenever this mechanism is selected.
`update_gaussian` is the mechanism with a defined sensitivity bound.

Use when:

- you want the simplest post-training baseline for experimentation;
- aggregator compatibility matters more than a privacy guarantee.

### `post_training_laplace` — experimental, no formal privacy guarantee

Behavior:

1. clip floating tensors in the final trained state;
2. add Laplace noise tensor-by-tensor;
3. save the resulting private `state_dict` locally.

**Experimental baseline (issue #279, dp-mechanism-review.md F4/F5):** same
weight-vs-update gap as `post_training_gaussian` above, plus its noise is
sized against the L2 `clipping_norm` while the Laplace mechanism's guarantee
is normally calibrated against L1 sensitivity — for model weights the gap
between the two can be as large as √d (d = parameter count). Neither gap is
fixed here; `resolve_dp_config` logs a warning whenever this mechanism is
selected.

Use when:

- you want a non-Gaussian noise option for experimentation;
- you want the same deployment shape as the Gaussian path.

### `update_gaussian`

Behavior:

1. compute the local update relative to the starting model for the round;
2. clip that delta;
3. add Gaussian noise to the delta;
4. reconstruct a full weight file from `reference + noisy_delta`;
5. save the reconstructed private `state_dict` locally.

Why this matters:

- it is closer to the federated-learning concept of privatizing an update rather than raw final weights;
- it still preserves compatibility with the current aggregator, which expects full model weights rather than deltas.

## Clipping Behavior

The service supports two clipping scopes:

- `global` (default): one combined L2 norm is computed across all floating tensors and one shared scale factor is applied.
- `per_layer`: each floating tensor is clipped independently.

`global` is the default because it is the only scope whose clip bounds the
whole update at `clipping_norm`. Clipping `n` tensors independently to
`clipping_norm` bounds the combined L2 norm at `clipping_norm * sqrt(n)`, so
under `per_layer` the quantity the noise is calibrated against grows with model
depth. `per_layer` remains available for utility, but it carries no formal
sensitivity bound and should be treated as experimental.

## Configuration Validation

`clipping_norm` must be greater than zero whenever DP is enabled. A
non-positive value used to disable clipping while noise still got applied,
which produced noise with nothing bounding the quantity it was meant to hide.
Both `resolve_dp_config` and `apply_dp_mechanism` now reject it, so a
hand-built config cannot bypass the manifest-level check.

`post_training_laplace` requires an explicit `laplace_scale`. It previously
defaulted to whatever `noise_multiplier` was set to, which silently produced a
scale nobody chose, since the two parameters carry different units and are
calibrated differently.

**DP is off by default.** With no `dp` block, or `dp.enabled: false`, the
service returns the raw trained weights path; `submit-lm` uploads that file.
That is a deliberate devnet default, not an oversight, but it means the absence of configuration is the absence of privacy.

## Noise Calibration

The noise scale is `noise_multiplier * clipping_norm`, not `noise_multiplier`
on its own. The clipping norm is the sensitivity these mechanisms bound, and
the multiplier scales that sensitivity, which is the form privacy accounting
libraries expect.

The practical consequence is that `clipping_norm` and the noise level move
together. Loosening the clip widens the sensitivity and widens the noise to
match, instead of leaving the noise fixed while the privacy level silently
changes.

`laplace_scale` is scaled the same way. Note that Laplace noise calibrated
against an L2 clip is a known mismatch, since the Laplace mechanism is
normally calibrated against an L1 sensitivity — see `post_training_laplace`
above and [issue #279](https://github.com/InfiniteZeroFoundation/DevNet/issues/279).

Only floating tensors are clipped/noised. Integer buffers or counters are copied through unchanged.

## Output Contract

Regardless of mechanism, the service saves a PyTorch `state_dict`, not a custom delta payload, and returns its local file path as a string:

- DP disabled: `models/clients/<account_address>/lm_<gi>.pth`;
- DP enabled: `models/clients/<account_address>/lm_<gi>_<mechanism>.pth`.

These paths are under `model_base_dir` (`/din/model` in the worker). With DP enabled, the raw file remains local and the returned path points to the separate private file. `submit-lm` independently selects the file according to the manifest's DP configuration, so keep that configuration consistent between training and submission.

That constraint is important because the current aggregator in [cache_model_0/services/aggregator.py](../../../cache_model_0/services/aggregator.py) averages full state dictionaries.

This means:

- no aggregator contract change is needed for the current DP modes;
- `update_gaussian` reconstructs full weights locally before upload.

## Limitations

Current limitations of the service:

- privacy is applied only after training;
- no epsilon/delta accountant is emitted;
- no per-sample gradient clipping;
- no DP-SGD integration;
- no secure aggregation coupling;
- no round-by-round privacy budget tracking.

## Sources And Lineage

Primary local sources:

- client implementation: [cache_model_0/services/client.py](../../../cache_model_0/services/client.py)
- runtime manifest access: [dincli/services/runtime.py](../../../dincli/services/runtime.py)
- CLI invocation path: [dincli/cli/client.py](../../../dincli/cli/client.py)
- sample manifest: [cache_model_0/manifest.json](../../../cache_model_0/manifest.json)
- DP issue/design notes: [Developer/issues/DifferentialPrivacy.md](../../../Developer/issues/DifferentialPrivacy.md)

Related research and reference repositories:

- Threshold KNN-Shapley paper: <https://arxiv.org/abs/2308.15709>
- TKNN-Shapley local checkout: [README.md](https://github.com/Jiachen-T-Wang/TKNN-Shapley/blob/main/README.md)
- TKNN-Shapley privacy helpers: [helper_privacy.py](https://github.com/Jiachen-T-Wang/TKNN-Shapley/blob/main/helper_privacy.py)
- TKNN-Shapley accounting logic: [helper_knn.py](https://github.com/Jiachen-T-Wang/TKNN-Shapley/blob/main/helper_knn.py)
- Datascope upstream repo: <https://github.com/easeml/datascope>
- Awesome Data Valuation upstream repo: <https://github.com/daviddao/awesome-data-valuation>

Important note:

- the current DevNet client service was implemented directly in this repository;
- the data-valuation repositories and the TKNN-Shapley paper informed future DP-aware scoring and accounting directions;
- the present client code does not directly vendor or paste their implementation into `client.py`.
