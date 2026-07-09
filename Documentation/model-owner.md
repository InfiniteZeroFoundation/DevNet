# Model Owner Documentation

The Model Owner initiates and manages a federated learning task from start to finish. This includes deploying the required contracts, seeding the task with a genesis model, and orchestrating each Global Iteration (GI) lifecycle.

---

## 1. Deployment & Setup

### Deploy Contracts

Deploy the Task Coordinator and Task Auditor contracts specific to your task.

```bash
# Deploy the Task Coordinator
dincli model-owner deploy task-coordinator --artifact <path_to_artifact>

# Deploy the Task Auditor
dincli model-owner deploy task-auditor --artifact <path_to_artifact>
```

The `--artifact` flag must point to the compiled Hardhat/Foundry JSON output (contains ABI and bytecode).

---


### Register Task Coordinator & Task Auditor as Slashers

After the DIN DAO has authorized the contracts as slashers in the DIN Coordinator, confirm them on the task side.

> **Prerequisite** — the following key must be set in your `.env` file:
> - `<NETWORK>_DINTaskCoordinator_Contract_Address`  
>   *(e.g. `SEPOLIA_OP_DEVNET_DINTaskCoordinator_Contract_Address`)*

```bash
# Confirm Task Coordinator as a slasher
dincli model-owner add-slasher --taskCoordinator [--contract <task_coordinator_address>]

# Confirm Task Auditor as a slasher
dincli model-owner add-slasher --taskAuditor [--contract <task_coordinator_address>]
```

`--contract` is optional. If omitted, the address is read from the `<NETWORK>_DINTaskCoordinator_Contract_Address` key in your `.env` file.

---

### Protocol Fees

The DIN protocol charges fees to submit model registration and manifest update requests. Fees are held by the registry contract and can only be withdrawn by the DAO admin.

Fees apply regardless of whether the request is approved or rejected (spam protection).

| Action | Open-Source | Proprietary |
|--------|------------|-------------|
| Register a new model | 0.000001 ETH | 0.00001 ETH |
| Request a manifest update | 0.0000001 ETH | 0.000001 ETH |

View current fees:

```bash
dincli system get-fees
```

---

### Manifest File & Service Files

**Manifest file**

The manifest is a JSON file containing the metadata for your model and task. For the full schema, field descriptions, and an example, see [manifest.md](manifest.md).

**Service files**

The Model Owner must provide a set of service files tailored to the task. For detailed documentation on each service file and the required function signatures, see [services.md](services.md).

---

## 1b. Model Registration (Request → Approval)

Model registration is a **two-step process**. The Model Owner submits a request; the DIN DAO reviews and approves (or rejects) it.

### Step 1 — Submit Registration Request

