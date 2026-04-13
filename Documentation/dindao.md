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

Check how many models are currently registered in the network.

```bash
dincli dindao registry total-models
```

---

## 3. Slasher Management

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

## Workflow

1. **Deploy** — Coordinator → Validator Stake → Model Registry (in order).
2. **Configure Slashers** — After each new task is created, register its Task Coordinator and Task Auditor as slashers.
3. **Monitor** — Use registry commands to track network growth.
