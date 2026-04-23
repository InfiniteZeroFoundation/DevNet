# Manifest

The manifest is a JSON file containing the metadata for your model and task. It serves as the central configuration that ties together the model, its services, and contract addresses.

## Location

The manifest file must be placed at:

```
<root_dir>/tasks/<network>/task_<coordinator_address>/manifest.json
```

For example:
```
<root_dir>/tasks/sepolia_op_devnet/task_0x1e31...4b133/manifest.json
```

> [!NOTE]
> If the manifest file is absent when the genesis setup (`dincli task model-owner create-genesis`) runs, it is automatically created with default values from the default manifest CID (`bafybeibbhrefnamky7vmgcrhfx4ptxb3bdemh5dtnvwfkpualoganvnuve`).

---

## Manifest Fields

### Metadata Fields

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Name of the model |
| `version` | Yes | Version of the model |
| `description` | No | Description of the model |
| `author` | No | Author of the model |
| `technical details` | No | Technical details of the model |

### Contract & Model Fields

| Field | Required | Description |
|---|---|---|
| `Genesis_Model_CID` | Yes | IPFS CID of the genesis model. Set after running `dincli model-owner model create-genesis` |
| `DINTaskCoordinator_Contract` | Yes | Address of the deployed TaskCoordinator contract |
| `DINTaskAuditor_Contract` | Yes | Address of the deployed TaskAuditor contract |
| `dp_mode` | No | Differential Privacy mode: `"disabled"` or `"enabled"` (default: `"disabled"`) |

### Service Entries

Each service function is registered in the manifest as a JSON object with the following structure:

```json
"<function_name>": {
    "type": "custom",
    "path": "services/<service_file>.py",
    "ipfs": "<IPFS_CID_OF_SERVICE_FILE>",
    "stakeholders": ["<role1>", "<role2>"]
}
```

| Key | Description |
|---|---|
| `type` | Service type (currently `"custom"`) |
| `path` | Local relative path to the service file |
| `ipfs` | IPFS CID of the uploaded and pinned service file |
| `stakeholders` | List of roles that use this service (e.g., `"modelowner"`, `"clients"`, `"auditors"`, `"aggregators"`) |

For detailed documentation on each service file and the functions that must be implemented, see [services.md](services.md).

### Guides Field (Optional)

The Model Owner can set up Markdown guides specific to their model for clients, aggregators, auditors and other stakeholders:

```json
"guides": {
    "clients": "<client_guide_ipfs_hash>",
    "aggregators": "<aggregator_guide_ipfs_hash>",
    "auditors": "<auditor_guide_ipfs_hash>"
}
```

### Custom Fields

The model owner can define any custom fields in the manifest file as per their requirements. Custom fields/parameters can be accessed in services via the `get_manifest_key` function. The manifest and parameters can be updated as the model training progresses.

---

### Requirements.txt Field

The `requirements.txt` field in the manifest is used to specify the dependencies for the model services. It is a JSON object where the keys are the roles and the values are the IPFS CIDs of the `requirements.txt` file.

```json
"requirements.txt": {
    "clients": "<client_requirements_ipfs_hash>",
    "auditors": "<auditor_requirements_ipfs_hash>",
    "aggregators": "<aggregator_requirements_ipfs_hash>",
    "modelowner": "<modelowner_requirements_ipfs_hash>"
}
```

The stakeholders should move to the project root directory and download their respective requirements.txt file using the following command:

```bash
dincli ipfs download -c <requirements.txt_ipfs_hash> -f requirements.txt
```

and then install the requirements.txt file using the following command:

```bash
pip3 install -r requirements.txt
```

## Example Manifest

Please find the example/template manifest file at [cache_model_0/manifest.json](../cache_model_0/manifest.json)


---

## Updating the Manifest

Once the model is registered and assigned a model ID, the manifest file should be updated with the `Model ID` field and re-uploaded to IPFS. The following dincli command can be used to update the model CID in the DINModelRegistry contract:

```bash
dincli task model-owner update-manifest <model_id> [--modelCID <model_cid>] [--manifestpath <manifest_path>]
```
