# DIN-Representative Documentation

The DIN-Representative administers the core infrastructure contracts of the DIN network. This includes deploying the platform contracts, approving model registrations and manifest updates, setting registry fees, and authorizing participants (slashers) who can penalize misbehaving validators.

Today the DIN-Representative is a single admin key: the `owner()` of the platform contracts. On-chain DIN-DAO governance is deferred to post-mainnet; until then, governance happens off-chain.

The CLI commands for this role live under `dincli dinrep`.

---

## 1. Deployment

The platform contracts (`DinTreasury`, `DinToken`, `DinCoordinator`, `DinValidatorStake`, `DINModelRegistry`, `DinFeeRouter`, `DinEmission`) are deployed behind OpenZeppelin Transparent Proxies by the Foundry script `foundry/script/DeployPlatform.s.sol`. The script also initializes and wires the contracts, then writes the proxy and ProxyAdmin addresses to `foundry/deployments/<network>.json`. After it runs, import that file into `dincli`.

The output file is named after the chain the script ran against:

| Chain | Chain ID | Deployments file |
|-------|----------|------------------|
| Local anvil / hardhat node | 1337 / 31337 | `foundry/deployments/localhost.json` |
| Optimism Sepolia | 11155420 | `foundry/deployments/sepolia_op_devnet.json` |

On any other chain the script reverts unless you set `DEPLOYMENTS_NETWORK=<name>` to choose the file name.

> [!NOTE]
> Both flows run from the repo root and need `npm ci` in `foundry/` first. The OpenZeppelin upgrade-safety validation that runs during the deploy calls `npx @openzeppelin/upgrades-core` from `foundry/node_modules`.

### 1a. Local network (anvil)

**1. Start a local chain.** `anvil.sh` runs a private chain (chain ID 1337) on `http://127.0.0.1:8545` with pre-funded dev accounts:

```bash
./foundry/anvil.sh
```

**2. Deploy.** `--unlocked` lets anvil sign for its dev account 0, so no private key is needed:

```bash
cd foundry && npm ci
forge clean
forge script script/DeployPlatform.s.sol \
  --rpc-url http://127.0.0.1:8545 \
  --broadcast \
  --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 \
  --unlocked
cd ..
```

This writes `foundry/deployments/localhost.json`. That file is gitignored, because it is regenerated on every local deploy.

**3. Import into dincli:**

```bash
dincli --network local system import-deployments
```

### 1b. Optimism Sepolia

Optimism Sepolia is a public chain, so there is no anvil step. Instead you need an RPC endpoint and a funded signing key.

**1. Prerequisites**

- **RPC endpoint.** Use the same endpoint dincli uses: `SEPOLIA_OP_DEVNET_RPC_URL` in `.env.sepolia_op_devnet` at the repo root. The file is gitignored, so create it from [`.env.example`](../../../.env.example) if you don't have one yet. Load it into your shell:

  ```bash
  set -a; source .env.sepolia_op_devnet; set +a
  ```

- **Signing key.** Import the DIN-Representative key into Foundry's encrypted keystore once. This prompts for the private key and a password:

  ```bash
  cast wallet import <keystore_name> --interactive
  cast wallet address --account <keystore_name>    # prints the DIN-Representative address
  ```

  The deploying address becomes the owner of every platform contract and every ProxyAdmin, so use the DIN-Representative key.

- **Funds.** The address needs Optimism Sepolia ETH. A full deploy is 22 transactions: seven implementations, seven proxies, and eight wiring calls. Each proxy creates its own ProxyAdmin inside its constructor, so the ProxyAdmins need no transactions of their own.

- **Tokenomics parameters.** `DeployPlatform.s.sol` reads 11 tokenomics settings from the environment: `DIN_PER_ETH`, `MINT_CAP`, the four `EMISSION_*` keys, `MIN_STAKE`, the three `S5_*` keys and `S6_NO_PARTICIPATION_THRESHOLD`. Any key that isn't set falls back to the in-code default; for example, `MINT_CAP` defaults to `0`, which means uncapped. Set the values chosen for this network in `.env.sepolia_op_devnet` (loaded above) or in `foundry/.env` (forge loads it automatically). The script logs an `[INFO] <KEY> not set` line for each missing key and ends with a `--- Effective tokenomics ---` block. See [DeployPlatform.md](../../technical/contracts/foundry/script/DeployPlatform.md) for every key and its default.

