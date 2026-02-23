# Model Owner Documentation

The Model Owner is the central figure who initiates a task, deploys contracts, and manages the Global Iteration (GI) lifecycle.

## 1. Deployment & Setup

### Deploy Contracts
Deploy the contracts specific to your task.

```bash
# Task Coordinator
dincli model-owner deploy task-coordinator --artifact <path>

# Task Auditor
dincli model-owner deploy task-auditor --artifact <path>
```


### Deposit Rewards in Task Auditor

> **Prerequisite**: The following key must be set in your `.env` file:

> `<NETWORK>_DINTaskCoordinator_Contract_Address`
> (e.g. `SEPOLIA_DEVNET_DINTaskCoordinator_Contract_Address`)
> `<NETWORK>_<TASK_COORDINATOR_ADDRESS>_DINTaskAuditor_Contract_Address`
> (e.g. `SEPOLIA_DEVNET_0x1234567890123456789012345678901234567890_DINTaskAuditor_Contract_Address`)

```bash
# Deposit rewards in Task Auditor
dincli model-owner deposit-reward-in-dintask-auditor --amount <usdt_amount>
# buy usdt using  
# dincli system buy-usdt <usdt_amount>
```


### Confirm Task Coordinator and Task Auditor as Slashers after DINDAO has added them as Slasher in DIN Coordinator Contract

> **Prerequisite**: The following key must be set in your `.env` file:
> `<NETWORK>_DINTaskCoordinator_Contract_Address`
> (e.g. `SEPOLIA_DEVNET_DINTaskCoordinator_Contract_Address`)

```bash
dincli model-owner add-slasher --taskCoordinator [--contract <task_coordinator_address>]
dincli model-owner add-slasher --taskAuditor [--contract <task_auditor_address>]
```
where `--contract` is optional and should be the address of the DIN task COordinator contract. If not provided, the contract address will be taken from the `.env` file from `<NETWORK>_DINTaskCoordinator_Contract_Address` key.

## Manifest file and services files

The manifest file is a json file that contains the metadata of the model and task. it must be created/ copied to  Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address / 'manifest.json' and edited along

if it is not present, it will be created with default values from default_manifest_CID = "QmQaPUfVAyQBrkRvHZWyH8tbNukmcgEmghYFGZA6LKo8tp". during create-genesis setup

The services for each stakeholder and Model Architect must be created by Model Owner specific to the task such as

1. modelowner.py
2. model.py
3. client.py
4. aggregator.py
5. auditor.py

The sample services files are available in the `DINv1MVC/cache_model_0/services` directory.
You must be elegant and ensure that your servives work fine for all stakeholders. model.py is for model architect, client.py is for client, aggregator.py is for aggregator and auditor.py is for auditor.

## 2. Genesis Model

Create and submit the initial model to start the task.

### Create Genesis Model

**Prerequisite**: The following key must be set in your `.env` file:

> `<NETWORK>_DINTaskCoordinator_Contract_Address`
> (e.g. `SEPOLIA_DEVNET_DINTaskCoordinator_Contract_Address`)


```bash
# Create (upload to IPFS)
dincli model-owner model create-genesis
```

### Submit Genesis Model

**Prerequisite**: The following key must be set in your `.env` file:

> `<NETWORK>_DINTaskCoordinator_Contract_Address`
> (e.g. `SEPOLIA_DEVNET_DINTaskCoordinator_Contract_Address`)

The test_data set must be available at Path(os.getcwd()) / "tasks" / effective_network.lower() / task_coordinator_address / "dataset"/"test"/"test_dataset.pt")

```bash
# Submit (register on-chain)
dincli model-owner model submit-genesis [--taskCoordinator <task_coordinator_address>] [--ipfs-hash <ipfs_hash>] [--score <score>] 
```

where taskCoordinator is optional and is address of the DIN task coordinator contract. If not provided, the contract address will be taken from the `.env` file from `<NETWORK>_DINTaskCoordinator_Contract_Address` key.

where ipfs-hash is optional and is the ipfs hash of the Genesis Model created in previous step. If not provided, the ipfs hash will be taken from the `.env` file from {effective_network.upper() + '_' + task_coordinator_address + '_GENESIS_MODEL_IPFS_HASH'} key.

where score is optional and is the score of the genesis model. If not provided, the score will be calculated using the `getscoreforGM` function in the `modelowner.py` service file.



## 3. Global Iteration (GI) Lifecycle

The bulk of the work happens in cycles called Global Iterations.

### Step 1: Start GI
```bash
dincli model-owner gi start <model-id> [--threshold <threshold>] [--gi <gi_index>]

```
where model-id is the id of the model to start the GI for.

where threshold is optional and is the score approval threshold for the local modelsfor the GI. If not provided, the default threshold is 5% accuracy less from the accuracy of the latest global model.

where gi_index is optional and is the index of the GI. If not provided, the current GI index will be used


### Step 2: Registrations
Manage the registration windows for participants.