Submit your model to the registry. Requires the registration fee (see [Protocol Fees](#protocol-fees) above).

```bash
# TODO
dincli model-owner registry request-registration \
  --manifest <path_to_manifest_cid_bytes32> \
  --task-coordinator <coordinator_address> \
  --task-auditor <auditor_address> \
  [--open-source]
```

On success you receive a **`requestId`**. Track it to monitor approval status.

### Step 2 — Wait for DAO Approval

The DIN DAO reviews your request and calls `approveModel(requestId)`. You will receive a **`modelId`** once approved.

Check the status of your request:

```bash
# TODO
dincli model-owner registry show-request <requestId>
```

> [!IMPORTANT]
> The coordinator and auditor contracts must remain registered slashers and still be owned by your address at the time the DAO approves. If either condition changes, the approval will revert and you must submit a new request.

### Updating a Manifest

Manifest updates also follow a request/approval flow. The model must not be disabled.

```bash
# TODO
dincli model-owner registry request-manifest-update <model_id> --manifest <new_manifest_cid_bytes32>
```

The DAO reviews the request and calls `approveManifestUpdate(requestId)` to apply it.

---

## 2. Genesis Model

Create and submit the initial (genesis) model to seed the task.

### Create Genesis Model

Uploads the genesis model to IPFS.

> **Prerequisite** — `<NETWORK>_DINTaskCoordinator_Contract_Address` must be set in your `.env` file.

```bash
dincli model-owner model create-genesis
```

### Submit Genesis Model

Registers the genesis model on-chain.

> **Prerequisite** — `<NETWORK>_DINTaskCoordinator_Contract_Address` must be set in your `.env` file.  
> The test dataset must exist at:  
> `<project_root>/tasks/<network>/task_<coordinator_address>/dataset/test/test_dataset.pt`

```bash
dincli model-owner model submit-genesis [--taskCoordinator <address>] [--ipfs-hash <hash>] [--score <score>]
```

| Option | Required | Description |
|---|---|---|
| `--taskCoordinator <address>` | No | Address of the Task Coordinator contract. Defaults to the value in `.env` if omitted |
| `--ipfs-hash <hash>` | No | IPFS hash of the genesis model from the previous step. Defaults to the value stored in `.env` if omitted as `<NETWORK>_<TASK_COORDINATOR_ADDRESS>_GENESIS_MODEL_IPFS_HASH` |
| `--score <score>` | No | Score of the genesis model. Calculated automatically via `getscoreforGM()` in `modelowner.py` if omitted |

---

## 3. Global Iteration (GI) Lifecycle

The bulk of the work happens in repeating cycles called Global Iterations. Follow these steps in order for each GI.

---

### Step 1 — Start GI

```bash
dincli model-owner gi start <model_id> [--gi <gi_index>] [--threshold <threshold>]
```

| Argument / Option | Required | Description |
|---|---|---|
| `<model_id>` | Yes | The ID of the model to start the GI for |
| `--gi <gi_index>` | No | GI index to start. Defaults to the next sequential GI if omitted |
| `--threshold <threshold>` | No | Minimum score threshold for accepting local models. Defaults to 5% below the latest global model accuracy if omitted |

---

### Step 2 — Registration

Open and close registration windows for Aggregators and Auditors.

```bash
# Open Aggregator registration
dincli model-owner gi reg aggregators-open <model_id> [--gi <gi_index>]

# Close Aggregator registration
dincli model-owner gi reg aggregators-close <model_id> [--gi <gi_index>]

# Show registered Aggregators
dincli model-owner gi show-registered-aggregators <model_id> [--gi <gi_index>]

# Open Auditor registration
dincli model-owner gi reg auditors-open <model_id> [--gi <gi_index>]

# Close Auditor registration
dincli model-owner gi reg auditors-close <model_id> [--gi <gi_index>]

# Show registered Auditors
dincli model-owner gi show-registered-auditors <model_id> [--gi <gi_index>]
```

`--gi` is optional for all commands above. Defaults to the current GI if omitted.

---

### Step 3 — Local Model Submission (LMS)

Open and close the window during which Clients can submit their trained local models.

```bash
# Open LMS
dincli model-owner lms open <model_id> [--gi <gi_index>]

# Close LMS
dincli model-owner lms close <model_id> [--gi <gi_index>]

# View submissions from Clients
dincli model-owner lms show-models <model_id> [--gi <gi_index>]
```

`--gi` is optional for all commands above. Defaults to the current GI if omitted.

---

### Step 4 — Auditor Assignment

Assign registered Auditors to evaluate the submitted local model batches.

```bash
# Create Auditor batches
dincli model-owner auditor-batches create <model_id> [--gi <gi_index>]

# Generate the test dataset used for auditing
dincli model-owner auditor-batches create-testdataset <model_id> [--gi <gi_index>] [--test-data-path <path>]

# Show Auditor batches
dincli model-owner auditor-batches show <model_id> [--gi <gi_index>]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | GI index. Defaults to the current GI if omitted |
| `--test-data-path <path>` | No | Path to the test dataset. Defaults to `<CACHE_DIR>/<network>/model_<model_id>/dataset/test/test_dataset.pt` if omitted |

---

### Step 5 — Evaluation Phase

Manage the period during which Auditors score the local models.

```bash
# Start evaluation — Auditors begin their evaluations
dincli model-owner lms-evaluation start <model_id>

# Close evaluation — collect results
dincli model-owner lms-evaluation close <model_id>
```

**View evaluation results:**

```bash
dincli model-owner lms-evaluation show <model_id> [--gi <gi_index>] [--auditors] [--models]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | Show results for a specific GI. Defaults to the current GI if omitted |
| `--auditors` | No | Also show results grouped per Auditor |
| `--models` | No | Also show results grouped per local model |

---

### Step 6 — Aggregation Phase

Manage the creation and execution of aggregation batches.

```bash
# Create Tier 1 and Tier 2 aggregation batches
dincli model-owner aggregation create-t1nt2-batches <model_id> [--gi <gi_index>]

# Show T1 batches
dincli model-owner aggregation show-t1-batches <model_id> [--gi <gi_index>] [--detailed]

# Show T2 batches
dincli model-owner aggregation show-t2-batches <model_id> [--gi <gi_index>] [--detailed]
```

`--detailed` is optional. When provided, includes the Aggregator address, submitted CID, and finalized CID for each batch.

```bash
# Start Tier 1 Aggregation — Aggregators begin combining approved local model in T1 batches
dincli model-owner aggregation T1 start <model_id> [--gi <gi_index>]

# Close Tier 1 Aggregation
dincli model-owner aggregation T1 close <model_id> [--gi <gi_index>]

# Start Tier 2 Aggregation — Aggregators produce the final global model from finalized T1 batches
dincli model-owner aggregation T2 start <model_id> [--gi <gi_index>]

# Close Tier 2 Aggregation
dincli model-owner aggregation T2 close <model_id> [--gi <gi_index>]
```

`--gi` is optional for all commands above. Defaults to the current GI if omitted.

---

### Step 7 — Slash & End GI

**Slash non-compliant Auditors** — penalize Auditors who failed to submit or submitted malicious results:

```bash
dincli model-owner slash auditors <model_id> [--gi <gi_index>]
```

**Slash non-compliant Aggregators** — penalize Aggregators who failed to submit or submitted malicious results:

```bash
dincli model-owner slash aggregators <model_id> [--gi <gi_index>]
```

**End the GI** — finalize the iteration and advance to the next:

```bash
dincli model-owner gi end <model_id> [--gi <gi_index>]
```

`--gi` is optional for all commands above. Defaults to the current GI if omitted.

---

## 4. Monitoring & Management

### Check GI State

View the full status of the current Global Iteration.

```bash
dincli task gi show-state <model_id>
```

### View All Submissions

A quick-reference set of read commands:

```bash
# Local model submissions
dincli model-owner lms show-models <model_id>

# Evaluation results grouped by model
dincli model-owner lms-evaluation show --models <model_id>

# Auditor batch assignments
dincli model-owner auditor-batches show <model_id>

# Tier 1 aggregation batch status
dincli model-owner aggregation show-t1-batches <model_id>

# Tier 2 aggregation batch status
dincli model-owner aggregation show-t2-batches <model_id>
```