**2. Deploy:**

```bash
cd foundry && npm ci
forge clean
forge script script/DeployPlatform.s.sol \
  --rpc-url "$SEPOLIA_OP_DEVNET_RPC_URL" \
  --broadcast \
  --account <keystore_name> \
  --sender <din_representative_address>
cd ..
```

To also verify the contracts on the block explorer, add `--verify --etherscan-api-key "$ETHERSCAN_API_KEY"`.

Alternatively, `--rpc-url optimism-sepolia` uses the `foundry.toml` RPC alias. That alias builds an Infura URL from `INFURA_API_KEY`, which forge loads automatically from `foundry/.env` (gitignored), so it works without sourcing `.env.sepolia_op_devnet`. In that case, put any tokenomics overrides in `foundry/.env` too.

This writes `foundry/deployments/sepolia_op_devnet.json`. Unlike `localhost.json`, this file is not gitignored: commit it, because it is the network's public record of the platform addresses.

> [!TIP]
> Run once without `--broadcast` first. Forge then only simulates the deploy against the live chain state, so you can check the sender, the balance, the upgrade-safety validation, and the `--- Effective tokenomics ---` values without spending gas.

**3. Import into dincli:**

```bash
dincli --network sepolia_op_devnet system import-deployments
```

### Import options

`import-deployments` reads `foundry/deployments/<network>.json` for the active dincli network by default. The other sources are:

```bash
dincli system import-deployments --file <path_to_deployments_json>   # any explicit file
dincli system import-deployments --hardhat                           # hardhat/deployments/<network>.json
```

`--hardhat` reads output from the secondary Hardhat toolchain (`cd hardhat && npx hardhat run scripts/deploy-platform.ts --network <network>`).

> [!NOTE]
> Native proxy deployment from `dincli` (`dincli dinrep deploy ...`) is planned but not implemented yet. See [dincli-native-proxy-deployment.md](../../../Developer/issues/dincli-native-proxy-deployment.md).

---

## 2. Registry Management

### View Total Models

Check how many models are currently approved in the network.

```bash
dincli dinrep registry total-models
```

---

### Model Registration Approval

Model registration follows a **request → approval** flow. Model Owners submit requests, and the DIN-Representative approves or rejects each one.

**List pending requests** (model registrations and manifest updates; `-t` narrows the list to one type):

```bash
dincli dinrep registry list-pending-requests [-t model|manifest]
```

**Inspect a single request:**

```bash
dincli dinrep registry explore-request -t model <requestId>
```

**Approve a model registration request:**

```bash
dincli dinrep registry approve-registration-request <requestId>
```

> [!IMPORTANT]
> Approval revalidates the coordinator and auditor contracts at the time of the call. If either contract has lost slasher status or been transferred to a different owner since the request was submitted, the transaction will revert. The requester must submit a new request.

**Reject a model registration request:**

```bash
dincli dinrep registry reject-registration-request <requestId>
```

The registration fee is retained by the contract in both cases.

---

### Manifest Update Approval

Manifest updates also follow a request → approval flow. Use `explore-request -t manifest <requestId>` to inspect a request before deciding.

**Approve a manifest update:**

```bash
dincli dinrep registry approve-manifest-update <requestId>
```

> [!NOTE]
> Approving a manifest update for a disabled model will revert. Enable the model first if the update is intentional.

**Reject a manifest update:**

```bash
dincli dinrep registry reject-manifest-update <requestId>
```

---

### Kill Switch — Disable / Enable Models

Disable a model immediately. A disabled model's owner can't submit manifest update requests, and pending updates for it can't be approved.

```bash
# Disable a model (emergency stop)
dincli dinrep registry disable-model <modelId>

# Re-enable a model
dincli dinrep registry enable-model <modelId>
```

> [!CAUTION]
> Disabling a model does not delete it. All on-chain history is preserved. Today the task contracts (`DINTaskCoordinator`, `DINTaskAuditor`) do **not** check `modelDisabled(modelId)`, so disabling only blocks manifest updates. It does not stop the model's running GIs, submissions or slashing.

---

## 3. Fee Governance

The registry charges fees for model registration and manifest update requests. All four fee parameters are controlled by the DIN-Representative.

