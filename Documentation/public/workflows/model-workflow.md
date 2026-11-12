# Preface

In this guide we will describe the workflow of the DIN Protocol for a model.

In Model Workflow there are 5 main entities:

1. Model-Owner
2. DIN-Representative
3. Auditors
4. Aggregators
5. Clients (Model-Trainees)

The DIN devnet is deployed on the Optimism Sepolia testnet with code name `SEPOLIA_OP_DEVNET` 

so all entities must configure their dincli to use this network as 

```bash
dincli system configure-network --network "sepolia_op_devnet"
```

Also each actor/stakeholder needs to have a wallet address to interact with the DIN Protocol. Before executing any command, the actor/stakeholder needs to connect their wallet to the DIN CLI.

```bash
dincli system register-wallet --account <account_id>
```
> [!WARNING]
> `--account <index>` (using `ETH_PRIVATE_KEY_<n>` from `.env`) is
> **local development only**. Production validators should use the encrypted
> keystore — see [wallet-setup.md](../guides/wallet-setup.md).

> [!NOTE]
> More on wallet configuration can be found in the [DIN CLI Documentation](../cli-reference.md).


In current DIN Protocol, the model owner needs to deploy a taskCoordinator contract and a taskAuditor contract specific to each model.

For current Foundry artifacts, `model-owner deploy task-coordinator` defaults `--model-id` to `DINModelRegistry.totalModels()`, the ID the next approval assigns. This assumes no other registration is approved first. `model-owner deploy task-auditor` defaults to the paired coordinator’s `modelId()`; explicit IDs must match. Both commands configure the platform `DinToken` from this network’s `din_info.json` (`token`), with auditor token setup completed before pairing. Configure the canonical platform registry address in this network's `din_info.json` (`registry`) before deploying the auditor. Its fourth constructor argument is immutable registry wiring. The coordinator reports `taskProtocolVersion() == 1`, identifying the interface that requires the auditor GI-start guard. Before deploying an auditor, the CLI checks this version as well as matching model IDs: version 1 requires the registry-aware four-argument auditor. Released unversioned coordinators remain supported with matching legacy auditors: coordinators without `modelId()` use the two-argument auditor, and those with `modelId()` use the three-argument auditor; unknown versions and mixed generations are rejected before deployment or pairing. Legacy pairs do not gain the guard described below. Unsupported custom constructor signatures are rejected.

The checked-in `cache_model_0` artifacts and manifest describe the current reference pair. The `cache-default-artifacts` command instead downloads the manifest and ABIs selected by this network's `din_info.json` (`default_manifest` and `default_abis`); those historical bootstrap CIDs are not refreshed by this change. Verify the downloaded constructor signatures and registry wiring before using them for a new deployment.

The DIN-Representative must approve the model before **any** GI can start. Both start overloads check the registry-assigned ID by auditor address; do not assume the anticipated constructor ID establishes registration. Coordinate ID allocation with the DIN-Representative for correct stake floors.

