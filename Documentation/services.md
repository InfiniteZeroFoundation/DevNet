# Services

The Model Owner must provide a set of service files that implement task-specific logic for each participant role in the DIN Protocol. These services are Python scripts used by different actors/stakeholders during the Federated Learning process. DIN Protocol provides a template for each service.

> [!NOTE]
> The Model Owner can use the templates provided by the DIN Protocol to create the services. It is up to the model owner to define the actual logic of the services but certain functions must be implemented as per the DIN Protocol specifications. The DIN-Protocol team can help Model Owner to create the custom services. Model Owner can use torch/tensorflow/keras or any other framework to create the model and related services.

Each service file must be uploaded and pinned to IPFS. The resulting CID is then referenced in the [manifest.json](manifest.md) so that `dincli` can automatically fetch the service from IPFS when needed.

## Service Files Overview

| File | Role | Description |
|---|---|---|
| `model.py` | All stakeholders | Defines the model architecture |
| `modelowner.py` | Model Owner | Model owner specific functions (genesis model, scoring, audit test data) |
| `client.py` | Clients | Client training and model submission logic |
| `auditor.py` | Auditors | Model evaluation and scoring logic |
| `aggregator.py` | Aggregators | T1 and T2 aggregation logic |

Sample service files are located in the `devnet/cache_model_0/services/` directory.

---

## 1. `model.py`

This service defines the model architecture. A `ModelArchitecture` class must be defined with `__init__` and `forward` methods implemented.

**Manifest entry:**

```json
"ModelArchitecture": {
    "type": "custom",
    "path": "services/model.py",
    "ipfs": "<IPFS_CID_OF_MODEL_PY>",
    "stakeholders": [
        "modelowner",
        "auditors",
        "aggregators",
        "clients"
    ]
}
```

---

## 2. `modelowner.py`

This service defines the functions used by the Model Owner to interact with the DIN Protocol for this model.

### 2.1. `getGenesisModelIpfs(base_path)`

Creates and uploads the genesis model to IPFS.

| Parameter | Description |
|---|---|
| `base_path` | Base path of the model directory |
| **Returns** | IPFS CID of the genesis model |

**Manifest entry:**

```json
"getGenesisModelIpfs": {
    "type": "custom",
    "path": "services/modelowner.py",
    "ipfs": "<IPFS_CID_OF_MODELOWNER_PY>",
    "stakeholders": [
        "modelowner"
    ]
}
```

### 2.2. `getscoreforGM(gi, gmcid, base_path)`

Calculates and returns the score for the global model.

| Parameter | Description |
|---|---|
| `gi` | Global iteration index |
| `gmcid` | Model CID |
| `base_path` | Base path of the model directory |
| **Returns** | Score for the global model |

**Manifest entry:**

```json
"getscoreforGM": {
    "type": "custom",
    "path": "services/modelowner.py",
    "ipfs": "<IPFS_CID_OF_MODELOWNER_PY>",
    "stakeholders": [
        "modelowner"
    ]
}
```

### 2.3. `create_audit_testDataCIDs(batch_counts, gi, base_path, test_data_path)`

Creates audit test data CIDs for auditor batches. The `testData_percentage_per_auditor_batch` is the percentage of test data used for each auditor batch (default: 5%).

| Parameter | Description |
|---|---|
| `batch_counts` | Number of audit batches to create |
| `gi` | Global iteration index |
| `base_path` | Base path of the model directory |
| `test_data_path` | Path to the test dataset |
| **Returns** | Audit test data CIDs |

**Manifest entry:**

```json
"create_audit_testDataCIDs": {
    "type": "custom",
    "path": "services/modelowner.py",
    "ipfs": "<IPFS_CID_OF_MODELOWNER_PY>",
    "stakeholders": [
        "modelowner"
    ]
}
```

---

## 3. `client.py`

This service defines the functions used by the clients to train and submit local models.