| Parameter | Default | Applies To |
|-----------|---------|-----------|
| `openSourceFee` | 0.000001 ETH | Open-source model registration |
| `proprietaryFee` | 0.00001 ETH | Proprietary model registration |
| `openSourceUpdateFee` | 0.0000001 ETH | Open-source manifest update requests |
| `proprietaryUpdateFee` | 0.000001 ETH | Proprietary manifest update requests |

**Update a single fee** (amounts in ETH):

```bash
dincli dinrep registry set-open-source-fee <eth>
dincli dinrep registry set-proprietary-fee <eth>
dincli dinrep registry set-open-source-update-fee <eth>
dincli dinrep registry set-proprietary-update-fee <eth>
```

**Update all fees atomically** (amounts in ETH):

```bash
dincli dinrep registry set-fees \
  --open-source <eth> \
  --proprietary <eth> \
  --open-source-update <eth> \
  --proprietary-update <eth>
```

### Sweep Accumulated Fees

Collected ETH stays in the contract that received it until the DIN-Representative sweeps it to `DinFeeRouter`. There are two sweep commands:

```bash
# Model registration and manifest update fees held by DINModelRegistry
dincli dinrep registry sweep-fees

# ETH that DinCoordinator received from DIN purchases (depositAndMint)
dincli dinrep coordinator sweep-fees
```

- **Owner only:** the active wallet must be the contract's owner, i.e. the DIN-Representative wallet.
- **Router wiring:** `foundry/script/DeployPlatform.s.sol` connects both contracts to the fee router when it deploys them. The CLI has no command for changing the router.
- **Fee-source check:** the router only accepts sweeps from contracts it has authorised as fee sources. The deploy script authorises both. The command checks this before the preview. If the contract has since been removed with `removeFeeSource`, the DinFeeRouter owner must call `addFeeSource(<contract address>)` again; dincli has no command for that yet.
- **Preview and confirmation:** each command reads the router's current `ethSplit`, shows how much will go to each bucket, and asks before sending. Pass `--yes` to skip the prompt.
- **One sweep moves the whole balance.**

> [!WARNING]
> **Only the Treasury share leaves the router.** With the default `ethSplit` (validator pool 95%, Treasury 5%), the Treasury receives 5% of each sweep. The validator-pool, storage and public-goods shares stay in `DinFeeRouter` as `accruedEth`, and nothing can withdraw them yet: that waits on the future P3-5.2 / RES-1 consumers. A sweep can't be reversed, so treat swept non-Treasury ETH as locked until those consumers ship.

---

## 4. Slasher Management

Slashers are contracts authorized to penalize misbehaving participants. The Task Coordinator and Task Auditor contracts must be registered as slashers before they can enforce penalties.

### Register Task Coordinator as a Slasher

> **Prerequisite** — the following key must be set in your `.env` file:
> - `<NETWORK>_DINTaskCoordinator_Contract_Address`  
>   *(e.g. `SEPOLIA_OP_DEVNET_DINTaskCoordinator_Contract_Address`)*

```bash
dincli dinrep add-slasher --taskCoordinator
```

### Register Task Auditor as a Slasher

> **Prerequisite** — the following keys must be set in your `.env` file:
> - `<NETWORK>_DINTaskCoordinator_Contract_Address`  
>   *(e.g. `SEPOLIA_OP_DEVNET_DINTaskCoordinator_Contract_Address`)*
> - `<NETWORK>_<TASK_COORDINATOR_ADDRESS>_DINTaskAuditor_Contract_Address`  
>   *(e.g. `SEPOLIA_OP_DEVNET_0x1234...7890_DINTaskAuditor_Contract_Address`)*

```bash
dincli dinrep add-slasher --taskAuditor
```

### Register by Address Directly

If you already know the contract address, you can pass it explicitly instead of relying on the `.env` file:

```bash
dincli dinrep add-slasher --contract <contract_address>
```

---

## Workflow

1. **Deploy** — Run the Foundry `DeployPlatform.s.sol` script (§1a local, §1b Optimism Sepolia), then `dincli system import-deployments`.
2. **Configure Slashers** — After each new task is created, register its Task Coordinator and Task Auditor as slashers.
3. **Process Registration Requests** — Review pending `ModelRequest` entries; approve or reject each one.
4. **Process Manifest Update Requests** — Review pending `ManifestUpdateRequest` entries.
5. **Monitor** — Use registry commands to track network growth and model status.
6. **Emergency** — Use `disable-model` if a model needs to be stopped immediately.
