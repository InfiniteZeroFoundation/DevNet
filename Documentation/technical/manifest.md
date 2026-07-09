# Manifest

Technical documentation for the DevNet model manifest, with emphasis on how `dincli` resolves it at runtime and how services consume it.

## Overview

The manifest is the single JSON document that ties a model deployment together.

It carries:

- task metadata;
- contract addresses;
- service file locations and IPFS CIDs;
- optional guides and per-role requirements files;
- model-specific configuration such as differential privacy parameters.

In the DevNet flow, the manifest is not just static metadata. It is also runtime configuration for dynamically loaded services.

## Canonical Example

The current reference manifest is:

- [cache_model_0/manifest.json](/home/azureuser/projects/devnet/cache_model_0/manifest.json)

That file is the best concrete example of the fields the current services expect.

## Runtime Resolution Path

The main manifest-loading path is:

- runtime object: [dincli/services/runtime.py](/home/azureuser/projects/devnet/dincli/services/runtime.py)
- manifest path helpers: [dincli/cli/utils.py](/home/azureuser/projects/devnet/dincli/cli/utils.py)
- client service invocation example: [dincli/cli/client.py](/home/azureuser/projects/devnet/dincli/cli/client.py)

High-level flow:

1. `dincli` identifies the active network and model.
2. `build_service_runtime_context(...)` resolves the manifest path.
3. `get_manifest(...)` loads the manifest JSON.
4. The manifest is attached to a `ServiceRuntimeContext`.
5. When a custom service is loaded, `dincli` injects that runtime into the function call.
6. Service code reads keys through `runtime.get_manifest_key(...)` or `runtime.require_manifest_key(...)`.

This design keeps manifest access centralized and avoids each service doing its own filesystem or IPFS lookups for configuration.

## Main Field Groups

### Metadata

| Field | Meaning |
|---|---|
| `name` | human-readable model name |
| `version` | manifest/model version |
| `description` | short summary of the task |
| `author` | model owner or maintainer |
| `technical details` | free-form notes |

### Task and contract linkage

| Field | Meaning |
|---|---|
| `Genesis_Model_CID` | IPFS CID of the genesis model artifact |
| `DINTaskCoordinator_Contract` | task coordinator contract address |
| `DINTaskAuditor_Contract` | task auditor contract address |

### Service entries

Each executable service function is represented by a manifest entry that points to a Python file and its IPFS CID.

Example:

```json
"train_client_model_and_upload_to_ipfs": {
  "type": "custom",
  "path": "services/client.py",
  "ipfs": "<cid>",
  "stakeholders": ["clients"]
}
```

Key meanings:

| Key | Meaning |
|---|---|
| `type` | currently `custom` for a project-provided Python service |
| `path` | relative path to the service file inside the model package |
| `ipfs` | CID used to fetch the service artifact |
| `stakeholders` | which roles rely on the service |

### Guides

The optional `guides` section maps stakeholder roles to Markdown CIDs:

```json
"guides": {
  "clients": "<client_guide_cid>"
}
```

### Requirements

The `requirements.txt` section maps each role to the IPFS CID of a role-specific requirements file:

```json
"requirements.txt": {
  "clients": "<cid>",
  "auditors": "<cid>",
  "aggregators": "<cid>",
  "modelowner": "<cid>"
}
```

## Manifest And Service Loading

For custom services, the manifest entry does more than describe the file. It defines how `dincli` finds and executes task-specific logic.

For example, in the client flow:

1. `dincli` reads `train_client_model_and_upload_to_ipfs` from the manifest.
2. It resolves the local cached file path from the entry's `path`.
3. It ensures the file exists locally, fetching from IPFS if needed.
4. It imports the Python function dynamically.
5. It injects the runtime context when the function accepts `runtime`.

This lets model owners swap in custom task logic without changing `dincli` itself.

## Nested DP Configuration

The DevNet manifest now supports a preferred nested `dp` block:

```json
"dp": {
  "enabled": true,
  "mode": "afterTraining",
  "mechanism": "post_training_gaussian",
  "parameters": {
    "clipping_norm": 1.0,
    "noise_multiplier": 0.5,
    "laplace_scale": 0.35,
    "clip_scope": "per_layer"
  }
}
```

Resolution rules in the current service:

- `dp.enabled: false` disables privacy;
- if the `dp` block is omitted, privacy is treated as disabled;
- if DP is enabled and no mechanism is specified, the client defaults to `post_training_gaussian`;
- the current client service supports `post_training_gaussian`, `post_training_laplace`, and `update_gaussian`.

## Why The Nested `dp` Block Matters

The nested block is easier to extend than flat keys because:

- parameters can be grouped by feature;
- new privacy options do not pollute the root manifest namespace;
- services can treat DP as one coherent config object;
- future builders in `dincli` can validate or generate the DP block more cleanly.

## Example Of Service Consumption

The service runtime object exposes the manifest through:

```python
runtime.get_manifest_key("dp", {})
runtime.require_manifest_key("ModelArchitecture")
```

That pattern is used in the client service to:

- read DP configuration;
- locate the service file entries;
- locate the model architecture service entry.

## Operational Constraints

The manifest is authoritative for configuration, but the service code still defines execution semantics.

Examples:

- the manifest can request `update_gaussian`, but only if the client service implements it;
- the manifest can set `clip_scope`, but the service decides what values are valid;
- the manifest can reference a custom service, but that service must still export the expected function name.

In other words, the manifest is the configuration contract and the service file is the execution contract.

## Recommended Authoring Rules

For current DevNet work:

- keep root-level metadata concise and stable;
- use the nested `dp` block for new DP configuration;
- treat every service entry as a deployable artifact, not just a local path;
- ensure `stakeholders` reflects who actually depends on that service file;
- keep `requirements.txt` entries aligned with the runtime needs of each role.

## Sources And Lineage

Primary local sources:

- example manifest: [cache_model_0/manifest.json](/home/azureuser/projects/devnet/cache_model_0/manifest.json)
- runtime object: [dincli/services/runtime.py](/home/azureuser/projects/devnet/dincli/services/runtime.py)
- service loading path: [dincli/cli/client.py](/home/azureuser/projects/devnet/dincli/cli/client.py)
- existing higher-level manifest doc: [Documentation/manifest.md](/home/azureuser/projects/devnet/Documentation/manifest.md)
- client-service technical doc: [Documentation/technical/services/clients.md](/home/azureuser/projects/devnet/Documentation/technical/services/clients.md)
- DP design notes: [Developer/issues/DifferentialPrivacy.md](/home/azureuser/projects/devnet/Developer/issues/DifferentialPrivacy.md)

Related external references for DP-specific manifest fields:

- Threshold KNN-Shapley paper: <https://arxiv.org/abs/2308.15709>
- Datascope upstream repo: <https://github.com/easeml/datascope>
- Awesome Data Valuation upstream repo: <https://github.com/daviddao/awesome-data-valuation>

The manifest structure itself is defined by this repository's code and examples. The external DP and valuation references inform how manifest fields may evolve, especially for future privacy-aware scoring and accounting work.