Disabling a model prevents future GIs, including those with a pre-funded or privately funded pool. An in-flight GI continues through work, slashing, settlement and reward claims. There is no GI abort or new pool refund/recovery path. The guard requires a newly deployed compatible coordinator/auditor pair with canonical registry wiring and reviewed task code; existing deployments remain unchanged. See [kill-switch scope](../../technical/contracts/DINModelRegistry.md#11-kill-switch).


# Workflow

## 1. Deploy TaskCoordinator - Model Owner

Model Owner deploys a taskCoordinator contract specific to each model, from the Foundry build output (`cd foundry && forge build`):
```bash
dincli model-owner deploy task-coordinator \
    --artifact "/path/to/devnet/foundry/out/DINTaskCoordinator.sol/DINTaskCoordinator.json" \
    [--model-id <model_id>]
```

`--model-id` is the ID `DINModelRegistry` will assign when your registration is approved. It is fixed in the contract and can't be changed later. If you leave it out, dincli uses `DINModelRegistry.totalModels()`, the ID the next approval assigns, and warns you that this only holds if no other registration request is approved before yours. The deploy also points the contract at the platform `DinToken` (`setDinToken`), which dispute bonds need.

dincli will store the taskCoordinator contract address in the .env file as `SEPOLIA_OP_DEVNET_DINTaskCoordinator_Contract_Address` in your local project directory which we call `root_dir`.

## 2. Deploy TaskAuditor - Model Owner

Model Owner deploys a taskAuditor contract specific to each model.
```bash
dincli model-owner deploy task-auditor \
    --artifact "/path/to/devnet/foundry/out/DINTaskAuditor.sol/DINTaskAuditor.json" \
    [--model-id <model_id>]
```

`--model-id` defaults to the coordinator's `modelId()`, and dincli refuses a value that doesn't match it. The deploy sets the auditor's `DinToken` (reward deposits and claims need it) and links the auditor to the coordinator.

dincli will store the taskAuditor contract address in the .env file as `SEPOLIA_OP_DEVNET_<task_coordinator_contract_address>_DINTaskAuditor_Contract_Address` in your local project directory which we call `root_dir`.

## 3. Request Slasher Authorization - Model Owner

Before a model can be registered with `DINModelRegistry`, both its `TaskCoordinator` and `TaskAuditor` contracts must be authorized as **slashers** on the `DINValidatorStake` contract. The model owner must request this authorization from the **DIN-Representative** off-chain.

> [!IMPORTANT]
> Your model **cannot** be registered with `DINModelRegistry` until your `TaskCoordinator` (and `TaskAuditor`) contracts are whitelisted as authorized slashers. Complete this step **before** attempting model registration — the registry contract will revert if the contracts are not yet authorized.

### Official Contact Channels

Reach out to the DIN-Representative through any of the following channels:

| Channel  | Link / Handle |
|----------|--------------|
| Discord  | `#model-onboarding` channel on the Infinte Zero Foundation Discord server: https://discord.gg/fSWPgdMA6 
| Telegram Group| https://t.me/+h46VS3AnO384ZGI8 |
| Email    | umermajeed.cto@gmail.com abrahamnash@protonmail.com |

> DIN Protocol is developed and maintained by InfiniteZero Foundation

> Dr. Umer Majeed is the Founding Member of InfiniteZero Foundation. He is the Technical Architecture & Implementation Lead for the DIN Protocol. Please mention "DIN Protocol Model Registration Request" in the subject of the email

> Dr. Abraham Nash is the Founding Member of InfiniteZero Foundation. He is Vision, Strategy & Ecosystem Development Lead for the DIN Protocol. Please mention "DIN Protocol Model Registration Request" in the subject of the email

### Required Information for Your Request

Please include all of the following in your message so the DIN-Representative can review and process your request efficiently:

1. **TaskCoordinator contract address** — deployed in Step 1.
2. **TaskAuditor contract address** — deployed in Step 2.
3. **Network / Chain ID** — e.g., `Optimism Sepolia (chainId: 11155420)`.
4. **Deployment transaction hashes** — for both contracts (used for independent on-chain verification).
5. **Model description** — model type, intended use-case, and whether it is open-source or proprietary.
6. **Model-owner wallet address** — the account used for deployment.

> [!NOTE]
> The DIN-Representative will verify that:
> - Both contracts were deployed by the stated model-owner address.
> - The `TaskCoordinator` implements the `IDINTaskCoordinator` interface and references the correct `DINValidatorStake` contract.
> - The `TaskAuditor` is correctly linked to the `TaskCoordinator`.
> - No malicious or unauthorized slashing logic is embedded in the contracts.
>
> Review typically takes **1–3 business days**. You will be notified through the same channel you used to submit your request.

> [!WARNING]
> Do **not** attempt to call `addSlasher` directly — only the DIN-Representative wallet is permitted to invoke this function through `DinCoordinator`. Unauthorized calls will revert on-chain.

---

## 4. Authorize Contracts as Slashers - DIN-Representative

Once the DIN-Representative reviews and approves the request, they execute the following on-chain to register both contracts as authorized slashers:

```bash

# Register TaskCoordinator as an authorized slasher
dincli dinrep add-slasher --contract <TASK_COORDINATOR_ADDRESS>

# Register TaskAuditor as an authorized slasher
dincli dinrep add-slasher --contract <TASK_AUDITOR_ADDRESS>
```

> [!NOTE]
> After this step, both contracts are recognized by `DINValidatorStake` as authorized slashers. Validators (auditors / aggregators) who violate protocol rules can now be slashed by these contracts.

Once complete, the DIN-Representative will notify the model-owner through the same channel used to submit the request.

---

## 5. Confirm Slasher Authorization - Model Owner

Once the DIN-Representative confirms the slasher authorization for both taskCoordinator and taskAuditor contracts, Model Owner confirms the slasher authorization on their end by calling the add-slasher function on both contracts.

```bash
dincli model-owner add-slasher --taskCoordinator 

dincli model-owner add-slasher --taskAuditor 
```

> [!IMPORTANT]
> Please, note that the addresses of the taskCoordinator and taskAuditor contracts must be stored in the .env file as `SEPOLIA_OP_DEVNET_DINTaskCoordinator_Contract_Address` and `SEPOLIA_OP_DEVNET_<task_coordinator_contract_address>_DINTaskAuditor_Contract_Address` respectively. 

After this step, model owner can proceed to the next step in the model workflow.

## 6. Create Manifest & Services - Model Owner

Before registering the model, the Model Owner must prepare the service files and manifest.

### 6.1. Create Services

The Model Owner must provide Python service files that implement task-specific logic for each participant role:

| File | Role |
|---|---|
| `model.py` | Defines the model architecture |
| `modelowner.py` | Model Owner functions (genesis model, scoring, audit test data) |
| `client.py` | Client training and model submission |
| `auditor.py` | Model evaluation and scoring |
| `aggregator.py` | T1 and T2 aggregation |

Each service file must be uploaded and pinned to IPFS. The resulting CID is referenced in the manifest file.

> For detailed documentation on each service file and required function signatures, see [services.md](../services.md).

### 6.2. Create Manifest File

The manifest is a JSON file containing model metadata, contract addresses, and service entries. It must be placed in the task directory:

```
<root_dir>/tasks/<network>/<coordinator_address>/manifest.json
```

To start from the reference MNIST model, create the task directory and cache the default manifest, services, ABIs and requirements into it, then edit them for your model:

```bash
dincli model-owner task create-task-dir
dincli model-owner task cache-default-artifacts
```

> For the full manifest schema, field descriptions, and an example manifest, see [manifest.md](../manifest.md).

  
## 7. Create and Submit Genesis Model - Model Owner

Model Owner creates and submits the genesis model to the TaskCoordinator contract. 

The following dincli command is used to create the genesis model:

```bash
dincli model-owner model create-genesis-model
```

> make sure that the manifest.json file is present at `<root_dir>/tasks/sepolia_op_devnet/<task_coordinator_contract_address>/manifest.json` before running the above command. The above dincli command will use `getGenesisModelIpfs` in `modelowner.py` service  to create the genesis model and upload it to IPFS and store the IPFS CID in the .env file as `SEPOLIA_OP_DEVNET_<TASK_COORDINATOR_CONTRACT_ADDRESS>_GENESIS_MODEL_IPFS_HASH`. Please note that dincli can automatically fetch the service from IPFS using the coressponding entry for `getGenesisModelIpfs` in the manifest.json file.

The model owner can submit the genesis model to the TaskCoordinator contract using the following dincli command:

```bash
dincli model-owner model submit-genesis-model [--ipfs-hash <cid>] [--score <score>]
```

> make sure that the appropriate test dataset for the model is available at `<root_dir>/tasks/sepolia_op_devnet/<task_coordinator_contract_address>/dataset/test/test_dataset.pt` before running the above command (`dincli model-owner model add-default-test-data --default-test-data` fetches the reference MNIST one). The test dataset will be used to evaluate the genesis model and calculate the score. This score will set the threshold range for the final eligibility of local models.

> this command is safe to re-run. If the genesis model hash was already submitted on-chain (e.g. a prior run submitted the hash but failed before or during the score submission), re-running it detects that the hash is already set, verifies it still matches the CID you're scoring, and (re-)submits only the tier 2 score. If the on-chain hash doesn't match the CID you're submitting, it exits with an error instead of attaching a score to the wrong genesis model.

## 8. Register Model - Model Owner & DIN-Representative

Model Owner updates the manifest file at `<root_dir>/tasks/sepolia_op_devnet/<task_coordinator_contract_address>/manifest.json`, especially the `Genesis_Model_CID`, `DINTaskCoordinator_Contract`, and `DINTaskAuditor_Contract` fields with the IPFS CID of the genesis model, the DINTaskCoordinator contract address and the DINTaskAuditor contract address respectively. `validate-update-manifest` compares these fields with your `.env` and offers to fix any that differ:

```bash
dincli model-owner model validate-update-manifest
```

Registration is a request that the DIN-Representative approves. It costs a fee in ETH, paid with the request; check it first:

```bash
dincli system get-registry-fee --fee-type model-registry --model-type open-source   # or proprietary
```

**Model Owner** submits the registration request (uploads the manifest to IPFS and pays the fee):

```bash
dincli task model-owner register-request [--isOpenSource]
# check its status
dincli task model-owner my-requests --include-processed
dincli task model-owner show-registration-request <request_id>
```

**DIN-Representative** reviews and approves (or rejects) it:

```bash
dincli dinrep registry list-pending-requests --type model
dincli dinrep registry explore-request <request_id> --type model
dincli dinrep registry approve-registration-request <request_id>
```

Approval assigns the model ID, which is `totalModels()` at that moment. `approve-registration-request` checks that both task contracts' `modelId()` match it and refuses a mismatch unless `--force` is given.

To change the manifest later (new service CIDs, new parameters), upload the edited manifest with a manifest-update request (it has its own fee, `--fee-type manifest-update`), which the DIN-Representative approves the same way:

```bash
# model owner
dincli task model-owner update-manifest-request <model_id> [--manifestpath <manifest_path> | --manifestCID <manifest_cid>]
# DIN-Representative
dincli dinrep registry list-pending-requests --type manifest
dincli dinrep registry approve-manifest-update <request_id>
```

## 9. Fund and Start the Global Iteration (GI) - Model Owner

After the model is registered, the Model Owner can initiate the Federated Learning process. The FL process is organized into Global Iterations (GI) where aggregators, auditors, and clients interact with the protocol.

Each GI pays its participants from a reward pool, and `gi start` refuses a GI whose pool is empty. Fund the next GI first, either by depositing your own DIN or from the protocol emission schedule:

```bash
# deposit DIN (buy some first with `dincli dintoken buy <eth_amount>`)
dincli model-owner rewards deposit <model_id> --amount <din_amount> [--gi <gi>]
# or fund it from the DinEmission schedule
dincli model-owner rewards fund-emission <model_id> [--gi <gi>]
```

`--gi` defaults to the next GI. Then start it:

```bash
dincli model-owner gi start <model_id> [--threshold <accuracy_deduction>]
```

When pass scoring is enabled, `gi start` uses the test dataset at `<CACHE_DIR>/sepolia_op_devnet/model_<model_id>/dataset/test/test_dataset.pt` to set the pass score. `--threshold` overrides the manifest's accuracy deduction (default 5).

---

## 10. Aggregator Registration - Model Owner & Aggregators

The Model Owner opens aggregator registration. Then, aggregators buy and stake DIN tokens before registering. Once all aggregators have registered, the Model Owner closes the registration.



**Model Owner** opens aggregator registration:

```bash
dincli model-owner gi reg aggregators-open <model_id>
```

**Aggregators** buy tokens, stake, and register (repeat for each aggregator):

```bash
# buy DIN tokens
dincli aggregator dintoken buy 0.00001
# stake DIN tokens
dincli aggregator dintoken stake 10
# read stake
dincli aggregator dintoken read-stake
# register aggregator in current GI
dincli aggregator register <model_id>
```

**Model Owner** reviews and closes aggregator registration:

```bash
# show registered aggregators in current GI
dincli model-owner gi show-registered-aggregators <model_id>
# close aggregator registration
dincli model-owner gi reg aggregators-close <model_id>
```

---

## 11. Auditor Registration - Model Owner & Auditors

Similar to aggregators, the Model Owner opens auditor registration. Auditors stake tokens and register, after which the Model Owner closes registration.

**Model Owner** opens auditor registration:

```bash
dincli model-owner gi reg auditors-open <model_id>
```

**Auditors** buy tokens, stake, register, and register an encryption key (repeat for each auditor):

```bash
# buy DIN tokens
dincli auditor dintoken buy 0.00001
# stake DIN tokens
dincli auditor dintoken stake 10
# read stake
dincli auditor dintoken read-stake
# register auditor in current GI
dincli auditor register <model_id>
# once per wallet: generate an X25519 key and register its public key on DinValidatorStake
dincli auditor register-encryption-key
```

The model owner encrypts each batch's test data to its auditors' keys, so an auditor without a registered key can't be given test data: `create-testdataset --submit` stops before sending anything and names any keyless auditor. A wallet that is an aggregator in this GI can't also register as an auditor.

**Model Owner** reviews and closes auditor registration:

```bash
# show registered auditors in current GI
dincli model-owner gi show-registered-auditors <model_id>
# close auditor registration
dincli model-owner gi reg auditors-close <model_id>
```

---

## 12. Local Model Submission (LMS) - Model Owner & Clients

The Model Owner opens the LMS phase allowing clients to download the genesis/global model, train on their local datasets, and submit their local models.

**Model Owner** opens LMS:

```bash
dincli model-owner lms open <model_id>
```

**Clients** train and then submit their local models (repeat for each client):

```bash
# train a local model in the worker container (nothing is sent on-chain)
dincli client train-lms <model_id>
# upload the trained model to IPFS and submit its CID
dincli client submit-lm <model_id>
# show submitted local model
dincli client lms show-models <model_id>
```

> [!IMPORTANT]
> The client local training data must be  located at `<CACHE_DIR>/sepolia_op_devnet/model_<model_id>/dataset/clients/<account_address>/data.pt`
> where `CACHE_DIR` is the path to the cache directory of the dincli.
> and can be found by running the command `dincli system get-cache-dir`.

**Model Owner** reviews submissions and closes LMS:

```bash
# show submitted local models by clients
dincli model-owner lms show-models <model_id>
# close LMS
dincli model-owner lms close <model_id>
```

---

## 13. Auditor Evaluation - Model Owner & Auditors

The Model Owner prepares evaluation batches and test data, then auditors evaluate the submitted local models to determine their quality and assign scores.

Scores use commit-then-reveal: `evaluate --submit` commits a hidden hash of each score, and auditors reveal them in a separate window the model owner opens. Only revealed scores count.

**Model Owner** prepares evaluation batches and test data, and starts evaluation. The GI state moves `LMSclosed` → `AuditSeedLocked` → `AuditorsBatchesCreated` → `AuditTestDataAssigned` → `LMSevaluationStarted`:

> [!NOTE]
> Auditor batches are drawn from a seed anchored to a future block when LMS
> closes (issue #156), so the model owner can't time the draw. Locking it is
> permissionless: any auditor can run `dincli auditor lock-seed <model_id>`
> once the anchor block is mined, and `lms-evaluation show-batch` does it
> automatically. A successful lock moves the GI to `AuditSeedLocked`. If
> nobody has locked it yet, `auditor-batches create` waits for the block
> (a few seconds on Optimism Sepolia) and locks it first. On the `local`
> network this needs an anvil that produces blocks on its own
> (`foundry/anvil.sh` passes `--block-time`); on an idle anvil the anchor
> block is never mined and the wait never ends.

```bash
# create evaluation batches (locks the seed first if needed)
dincli model-owner auditor-batches create <model_id>
# show evaluation batches
dincli model-owner auditor-batches show <model_id>
# encrypt each batch's test data to its auditors' keys and assign it on-chain
dincli model-owner auditor-batches create-testdataset <model_id> --submit
# start evaluation (opens the commit window)
dincli model-owner lms-evaluation start <model_id>
# show evaluation progress
dincli model-owner lms-evaluation show <model_id> --auditors --models
```

> [NOTE]
> The test dataset  must be located at `<CACHE_DIR>/sepolia_op_devnet/model_<model_id>/dataset/test/test_dataset.pt` for model owner.
> where `CACHE_DIR` is the path to the cache directory of the dincli.
> and can be found by running the command `dincli system get-cache-dir`.

> [NOTE]
> `create-testdataset --submit` is safe to re-run. If some auditor batches failed to
> be assigned, it prints their batch IDs, skips the test-dataset-assigned flag, and
> exits non-zero. Retry just those batches with the repeatable `--batch <id>` option,
> e.g. `dincli model-owner auditor-batches create-testdataset <model_id> --submit --batch 2 --batch 5`.
> The flag itself is one-shot on-chain; re-running after it's already set is detected
> and skipped rather than treated as an error. Setting it moves the GI to
> `AuditTestDataAssigned`, which `lms-evaluation start` requires.

> [!IMPORTANT]
> The first time `create-testdataset --submit` runs, and again after the owner key changes, it writes `owner_encryption_pubkey` into the model-cache manifest at `<CACHE_DIR>/<network>/model_<model_id>/manifest.json`, and only there. Auditors on other machines read the key from the manifest at the on-chain CID, so until it's published they skip decryption and evaluation. Publish it before opening evaluation:
> 1. `dincli task model-owner update-manifest-request <model_id> --manifestpath <CACHE_DIR>/<network>/model_<model_id>/manifest.json`. Point it at the model-cache manifest the command changed, not the task-directory manifest used at registration.
> 2. Wait for the DIN-Representative's `dincli dinrep registry approve-manifest-update <request_id>`.
> 3. Make sure remote auditors have the approved CID before evaluation starts. dincli re-fetches the manifest when its on-chain CID changes.
>
> Only the public key goes in the manifest. Never publish the owner's private key.

> [!NOTE]
> `create-testdataset --submit` saves each batch's key and plaintext hash to
> `<model dir>/audits/testdata_keys/` (mode 0600). Keep them: you need them
> to answer a test-data dispute (`dincli model-owner disputes resolve-test-data`).

**Auditors** evaluate their assigned batches and commit the scores (repeat for each auditor):

```bash
# show the auditor its assigned auditor batches
dincli auditor lms-evaluation show-batch <model_id>
# evaluate every LM in the assigned batches and commit the scores
dincli auditor lms-evaluation evaluate <model_id> --submit
```

**Model Owner** closes the commit window and opens the reveal window:

```bash
dincli model-owner lms-evaluation start-reveal <model_id>
```

**Auditors** reveal their committed scores (repeat for each auditor, from the same machine the commit was made from: the salt is in the local commit cache):

```bash
dincli auditor lms-evaluation reveal <model_id> [--batch <batch_id>] [--lmi <lm_index>]
```

**Model Owner** reviews and closes evaluation:

```bash
# show evaluation results from all auditors
dincli model-owner lms-evaluation show <model_id> --models
# close evaluation
dincli model-owner lms-evaluation close <model_id>
```

An auditor who believes its batch's test data is wrong can open a bonded dispute: `dincli auditor dispute-test-data <model_id> --batch <batch_id>`. See [Disputes](#17-disputes).

---

## 14. Model Aggregation (T1 and T2) - Model Owner & Aggregators

Eligible local models are aggregated hierarchically. Tier 1 (T1) aggregation combines sub-batches, and Tier 2 (T2) aggregation combines the results of T1 into the new global model.

> [!NOTE]
> T1 and T2 aggregation submissions use commit-then-reveal (issue #156
> M-1): `aggregator aggregate-t1/t2 --submit` only **commits** a hidden
> hash of the aggregated CID. The model owner must close the commit
> window and open the reveal window (`aggregation T1/T2 start-reveal`)
> before aggregators can reveal with `aggregator reveal-t1`/`reveal-t2`
> — only revealed CIDs count toward the batch's finalized result. An
> aggregator who commits but never reveals is excluded from finalization
> and is still slashable for a missed submission, exactly as if they had
> never submitted at all.

**Model Owner** generates T1 & T2 batches and starts T1 aggregation. The GI state moves `LMSevaluationClosed` → `AggSeedLocked` → `T1nT2Bcreated` → `T1AggregationStarted`:

> [!NOTE]
> Same as auditor batches above: T1/T2 batches are drawn from a seed
> anchored when evaluation closes. Any aggregator can lock it
> (`dincli aggregator lock-seed <model_id>`, or automatically via
> `show-t1-batches` / `show-t2-batches`), which moves the GI to
> `AggSeedLocked`; otherwise `create-t1nt2-batches` waits and locks it
> first. Same `local`-network block-production caveat.

```bash
# create t1 and t2 batches
dincli model-owner aggregation create-t1nt2-batches <model_id>
# show t1 and t2 batches
dincli model-owner aggregation show-t1-batches <model_id> --detailed
dincli model-owner aggregation show-t2-batches <model_id> --detailed
# start t1 aggregation (opens the commit window)
dincli model-owner aggregation T1 start <model_id>
```

**Aggregators** commit their T1 aggregation (repeat for each aggregator):

```bash
# show the aggregator its assigned t1 batches
dincli aggregator show-t1-batches <model_id> --detailed
# aggregate and commit the assigned t1 batches
dincli aggregator aggregate-t1 <model_id> --submit
```

**Model Owner** opens the T1 reveal window:

```bash
dincli model-owner aggregation T1 start-reveal <model_id>
```

**Aggregators** reveal their committed T1 aggregation (repeat for each aggregator, on the same machine/cache the commit was made from):

```bash
dincli aggregator reveal-t1 <model_id>
```

**Model Owner** closes T1 and starts T2 aggregation:

```bash
# show t1 batches
dincli model-owner aggregation show-t1-batches <model_id> --detailed
# close t1 aggregation
dincli model-owner aggregation T1 close <model_id>
# start t2 aggregation (opens the commit window)
dincli model-owner aggregation T2 start <model_id>
# show t2 batches
dincli model-owner aggregation show-t2-batches <model_id> --detailed
```

**Aggregators** commit their T2 aggregation (repeat for each aggregator):

```bash
# show the aggregator its assigned t2 batches
dincli aggregator show-t2-batches <model_id> --detailed
# aggregate and commit the assigned t2 batches
dincli aggregator aggregate-t2 <model_id> --submit
```

**Model Owner** opens the T2 reveal window:

```bash
dincli model-owner aggregation T2 start-reveal <model_id>
```

**Aggregators** reveal their committed T2 aggregation (repeat for each aggregator, on the same machine/cache the commit was made from):

```bash
dincli aggregator reveal-t2 <model_id>
```

**Model Owner** closes T2 aggregation and scores the new global model:

```bash
# show t2 batches
dincli model-owner aggregation show-t2-batches <model_id> --detailed
# close t2 aggregation
dincli model-owner aggregation T2 close <model_id>
# score the final global model on your test dataset and record the score on-chain
dincli model-owner aggregation T2 set-score <model_id>
```

`set-score` doesn't change the GI state, so run it before slashing: `slash auditors` uses the score, and asks you to confirm if it still reads 0.

Any active validator can dispute a finalized T1 or T2 batch's result within the dispute window by posting a bond: `dincli aggregator dispute <model_id> --tier t1|t2 --batch <batch_id>`. See [Disputes](#17-disputes).

---

## 15. Slashing & End Global Iteration - Model Owner

Any malicious or non-performing actors (auditors or aggregators) are penalized, and the Global Iteration is finalized.

```bash
# show current state
dincli task gi show-state <model_id>
# slash auditors
dincli model-owner slash auditors <model_id>
# slash aggregators
dincli model-owner slash aggregators <model_id>
# end global iteration (settles the GI's rewards)
dincli model-owner gi end <model_id>
```

The GI is now `GIended`. Fund the next GI (step 9) to start it.

## 16. Claim Rewards and Release Slots - Participants & Model Owner

Ending the GI settles its reward pool. Each client, auditor and aggregator credits its share and then withdraws it:

```bash
# credit your share of a settled GI
dincli rewards claim <model_id> --gi <gi>
# transfer your whole claimable balance to your wallet
dincli rewards withdraw <model_id>
```

**Model Owner** releases the ended GI's validator registration slots, once per GI. Until then those registrations count against each validator's concurrent-registration cap:

```bash
dincli model-owner gi release-slots <model_id> [--gi <gi>]
```

## 17. Disputes

Both kinds of dispute are bonded: the challenger posts a DIN bond, which is forfeited if the dispute fails.

**Test data.** An auditor of a batch can dispute that batch's test data (for example, it received no key) until the GI's rewards settle at `gi end`:

```bash
# auditor
dincli auditor dispute-test-data <model_id> --batch <batch_id>
# model owner, within the dispute window: reveal the batch key and plaintext hash
dincli model-owner disputes resolve-test-data <model_id> --gi <gi> --batch <batch_id>
# anyone, once the window has passed without an answer
dincli model-owner disputes close-expired <model_id> --gi <gi> --batch <batch_id>
```

If the revealed key matches the commitment, the dispute fails and the bond is forfeited. If it doesn't, or the owner never answers (`close-expired`), the dispute is upheld: the bond goes back to the auditor, and the owner must assign new test data with `dincli model-owner disputes reassign-test-data <model_id> --batch <batch_id>`. An upheld dispute also takes part of the GI's reward pool as a penalty, but only while the GI's rewards are unsettled. `gi end` settles them and doesn't wait for open disputes, so if a dispute is upheld after that, the penalty is zero. To make the penalty apply, resolve or close pending test-data disputes before ending the GI.

**Aggregation.** Any active validator can dispute a finalized T1 or T2 batch's CID within the dispute window:

```bash
# challenger
dincli aggregator dispute <model_id> --tier t1|t2 --batch <batch_id>
# model owner: reject it (bond forfeited), or uphold it, which assigns a fresh subgroup of 3 aggregators
dincli model-owner disputes resolve-aggregation <model_id> --gi <gi> --tier t1|t2 --batch <batch_id> --upheld|--rejected
# model owner, after the off-chain recomputation: confirm (the original aggregators whose revealed CID matched the disputed one are slashed) or dismiss (bond forfeited)
dincli model-owner disputes settle-recomputation <model_id> --gi <gi> --tier t1|t2 --batch <batch_id> --confirmed|--dismissed
# anyone, past the resolution deadline: the fresh subgroup is slashed
dincli model-owner disputes expire <model_id> --gi <gi> --tier t1|t2 --batch <batch_id>
```

> [!WARNING]
> Upholding a dispute only records the fresh subgroup on-chain. It doesn't reopen the GI for them, and they have no on-chain way to submit a recomputation. The model owner has to coordinate the evidence and recomputation with them off-chain and call `settle-recomputation` before anyone calls `expire`. After `resolutionDeadline`, anyone can call `expire`, which slashes all three fresh-subgroup members for liveness even though they couldn't submit anything. `settle-recomputation` has no deadline check, so the owner can still call it after the deadline, but only until someone expires the dispute.

A confirmed recomputation or an expired dispute credits the bond back to the challenger, who withdraws it with `dincli aggregator claim-dispute-bond <model_id>`. A batch can be disputed only once.
