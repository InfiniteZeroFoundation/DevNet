# Client Service

Technical documentation for the DevNet reference client service at [cache_model_0/services/client.py](/home/azureuser/projects/devnet/cache_model_0/services/client.py).

## Overview

The client service is responsible for producing a local model submission for one client and one global iteration.

Its job is to:

1. read the active manifest through the injected runtime context;
2. download the correct starting model from IPFS;
3. load the client dataset from the local cache;
4. run local training;
5. optionally apply a manifest-selected differential privacy mechanism;
6. upload the resulting `state_dict` to IPFS.

The public entrypoint is:

```python
train_client_model_and_upload_to_ipfs(
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

- CLI entrypoint: [dincli/cli/client.py](/home/azureuser/projects/devnet/dincli/cli/client.py)
- Runtime builder: [dincli/services/runtime.py](/home/azureuser/projects/devnet/dincli/services/runtime.py)
- Manifest service entry: [cache_model_0/manifest.json](/home/azureuser/projects/devnet/cache_model_0/manifest.json)

Flow summary:

1. `dincli client train-lms` builds a `ServiceRuntimeContext`.
2. The runtime loads the model manifest once.
3. `dincli` resolves the custom client service path from the manifest.
4. `dincli` loads `train_client_model_and_upload_to_ipfs(...)`.
5. The runtime object is injected into that function.
6. The service reads manifest keys through `runtime.get_manifest_key(...)`.

## Inputs And Local Files

### Required runtime inputs

| Input | Purpose |
|---|---|
| `genesis_model_ipfs_hash` | CID of the genesis model object |
| `account_address` | client wallet address; also used to locate the dataset |
| `effective_network` | selects the cache namespace |
| `initial_model_ipfs_hash` | latest global model CID for rounds after GI 1 |
| `gi` | global iteration index |
| `runtime` | manifest-aware context provided by `dincli` |

### Expected local file layout

The service reads and writes under:

```text
<CACHE_DIR>/<network>/model_<model_id>/
```

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

1. fetch genesis model from IPFS;
2. deserialize the model object;
3. optionally load the latest global model weights into that model;
4. keep a clone of the starting state for update-based privacy;
5. train with a `DataLoader`, `CrossEntropyLoss`, and `Adam`;
6. save raw local weights;
7. if DP is enabled, create a separate private artifact and upload that instead.

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

### `post_training_gaussian`

Behavior:

1. clip floating tensors in the final trained state;
2. add Gaussian noise tensor-by-tensor;
3. save and upload the resulting private `state_dict`.

Use when:

- you want the simplest post-training baseline;
- aggregator compatibility matters more than strong privacy guarantees.

### `post_training_laplace`

Behavior:

1. clip floating tensors in the final trained state;
2. add Laplace noise tensor-by-tensor;
3. save and upload the resulting private `state_dict`.

Use when:

- you want a non-Gaussian noise option for experiments;
- you want the same deployment shape as the Gaussian path.

### `update_gaussian`

Behavior:

1. compute the local update relative to the starting model for the round;
2. clip that delta;
3. add Gaussian noise to the delta;
4. reconstruct a full weight file from `reference + noisy_delta`;
5. upload the reconstructed private `state_dict`.

Why this matters:

- it is closer to the federated-learning concept of privatizing an update rather than raw final weights;
- it still preserves compatibility with the current aggregator, which expects full model weights rather than deltas.

## Clipping Behavior

The service supports two clipping scopes:

- `per_layer`: each floating tensor is clipped independently.
- `global`: one combined L2 norm is computed across all floating tensors and one shared scale factor is applied.

Only floating tensors are clipped/noised. Integer buffers or counters are copied through unchanged.

## Output Contract

Regardless of mechanism, the service uploads a PyTorch `state_dict`, not a custom delta payload.

That constraint is important because the current aggregator in [cache_model_0/services/aggregator.py](/home/azureuser/projects/devnet/cache_model_0/services/aggregator.py) averages full state dictionaries.

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

- client implementation: [cache_model_0/services/client.py](/home/azureuser/projects/devnet/cache_model_0/services/client.py)
- runtime manifest access: [dincli/services/runtime.py](/home/azureuser/projects/devnet/dincli/services/runtime.py)
- CLI invocation path: [dincli/cli/client.py](/home/azureuser/projects/devnet/dincli/cli/client.py)
- sample manifest: [cache_model_0/manifest.json](/home/azureuser/projects/devnet/cache_model_0/manifest.json)
- DP issue/design notes: [Developer/issues/DifferentialPrivacy.md](/home/azureuser/projects/devnet/Developer/issues/DifferentialPrivacy.md)

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
