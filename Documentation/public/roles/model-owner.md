# Model Owner Documentation

The Model Owner initiates and manages a federated learning task from start to finish. This includes deploying the required contracts, seeding the task with a genesis model, and orchestrating each Global Iteration (GI) lifecycle.

---

## 1. Deployment & Setup

### Deploy Contracts

Deploy the Task Coordinator and Task Auditor contracts specific to your task.

```bash
# Deploy the Task Coordinator
dincli model-owner deploy task-coordinator --artifact foundry/out/DINTaskCoordinator.sol/DINTaskCoordinator.json [--model-id <model_id>]

# Deploy the Task Auditor
dincli model-owner deploy task-auditor --artifact foundry/out/DINTaskAuditor.sol/DINTaskAuditor.json [--taskCoordinator <address>] [--model-id <model_id>]
```

| Option | Required | Description |
|---|---|---|
| `--artifact <path>` | Yes | The compiled Foundry JSON output (ABI and bytecode), from `cd foundry && forge build` |
| `--model-id <model_id>` | No | The ID `DINModelRegistry` will assign at approval; fixed in the contract. The coordinator defaults to `DINModelRegistry.totalModels()` (the ID the next approval assigns, with a warning that this only holds if no other request is approved first). The auditor defaults to the coordinator's `modelId()` and refuses any other value |
| `--taskCoordinator <address>` | No | Coordinator to pair the auditor with. Defaults to `<NETWORK>_DINTaskCoordinator_Contract_Address` in `.env` |

Both deploys also set the platform `DinToken` on the new contract (`setDinToken`), which reward deposits, claims and dispute bonds need. The auditor deploy then links the auditor to the coordinator.

Before deploying, set the platform `stake` and `token` addresses in this network's `din_info.json`, and `registry` too for the current auditor, which takes the registry as an immutable constructor argument. The auditor deploy also refuses a coordinator from a different contract generation (`taskProtocolVersion()`; the current pair is version `1`), because pairing is one-shot. Released legacy Hardhat artifacts can still be deployed, but they don't get the guard that stops a disabled model from starting new GIs. Agree the anticipated ID with the DIN-Representative; the registry assigns the authoritative ID at approval. See the [model workflow](../workflows/model-workflow.md) for registration and deployment requirements.

---


### Register Task Coordinator & Task Auditor as Slashers

After the DIN-Representative has authorized the contracts as slashers in the DIN Coordinator, confirm them on the task side.

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

The DIN protocol charges fees, in ETH, to submit model registration and manifest update requests. The registry contract holds them until the DIN-Representative sweeps them to the fee router (`dincli dinrep registry sweep-fees`).

Fees apply regardless of whether the request is approved or rejected (spam protection).

The defaults are below; the DIN-Representative can change them (`dincli dinrep registry set-fees`):

| Action | Open-Source | Proprietary |
|--------|------------|-------------|
| Register a new model | 0.000001 ETH | 0.00001 ETH |
| Request a manifest update | 0.0000001 ETH | 0.000001 ETH |

View the current fees:

```bash
dincli system get-registry-fee [--fee-type model-registry|manifest-update] [--model-type open-source|proprietary]
```

---

### Manifest File & Service Files

**Manifest file**

The manifest is a JSON file containing the metadata for your model and task. For the full schema, field descriptions, and an example, see [manifest.md](../manifest.md).

**Service files**

The Model Owner must provide a set of service files tailored to the task. For detailed documentation on each service file and the required function signatures, see [services.md](../services.md).

---

## 1b. Model Registration (Request → Approval)

Model registration is a **two-step process**. The Model Owner submits a request; the DIN-Representative reviews and approves (or rejects) it.

### Step 1 — Submit Registration Request