```bash
# Open Registrations for Aggregators
dincli model-owner gi reg aggregators-open <model-id> [--gi <gi_index>]


# Close Registrations for Aggregators (after some appropriate time)
dincli model-owner gi reg aggregators-close <model-id> [--gi <gi_index>]

# show registered aggregators for current GI or specific GI
dincli model-owner gi show-registered-aggregators <model-id> [--gi <gi_index>]

where --gi is optional and is the index of the GI. If not provided, the current GI index will be used

# Open Registrations for Auditors
dincli model-owner gi reg auditors-open <model-id> [--gi <gi_index>]

# Close Registrations for Auditors (after some appropriate time)
dincli model-owner gi reg auditors-close <model-id> [--gi <gi_index>]
```
# show registered auditors for current GI or specific GI
dincli model-owner gi show-registered-auditors <model-id> [--gi <gi_index>]

where --gi is optional and is the index of the GI. If not provided, the current GI index will be used

### Step 3: Local Model Submission (LMS)
Allow clients to train and submit models.

```bash
# Open LMS
dincli model-owner lms open <model_id> [--gi <gi_index>]

# Close LMS (after appropriate deadline)
dincli model-owner lms close <model_id> [--gi <gi_index>]
```
 
Show lms submissions from clients

```bash
dincli model-owner lms show-models <model_id> [--gi <gi_index>]
```

### Step 4: Auditor Assignment
Assign registered auditors to evaluate the submitted batches.

```bash
# Create Auditors Batches
dincli model-owner auditor-batches create <model-id> [--gi <gi_index>]

# Create Test Dataset for Auditing Batches
dincli model-owner auditor-batches create-testdataset <model-id> [--test-data-path <path>] [--gi <gi_index>]
```
where --gi is optional and is the index of the GI. If not provided, the current GI index will be used
--test-data-path is optional and is the path to the test dataset. If not provided, the test dataset must be available at Path(CACHE_DIR) / effective_network /  f"model_{model_id}" / "dataset" / "test" / "test_dataset.pt"


# show auditor batches
```bash
dincli model-owner auditor-batches show <model-id> [--gi <gi_index>]
```


### Step 5: Evaluation Phase
Manage the evaluation period.

```bash
# Start Evaluation
dincli model-owner lms-evaluation start <model-id>
# let the auditors do there work

# Close Evaluation
dincli model-owner lms-evaluation close <model-id>
```

# show lms evaluation results
```
dincli model-owner lms-evaluation show <model-id> [--auditors] [--gi <gi_index>] [--models]
```
-- auditors is optional, if provided, it will show the evaluation results of all models grouped per assigned auditor

-- models is optional, if provided, it will show the evaluation results of all assigned auditors grouped per local model

-- gi is optional, if provided, it will show the evaluation results for the given GI



### Step 6: Aggregation Phase
Manage the aggregation of evaluated models.

```bash
# Create Aggregation Batches
dincli model-owner aggregation create-t1nt2-batches <model-id> [--gi <gi_index>]

# Show T1 aggregation batches
dincli model-owner aggregation show-t1-batches <model-id> [--gi <gi_index>] [--detailed]
# --detailed is optional, if provided, it will show the detailed information of all T1 aggregation batches including Aggregator Address, Submitted CID from the aggregator, and the Finalized CID for the Batch

# Show T2 aggregation batches
dincli model-owner aggregation show-t2-batches <model-id> [--gi <gi_index>] [--detailed]
# --detailed is optional, if provided, it will show the detailed information of all T2 aggregation batches including Aggregator Address, Submitted CID from the aggregator, and the Finalized CID for the Batch

# Start Tier 1 Aggregation
dincli model-owner aggregation T1 start <model-id> [--gi <gi_index>]
# ... wait for aggregators to submit their aggregated models ...

# Close Tier 1 Aggregation
dincli model-owner aggregation T1 close <model-id> [--gi <gi_index>]

# Start Tier 2 Aggregation
dincli model-owner aggregation T2 start <model-id> [--gi <gi_index>]
# ... wait for final aggregation ...

# Close Tier 2 Aggregation
dincli model-owner aggregation T2 close <model-id> [--gi <gi_index>]
```

### Step 7: End GI

# Slash Auditors

SLash the stake of the auditors who did not submit their evaluation results or submitted malicious evaluation results

```bash
dincli model-owner slash auditors <model-id> [--gi <gi_index>]
```

# Slash Aggregators

SLash the stake of the aggregators who did not submit their aggregated models or submitted malicious aggregated models

```bash
dincli model-owner slash aggregators <model-id> [--gi <gi_index>]
```

# End GI

Finalize the iteration and prepare for the next one.

```bash
dincli model-owner gi end <model-id> [--gi <gi_index>]
```

## 4. Monitoring & Management

### View State
Check the current status of the GI or participants.

```bash
dincli model-owner gi show-state <model-id>
```

### View Submissions
Inspect what has been submitted.

```bash
dincli model-owner lms show-models <model-id>
dincli model-owner lms-evaluation show --per-model <model-id>
dincli model-owner auditor-batches show <model-id>
dincli model-owner aggregation show-t1-batches <model-id>
dincli model-owner aggregation show-t2-batches <model-id>
```