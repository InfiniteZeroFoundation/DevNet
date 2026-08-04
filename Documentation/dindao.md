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

## 5a. Ownership-Transfer Runbook — Stage B Activation (devnet 3.0)

This runbook transfers `owner()` of each platform contract from the DIN-Representative
EOA to the appropriate `DinTimelock` instance. Execute steps in the exact order listed.
The entire sequence must be rehearsed on Optimism Sepolia devnet before any testnet
deployment.

### Prerequisites

- `DinMultisig` deployed with production signers and thresholds verified.
- `DinTimelockShort` (24 h delay) deployed; `DinMultisig` holds `PROPOSER_ROLE` and
  `CANCELLER_ROLE`; `DEFAULT_ADMIN_ROLE` renounced.
- `DinTimelockLong` (48 h delay) deployed; same role wiring as above.
- Both timelocks verified on Optimism Sepolia Blockscout.
- All four platform contract proxies deployed (PR #13): `DinCoordinator`,
  `DinToken`, `DinValidatorStake`, `DINModelRegistry`.

### Step 1 — Transfer DINModelRegistry ownership

`DINModelRegistry` uses OZ two-step `Ownable2Step`. Initiate from the DIN-Representative
EOA, then accept from the timelock side via a scheduled call.

```bash
# 1a. Initiate transfer (DIN-Representative signs)
dincli dindao registry set-admin <DinTimelockLong_address>

# 1b. Build the acceptance call and schedule it through DinMultisig
#     Target:   DINModelRegistry proxy address
#     Calldata: acceptOwnership()
#     Category: Upgrade
#     Timelock: DinTimelockLong (48 h)
```

After the 48 h delay, execute the scheduled timelock operation. Verify:
```bash
# Confirm new owner
cast call <DINModelRegistry_proxy> "owner()(address)" --rpc-url $RPC
# Expected: DinTimelockLong address
```

> [!IMPORTANT]
> Do not proceed to Step 2 until Step 1 is confirmed on-chain.

### Step 2 — Transfer DinValidatorStake ownership

```bash
# DIN-Representative initiates
cast send <DinValidatorStake_proxy> "transferOwnership(address)" \
  <DinTimelockLong_address> \
  --private-key $DIN_REP_KEY --rpc-url $RPC

# Schedule acceptance through DinMultisig (Upgrade category → DinTimelockLong)
# Calldata: acceptOwnership() on DinValidatorStake proxy
```

Verify after 48 h execution:
```bash
cast call <DinValidatorStake_proxy> "owner()(address)" --rpc-url $RPC
# Expected: DinTimelockLong address
```

### Step 3 — Transfer DinCoordinator ownership

```bash
cast send <DinCoordinator_proxy> "transferOwnership(address)" \
  <DinTimelockLong_address> \
  --private-key $DIN_REP_KEY --rpc-url $RPC

# Schedule acceptance (Upgrade category → DinTimelockLong)
```

### Step 4 — Transfer DinToken ownership

`DinToken` ownership controls the mint-authority wiring to `DinCoordinator`.
Transfer to `DinTimelockLong`.

```bash
cast send <DinToken_proxy> "transferOwnership(address)" \
  <DinTimelockLong_address> \
  --private-key $DIN_REP_KEY --rpc-url $RPC
```

### Step 5 — Transfer ProxyAdmin ownership (upgrade governance)

The `ProxyAdmin` created in PR #13 controls implementation upgrades for all four
proxy contracts. Transfer it to `DinTimelockLong`.

```bash
cast send <ProxyAdmin_address> "transferOwnership(address)" \
  <DinTimelockLong_address> \
  --private-key $DIN_REP_KEY --rpc-url $RPC
```

> [!CAUTION]
> After this step, no platform contract upgrade can proceed without a successful
> governance proposal through `DinTimelockLong`. Ensure the multisig signers are
> active and the timelock role wiring is verified before completing this step.

### Step 6 — Verify end state

```bash
# All four contracts should report DinTimelockLong as owner
for PROXY in $COORDINATOR $VALIDATOR_STAKE $MODEL_REGISTRY $DIN_TOKEN; do
  echo "Owner of $PROXY:"
  cast call $PROXY "owner()(address)" --rpc-url $RPC
done

# ProxyAdmin owner
cast call $PROXY_ADMIN "owner()(address)" --rpc-url $RPC
```

### Rollback

If the ownership transfer must be reversed before `acceptOwnership()` is called:
1. The pending transfer can be cancelled by calling `transferOwnership(address(0))` on
   the relevant contract from the still-active DIN-Representative EOA.
2. Once `acceptOwnership()` has been called by the timelock (Step 1b etc.), the transfer
   is complete and cannot be rolled back via EOA. Recovery requires a governance proposal
   through the timelock to call `transferOwnership` again.

This is why the runbook must be rehearsed end-to-end on devnet before mainnet execution.

---

## Workflow

1. **Deploy** — Coordinator → Validator Stake → Model Registry (in order).
2. **Configure Slashers** — After each new task is created, register its Task Coordinator and Task Auditor as slashers.
3. **Process Registration Requests** — Review pending `ModelRequest` entries; approve or reject each one.
4. **Process Manifest Update Requests** — Review pending `ManifestUpdateRequest` entries.
5. **Monitor** — Use registry commands to track network growth and model status.
6. **Emergency** — Use `disable-model` if a model needs to be stopped immediately.
7. **Stage B Activation** — See §5a for the ordered runbook to transfer ownership to the timelocks.

