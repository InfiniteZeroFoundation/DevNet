# DIN DAO Documentation

The DIN DAO (Decentralized Autonomous Organization) role involves deploying and managing the core infrastructure contracts of the network.

## Deployment

Deploy the fundamental contracts that govern the DIN ecosystem.

### DIN Coordinator
Deploy the main coordinator contract.

```bash
dincli dindao deploy din-coordinator --artifact <path_to_artifact>
```

### Validator Stake
Deploy the staking contract for validators.

```bash
dincli dindao deploy din-validator-stake  --artifact <path_to_artifact>
```

### Model Registry
Deploy the registry where a federated learning task is recorded with initial global model and the model id is assigned to the learning task.

```bash
dincli dindao deploy din-model-registry --artifact <path_to_artifact>
```

*Note: The `--artifact` path should point to the compiled JSON output from Hardhat with the abi and bytecode.*

## Registry Management

### View Total Models
Check the number of models registered in the system.

```bash
dincli dindao registry total-models
```

## Slasher Management

Authorize contracts to act as slashers within the DIN system.

### Add Slasher
Register a Task Coordinator as a valid slasher.

> **Prerequisite**: The following key must be set in your `.env` file:
> `<NETWORK>_DINTaskCoordinator_Contract_Address`
> (e.g. `SEPOLIA_DEVNET_DINTaskCoordinator_Contract_Address`)

```bash
# Register the Task Coordinator as a slasher
dincli dindao add-slasher --taskCoordinator
```

Register Task Auditor as a slasher

> **Prerequisite**: The following key must be set in your `.env` file:
> `<NETWORK>_DINTaskCoordinator_Contract_Address`
> (e.g. `SEPOLIA_DEVNET_DINTaskCoordinator_Contract_Address`)
> `<NETWORK>_<TASK_COORDINATOR_ADDRESS>_DINTaskAuditor_Contract_Address`
> (e.g. `SEPOLIA_DEVNET_0x1234567890123456789012345678901234567890_DINTaskAuditor_Contract_Address`)

```bash
# Register the Task Auditor as a slasher
dincli dindao add-slasher --taskAuditor
```

**Alternative**: If you already have the contract address, you can pass it directly with `--contract` instead:

```bash
dincli dindao add-slasher --contract <contract_address>
```

## Workflow

1. **Deploy**: Deploy Coordinator -> Stake -> Registry in that order.
2. **Configure**: Add slashers as new tasks are created (Task Coordinators/Auditors need permission to slash).
3. **Monitor**: Use registry commands to track network growth.