Submit your model to the registry. Requires the registration fee (see [Protocol Fees](#protocol-fees) above), which is sent with the request.

```bash
# Check the manifest's contract addresses and genesis CID against your .env first
dincli model-owner model validate-update-manifest

dincli task model-owner register-request \
  [--taskCoordinator <coordinator_address>] \
  [--taskAuditor <auditor_address>] \
  [--manifestpath <path> | --manifestCID <cid>] \
  [--isOpenSource]
```

The contract addresses default to the ones in your `.env`, and the manifest to the task directory's `manifest.json`, which is uploaded to IPFS. `--manifestCID` skips the upload and registers an already-pinned manifest directly. Without `--isOpenSource` the model is registered as proprietary.

On success you receive a **`requestId`**. Track it to monitor approval status.

### Step 2 — Wait for DIN-Representative Approval

The DIN-Representative reviews your request and approves it (`dincli dinrep registry approve-registration-request <requestId>`). Approval assigns the **`modelId`**, which must match the `modelId()` both task contracts were deployed with; dincli refuses a mismatch unless the DIN-Representative passes `--force`.

Check the status of your request:

```bash
# Your pending requests (add --include-processed for approved and rejected ones)
dincli task model-owner my-requests [--type model|manifest] [--include-processed]

# One request in detail
dincli task model-owner show-registration-request <requestId>
```

> [!IMPORTANT]
> The coordinator and auditor contracts must remain registered slashers and still be owned by your address at the time the DIN-Representative approves. If either condition changes, the approval will revert and you must submit a new request.

### Updating a Manifest

Manifest updates also follow a request/approval flow and pay the manifest-update fee. The model must not be disabled.

```bash
dincli task model-owner update-manifest-request <model_id> [--manifestpath <path> | --manifestCID <cid>]

# Track it
dincli task model-owner show-manifest-update-request <requestId>
```

The DIN-Representative reviews the request and applies it (`dincli dinrep registry approve-manifest-update <requestId>`).

---

## 2. Genesis Model

Create and submit the initial (genesis) model to seed the task.

### Create Genesis Model

Creates the genesis model with your `modelowner.py` service's `getGenesisModelIpfs`, uploads it to IPFS and saves its CID in `.env` as `<NETWORK>_<TASK_COORDINATOR_ADDRESS>_GENESIS_MODEL_IPFS_HASH`.

> **Prerequisite** — `<NETWORK>_DINTaskCoordinator_Contract_Address` must be set in your `.env` file, and the task directory must hold your manifest and services (`dincli model-owner task create-task-dir`, then `dincli model-owner task cache-default-artifacts` to start from the reference MNIST model).

```bash
dincli model-owner model create-genesis-model [--taskCoordinator <address>]
```

### Submit Genesis Model

Registers the genesis model on-chain.

> **Prerequisite** — `<NETWORK>_DINTaskCoordinator_Contract_Address` must be set in your `.env` file.  
> The test dataset must exist at:  
> `<project_root>/tasks/<network>/<coordinator_address>/dataset/test/test_dataset.pt`  
> (`dincli model-owner model add-default-test-data --default-test-data` fetches the reference MNIST one.)

```bash
dincli model-owner model submit-genesis-model [--taskCoordinator <address>] [--ipfs-hash <hash>] [--score <score>]
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

### Step 1 — Fund and Start GI

Each GI pays clients, auditors and aggregators from its reward pool, and `gi start` refuses a GI whose pool is empty. Fund it first, from your own DIN or from the protocol emission schedule:

```bash
# Deposit DIN into a GI's reward pool (approves, then deposits)
dincli model-owner rewards deposit <model_id> --amount <din_amount> [--gi <gi_index>]

# Or fund it from the DinEmission schedule
dincli model-owner rewards fund-emission <model_id> [--gi <gi_index>]
```

`--gi` defaults to the next GI. Buy DIN with `dincli dintoken buy <eth_amount>`.

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

Assign registered Auditors to evaluate the submitted local model batches, and give each batch its test data. The GI state moves `LMSclosed` → `AuditSeedLocked` → `AuditorsBatchesCreated` → `AuditTestDataAssigned`.

```bash
# Create Auditor batches (locks the batch-assignment seed first if no auditor has: `dincli auditor lock-seed`)
dincli model-owner auditor-batches create <model_id> [--gi <gi_index>]

# Encrypt each batch's test data to its auditors' keys; --submit assigns it on-chain
dincli model-owner auditor-batches create-testdataset <model_id> [--gi <gi_index>] [--test-data-path <path>] [--submit] [--batch <batch_id> ...]

# Show Auditor batches
dincli model-owner auditor-batches show <model_id> [--gi <gi_index>]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | GI index. Defaults to the current GI if omitted |
| `--test-data-path <path>` | No | Path to the test dataset. Defaults to `<CACHE_DIR>/<network>/model_<model_id>/dataset/test/test_dataset.pt` if omitted |
| `--submit` | No | Assign the test data on-chain. Once every batch has it, the GI moves to `AuditTestDataAssigned`, which evaluation needs |
| `--batch <batch_id>` | No | Repeatable. Retry only these batches after a partial failure |

`create-testdataset --submit` checks first that every batch auditor has registered an encryption key (`dincli auditor register-encryption-key`) and stops, naming them, if any hasn't. It saves each batch's key and plaintext hash under `<model dir>/audits/testdata_keys/` (mode 0600); keep them to answer test-data disputes.

> [!IMPORTANT]
> The first time `create-testdataset --submit` runs, and again after the owner key changes, it writes `owner_encryption_pubkey` into the model-cache manifest at `<CACHE_DIR>/<network>/model_<model_id>/manifest.json`, and only there. Auditors on other machines read the key from the manifest at the on-chain CID, so until it's published they skip decryption and evaluation. Publish it before opening evaluation:
> 1. `dincli task model-owner update-manifest-request <model_id> --manifestpath <CACHE_DIR>/<network>/model_<model_id>/manifest.json`. Point it at the model-cache manifest the command changed, not the task-directory manifest used at registration.
> 2. Wait for the DIN-Representative's `dincli dinrep registry approve-manifest-update <request_id>`.
> 3. Make sure remote auditors have the approved CID before evaluation starts. dincli re-fetches the manifest when its on-chain CID changes.
>
> Only the public key goes in the manifest. Never publish the owner's private key.

---

### Step 5 — Evaluation Phase

Manage the period during which Auditors score the local models.

Scores are commit-then-reveal: auditors commit hidden scores while evaluation is open, then reveal them in a window you open. Only revealed scores count.

```bash
# Start evaluation (opens the commit window)
dincli model-owner lms-evaluation start <model_id> [--gi <gi_index>]

# Close the commit window and open the reveal window
dincli model-owner lms-evaluation start-reveal <model_id> [--gi <gi_index>]

# Close evaluation (after auditors have revealed)
dincli model-owner lms-evaluation close <model_id> [--gi <gi_index>]
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

`create-t1nt2-batches` locks the T1/T2 batch-assignment seed first if no aggregator has (`dincli aggregator lock-seed`); the GI moves `LMSevaluationClosed` → `AggSeedLocked` → `T1nT2Bcreated`.

Like evaluation, each tier is commit-then-reveal: aggregators commit a hidden hash of their aggregated CID, then reveal it once you open the reveal window. Only revealed CIDs count, and a commit that is never revealed is slashed like a missed submission.

```bash
# Start Tier 1 Aggregation (opens the commit window)
dincli model-owner aggregation T1 start <model_id> [--gi <gi_index>]

# Close the T1 commit window and open the reveal window
dincli model-owner aggregation T1 start-reveal <model_id> [--gi <gi_index>]

# Close Tier 1 Aggregation (finalizes each T1 batch from the revealed CIDs)
dincli model-owner aggregation T1 close <model_id> [--gi <gi_index>]

# Start Tier 2 Aggregation — Aggregators produce the final global model from finalized T1 batches
dincli model-owner aggregation T2 start <model_id> [--gi <gi_index>]

# Close the T2 commit window and open the reveal window
dincli model-owner aggregation T2 start-reveal <model_id> [--gi <gi_index>]

# Close Tier 2 Aggregation
dincli model-owner aggregation T2 close <model_id> [--gi <gi_index>]

# Score the final global model on your test dataset and record it on-chain
dincli model-owner aggregation T2 set-score <model_id> [--gi <gi_index>]
```

`set-score` doesn't change the GI state. Run it before slashing: `slash auditors` uses the score and asks you to confirm if it still reads 0.

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

**End the GI** — finalize the iteration and settle its reward pool:

```bash
dincli model-owner gi end <model_id> [--gi <gi_index>]
```

`--gi` is optional for all commands above. Defaults to the current GI if omitted.

---

### Step 8 — Rewards and Registration Slots

Once the GI has ended, each participant claims and withdraws its own share (`dincli rewards claim <model_id> --gi <gi>`, then `dincli rewards withdraw <model_id>`).

Release the ended GI's validator registration slots, once per GI. Until you do, those registrations count against each validator's concurrent-registration cap:

```bash
dincli model-owner gi release-slots <model_id> [--gi <gi_index>]
```

`--gi` defaults to the current GI once it has ended. To start the next GI, fund it (Step 1) and run `gi start` again.

---

### Disputes

Auditors can dispute their batch's test data, and any active validator can dispute a finalized T1/T2 batch. You answer and settle them:

```bash
# Test data: reveal the batch key and plaintext hash (within the dispute window)
dincli model-owner disputes resolve-test-data <model_id> --gi <gi> --batch <batch_id>
# Test data: anyone can close an unanswered dispute once the window has passed (it is upheld)
dincli model-owner disputes close-expired <model_id> --gi <gi> --batch <batch_id>
# Test data: assign new test data to a batch whose dispute was upheld
dincli model-owner disputes reassign-test-data <model_id> --batch <batch_id> [--gi <gi>] [--test-data-path <path>]

# Aggregation: reject, or uphold (assigns a fresh subgroup of 3 aggregators; locks the dispute seed first)
dincli model-owner disputes resolve-aggregation <model_id> --gi <gi> --tier t1|t2 --batch <batch_id> --upheld|--rejected
# Aggregation: after the off-chain recomputation, confirm (original aggregators whose revealed CID matched the disputed one are slashed, bond returned) or dismiss (bond forfeited)
dincli model-owner disputes settle-recomputation <model_id> --gi <gi> --tier t1|t2 --batch <batch_id> --confirmed|--dismissed
# Aggregation: anyone, past the resolution deadline (the fresh subgroup is slashed)
dincli model-owner disputes expire <model_id> --gi <gi> --tier t1|t2 --batch <batch_id>
```

`resolve-test-data` needs the key `create-testdataset --submit` saved. An upheld test-data dispute takes part of the GI's reward pool as a penalty, but only while the GI's rewards are unsettled. `gi end` settles them without waiting for open disputes, so resolve or close pending test-data disputes before ending the GI if the penalty is to apply.

Upholding an aggregation dispute only records the fresh subgroup on-chain. They can't submit a recomputation on-chain, so you coordinate it with them off-chain and call `settle-recomputation` before anyone calls `expire`. After `resolutionDeadline`, anyone can call `expire`, which slashes all three fresh-subgroup members. See [model-workflow.md](../workflows/model-workflow.md#17-disputes) for the full flow.

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
dincli model-owner lms-evaluation show <model_id> --models

# Auditor batch assignments
dincli model-owner auditor-batches show <model_id>

# Tier 1 aggregation batch status
dincli model-owner aggregation show-t1-batches <model_id>

# Tier 2 aggregation batch status
dincli model-owner aggregation show-t2-batches <model_id>
```