For the current DevNet reference implementation and the manifest-driven DP flow, see [technical/services/clients.md](technical/services/clients.md).

### 3.1. `train_client_model_and_upload_to_ipfs(...)`

Trains the client model on local data and uploads it to IPFS.

| Parameter | Description |
|---|---|
| `genesis_model_ipfs_hash` | IPFS CID of the genesis model |
| `account_address` | Client's wallet address |
| `effective_network` | Network identifier (default: `"local"`) |
| `initial_model_ipfs_hash` | IPFS CID of the initial model (optional) |
| `model_base_dir` | Base directory for model files |
| `gi` | Global iteration index |
| `runtime` | Injected manifest-aware service runtime context |
| **Returns** | IPFS CID of the trained client model |

Model Owner may define Differential Privacy (DP) logic for the model through the nested `dp` manifest block. If `dp.enabled` is `true`, the client service applies the configured mechanism from `client.py`.

**Manifest entry:**

```json
"train_client_model_and_upload_to_ipfs": {
    "type": "custom",
    "path": "services/client.py",
    "ipfs": "<IPFS_CID_OF_CLIENT_PY>",
    "stakeholders": [
        "clients"
    ]
}
```

---

## 4. `auditor.py`

This service defines the functions used by auditors to evaluate submitted local models.

### 4.1. `Score_model_by_auditor(...)`

Scores a local model as part of the auditing process.

| Parameter | Description |
|---|---|
| `gi` | Global iteration index |
| `genesis_model_cid` | IPFS CID of the genesis model |
| `batch_id` | Auditor batch index |
| `model_index` | Index of the model within the batch |
| `auditor_address` | Auditor's wallet address |
| `testDataCID` | IPFS CID of the test dataset |
| `lm_cid` | IPFS CID of the local model |
| `model_base_dir` | Base directory for model files |
| **Returns** | Score and eligibility for the local model |

**Manifest entry:**

```json
"Score_model_by_auditor": {
    "type": "custom",
    "path": "services/auditor.py",
    "ipfs": "<IPFS_CID_OF_AUDITOR_PY>",
    "stakeholders": [
        "auditors"
    ]
}
```

---

## 5. `aggregator.py`

This service defines the functions used by aggregators to combine local models during the aggregation phase.

### 5.1. `get_aggregated_cid_t1(...)`

Aggregates local models in a Tier 1 (T1) aggregation batch.

| Parameter | Description |
|---|---|
| `curr_GI` | Global iteration index |
| `aggregator_address` | Aggregator's wallet address |
| `model_cids` | List of local model IPFS CIDs |
| `genesis_model_ipfs_hash` | IPFS CID of the genesis model |
| `bid` | Batch index |
| `model_base_dir` | Base directory for model files |
| **Returns** | IPFS CID of the aggregated model |

**Manifest entry:**

```json
"get_aggregated_cid_t1": {
    "type": "custom",
    "path": "services/aggregator.py",
    "ipfs": "<IPFS_CID_OF_AGGREGATOR_PY>",
    "stakeholders": [
        "aggregators"
    ]
}
```

### 5.2. `get_aggregated_cid_t2(...)`

Aggregates T1 results in a Tier 2 (T2) aggregation batch to produce the final global model.

| Parameter | Description |
|---|---|
| `curr_GI` | Global iteration index |
| `aggregator_address` | Aggregator's wallet address |
| `model_cids` | List of T1-aggregated model IPFS CIDs |
| `genesis_model_ipfs_hash` | IPFS CID of the genesis model |
| `bid` | Batch index |
| `model_base_dir` | Base directory for model files |
| **Returns** | IPFS CID of the aggregated model |

**Manifest entry:**

```json
"get_aggregated_cid_t2": {
    "type": "custom",
    "path": "services/aggregator.py",
    "ipfs": "<IPFS_CID_OF_AGGREGATOR_PY>",
    "stakeholders": [
        "aggregators"
    ]
}
```
