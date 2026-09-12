# DIN DAO Documentation

The DIN DAO (Decentralized Autonomous Organization) administers the core infrastructure contracts of the DIN network. This includes deploying the fundamental contracts and authorizing participants (slashers) who can penalize misbehaving validators.

---

## 1. Deployment

Deploy the core contracts in the order listed below. Each contract depends on the previous one being live.

> [!NOTE]
> The `--artifact` flag must point to the compiled JSON output from Hardhat/ Foundry (contains the ABI and bytecode).

### 1. DIN Coordinator

The main coordinator contract that governs network-wide operations.

```bash
dincli dindao deploy din-coordinator --artifact <path_to_artifact>
```

### 2. Validator Stake

The staking contract used by validators (Auditors, Aggregators).

```bash
dincli dindao deploy din-validator-stake --artifact <path_to_artifact>
```

### 3. Model Registry

Records federated learning tasks, assigns a unique `model_id` to each task, and stores the initial global model reference and manifest for a task.

```bash
dincli dindao deploy din-model-registry --artifact <path_to_artifact>
```

---

## 2. Registry Management

### View Total Models

Check how many models are currently approved in the network.

```bash
dincli dindao registry total-models
```

---

### Model Registration Approval

Model registration follows a **request → approval** flow. Model Owners submit requests; the DAO reviews and approves or rejects them.

**List pending registration requests:**

```bash
dincli dindao registry list-requests [--pending]
```

**Approve a model registration request:**

```bash
dincli dindao registry approve-model <requestId>
```

> [!IMPORTANT]
> Approval revalidates the coordinator and auditor contracts at the time of the call. If either contract has lost slasher status or been transferred to a different owner since the request was submitted, the transaction will revert. The requester must submit a new request.

**Reject a model registration request:**

```bash
dincli dindao registry reject-model <requestId>
```

The registration fee is retained by the contract in both cases.

---

### Manifest Update Approval

Manifest updates also follow a request → approval flow.

**Approve a manifest update:**

```bash
dincli dindao registry approve-manifest-update <requestId>
```

> [!NOTE]
> Approving a manifest update for a disabled model will revert. Enable the model first if the update is intentional.

**Reject a manifest update:**

```bash
dincli dindao registry reject-manifest-update <requestId>
```

---

### Kill Switch — Disable / Enable Models

Disable a model immediately. This blocks manifest update requests from the model owner and should be checked by downstream contracts (`TaskCoordinator`, `TaskAuditor`) before executing any model tasks.

```bash
# Disable a model (emergency stop)
dincli dindao registry disable-model <modelId>

# Re-enable a model
dincli dindao registry enable-model <modelId>
```

> [!CAUTION]
> Disabling a model does not delete it. All on-chain history is preserved. Downstream contracts must actively check `modelDisabled(modelId)` for the kill switch to have operational effect.

---

## 3. Fee Governance

The registry charges fees for model registration and manifest update requests. All four fee parameters are DAO-controlled.

| Parameter | Default | Applies To |
|-----------|---------|-----------|
| `openSourceFee` | 0.000001 ETH | Open-source model registration |
| `proprietaryFee` | 0.00001 ETH | Proprietary model registration |
| `openSourceUpdateFee` | 0.0000001 ETH | Open-source manifest update requests |
| `proprietaryUpdateFee` | 0.000001 ETH | Proprietary manifest update requests |

**Update a single fee:**

```bash
dincli dindao registry set-fee --open-source-fee <wei>
dincli dindao registry set-fee --proprietary-fee <wei>
dincli dindao registry set-fee --open-source-update-fee <wei>
dincli dindao registry set-fee --proprietary-update-fee <wei>
```

**Update all fees atomically (preferred for governance proposals):**

```bash
dincli dindao registry set-fees \
  --open-source-fee <wei> \
  --proprietary-fee <wei> \
  --open-source-update-fee <wei> \
  --proprietary-update-fee <wei>
```

**Withdraw accumulated fees:**

```bash
dincli dindao registry withdraw-fees --to <address>
```

---

## 4. Slasher Management

Slashers are contracts authorized to penalize misbehaving participants. The Task Coordinator and Task Auditor contracts must be registered as slashers before they can enforce penalties.

### Register Task Coordinator as a Slasher

> **Prerequisite** — the following key must be set in your `.env` file:
> - `<NETWORK>_DINTaskCoordinator_Contract_Address`  
>   *(e.g. `SEPOLIA_OP_DEVNET_DINTaskCoordinator_Contract_Address`)*

```bash
dincli dindao add-slasher --taskCoordinator
```

### Register Task Auditor as a Slasher

> **Prerequisite** — the following keys must be set in your `.env` file:
> - `<NETWORK>_DINTaskCoordinator_Contract_Address`  
>   *(e.g. `SEPOLIA_OP_DEVNET_DINTaskCoordinator_Contract_Address`)*
> - `<NETWORK>_<TASK_COORDINATOR_ADDRESS>_DINTaskAuditor_Contract_Address`  
>   *(e.g. `SEPOLIA_OP_DEVNET_0x1234...7890_DINTaskAuditor_Contract_Address`)*

```bash
dincli dindao add-slasher --taskAuditor
```

### Register by Address Directly

If you already know the contract address, you can pass it explicitly instead of relying on the `.env` file:

```bash
dincli dindao add-slasher --contract <contract_address>
```

---

## 5. DAO Admin Transfer

The DAO admin role can be transferred to a multisig or on-chain timelock without redeploying the registry.

```bash
dincli dindao registry set-admin <new_admin_address>
```

> [!CAUTION]
> This action is irreversible from the old admin address. Confirm the new address is correct before proceeding.

---

## Workflow

1. **Deploy** — Coordinator → Validator Stake → Model Registry (in order).
2. **Configure Slashers** — After each new task is created, register its Task Coordinator and Task Auditor as slashers.
3. **Process Registration Requests** — Review pending `ModelRequest` entries; approve or reject each one.
4. **Process Manifest Update Requests** — Review pending `ManifestUpdateRequest` entries.
5. **Monitor** — Use registry commands to track network growth and model status.
6. **Emergency** — Use `disable-model` if a model needs to be stopped immediately.

