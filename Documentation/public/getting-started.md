# Model_0 — Infinite Zero Network Protocol

> [!TIP]
> Hit an error or get stuck anywhere in this guide? Post it in the
> [DevNet 2.0 pre-launch discussion](https://github.com/InfiniteZeroFoundation/DevNet/discussions/102).

Welcome to the onboarding guide for **Model_0** on the Infinite Zero Network.

Infinite Zero Network devnet has been launched as `sepolia-op-devnet`.

Model_0 is the first active model registered on the Infinite Zero Network and serves as the pioneer deployment of Infinite Zero's  model-specific smart contracts.

The Infinite Zero Network coordinates decentralized AI training, auditing, aggregation, and validation through Ethereum smart contracts, off-chain distributed compute, and decentralized storage.

---

# 🧭 Protocol Overview

Model_0 operates through recurring **Global Iterations (GI)**.

Each Global Iteration represents a complete decentralized training cycle coordinated by Ethereum smart contracts.

A typical iteration includes:

1. Clients train local models on their own datasets
2. Local model updates are submitted to IPFS and referenced on-chain
3. Auditors independently evaluate the submitted local models and approve (or reject) them.
4. Approved local models are batched and assigned to aggregators for aggregation.
5. Aggregators aggregate assigned T1 and subsequently T2 aggregation batches.
6. The resulting global model is finalized and published
7. The next iteration begins using the updated global model

This process enables decentralized, verifiable, and scalable collaborative AI training without centralizing participant data.

---

# 🌐 What is `sepolia-op-devnet`?

To simplify onboarding, we refer to our devnet as:

> **`sepolia-op-devnet` = Optimism Sepolia testnet + DIN deployed contracts**

So when you see:

```env
SEPOLIA_OP_DEVNET_RPC_URL=<your_rpc_url>
```

It means:

* You are connecting to **Optimism Sepolia**
* And interacting specifically with **DIN protocol contracts deployed there**

---


# Current Status

* ✅ Global Iteration 1 completed
* 🔄 Global Iteration 2 in progress

---

# 🔐 Security Model

The Infinite Zero Network is secured by Ethereum smart contracts deployed on Sepolia OP Devnet.

Ethereum acts as the source of truth for:

* Participant registration
* State transitions
* Submission coordination
* Staking logic
* Validation rules
* Protocol enforcement

### On-chain responsibilities

| Layer               | Responsibility                               |
| ------------------- | -------------------------------------------- |
| Ethereum (on-chain) | Coordination, state, validation, enforcement |
| IPFS/Filebase       | Model artifacts and decentralized storage    |
| Off-chain compute   | Training, aggregation, auditing              |
| Participants        | Execute computation and submit results       |

---

### Core guarantee

The system is **fully verifiable end-to-end**:

- Ethereum enforces correctness, coordination, and finality  
- IPFS ensures reproducible and distributed data availability  
- Off-chain compute enables scalable ML execution  

> 💡 Trust is shifted from participants to cryptographic and economic enforcement.

# 📦 Data Availability Layer (IPFS via Filebase)

The protocol uses IPFS (commonly through Filebase) as a decentralized storage layer for protocol artifacts.

This includes:

* Local model uploads
* Aggregated/global model artifacts
* Manifest or scripts artifacts
* Aggregation outputs


---

# 🎭 Participation Model

Participants may operate as one or more of the following roles simultaneously:

1. Aggregators
    - Aggregate Tier 1 and Tier 2 batches of models
2. Auditors
    - Independently evaluate the submitted local models and approve (or reject) them.
3. Clients
    - Train local models on local datasets
    - Submit local model updates to the network

> 💡 A single participant may act as Client, Auditor, and Aggregator simultaneously using multiple accounts.

---

# 🧠 Validator Model (No Mining)

This system does not use mining or Proof-of-Work.

Instead, it uses a role-based validation model coordinated through Ethereum smart contracts on `sepolia-op-devnet`.

* Clients train and submit local model updates
* Auditors independently evaluate the submitted local models and approve (or reject) them.
* Approved model updates are batched and assigned to aggregators
* Aggregators aggregate assigned T1 and subsequently T2 aggregation batches.
* Ethereum finalizes accepted protocol state transitions

> 💡 Aggregators and Auditors collectively function as validators.

---

# 💻 System Requirements

Participating in Model_0 on the Infinite Zero Network is lightweight and does not require specialized hardware.

### Minimum Requirements

* RAM: 4 GB
* Disk: ~30 GB
* CPU: Standard CPU (GPU not required)
* Python 3 + virtual environment

### Dependencies

* `dincli`
* Python ML/runtime dependencies (~5 GB virtual environment)

> 💡 Typical setup time is around 10–15 minutes for users familiar with Python environments.

---

# ⚠️ Current Devnet Scope

The current devnet primarily focuses on:

* Decentralized coordination
* Distributed training
* Aggregation workflows
* Validation workflows
* Ethereum-enforced protocol state transitions

Staking and slashing concepts exist within the protocol architecture.

Economic and reward distribution mechanisms are still under active development and are not yet the primary focus of the current devnet phase.

---

# 🌐 Community Channels

### Telegram

* Announcements
* Coordination
* Community support

https://t.me/+I4Tl7foCVwwwM2Vk

### Signal

* Technical discussions
* Coordination
* Protocol updates

https://signal.group/#CjQKICVqJ0Ri3KGCZOsf8A3dhmg8GC_vc1MBmBrq0JV7lIr6EhBCOwElVHvE0swjO8kSk7ky

> ⚠️ Global Iteration updates and onboarding assistance are shared regularly.

---

## Faucet Access (Sepolia Optimism)

To participate in the Infinite Zero Network devnet, you will need Sepolia Optimism ETH for transaction fees.

You can request testnet tokens from the following official faucets:

* [Optimism Faucet](https://console.optimism.io/faucet)
* [Chainlink Faucet (Optimism Sepolia)](https://faucets.chain.link/optimism-sepolia)
* [LearnWeb3 Faucet](https://learnweb3.io/faucets/optimism_sepolia/)
* [ETHGlobal OP Sepolia Faucet](https://ethglobal.com/faucet/op-sepolia-11155420)
* [Alchemy Optimism Sepolia Faucet](https://www.alchemy.com/faucets/optimism-sepolia)

If you are unable to obtain funds through the faucets above, you may also request Sepolia Optimism ETH through the Infinite Zero Foundation Telegram and Signal community groups.

---


# ⚙️ DIN CLI Installation and Setup

Before participating, ensure dincli is correctly installed and configured.

Please read:

https://github.com/InfiniteZeroFoundation/DevNet/blob/develop/Documentation/public/setup.md

### Initialize DIN CLI

```bash
dincli system init
```

### Environment Configuration

Set RPC URL in `.env`:

```env
SEPOLIA_OP_DEVNET_RPC_URL=<your_rpc_url>
```

Add Ethereum private keys:

> **⚠️ Local development only.** The `ETH_PRIVATE_KEY_<n>` pattern stores raw
> private keys in plaintext. Production validators: use the encrypted keystore
> instead — see [wallet-setup.md](./guides/wallet-setup.md).

```env
ETH_PRIVATE_KEY_0=...
ETH_PRIVATE_KEY_1=...
```

### Recommended

* Use Filebase as your IPFS provider

---

# 🧩 Aggregators

### Step 1: Explore Model

```bash
dincli task explore 0
```

### Step 2: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 3: Register (if state = `DINaggregatorsRegistrationStarted`)

```bash
# Register wallet (example: account index 0; saved as 'default', the active fallback)
dincli system register-wallet --account 0

# Check ETH balance
dincli system --eth-balance

# Buy DIN tokens
dincli aggregator dintoken buy 0.00001

# Stake tokens
dincli aggregator dintoken stake 10

# Verify stake
dincli aggregator dintoken read-stake

# Register as aggregator
dincli aggregator register 0
```

### Step 4: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 5: Check your Aggregation Batch (if state = `T1nT2Bcreated`)

```bash
# Check T1 batch assigned to you
dincli model-owner aggregation show-t1-batches 0 --detailed

# Check T2 batch assigned to you
dincli model-owner aggregation show-t2-batches 0 --detailed
```

---

### Step 6: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 7: Aggregate your T1 Batch (if state = `T1AggregationStarted`)

```bash
# show the aggregator its assigned t1 batches if assigned
dincli aggregator show-t1-batches 0 --detailed

# aggregate the assigned t1 batches
dincli aggregator aggregate-t1 0 --submit
```

---

### Step 8: Aggregate your T2 Batch (if state = `T2AggregationStarted`)

```bash
# show the aggregator its assigned t2 batches if assigned
dincli aggregator show-t2-batches 0 --detailed

# aggregate the assigned t2 batches
dincli aggregator aggregate-t2 0 --submit
```

> 💡 T1 and T2 batch assignments depend on the current Global Iteration state and protocol allocation logic. A registered aggregator may not receive a batch in every iteration.

---

# 🛡️ Auditors

### Step 1: Explore Model

```bash
dincli task explore 0
```

### Step 2: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 3: Register (if state = `DINauditorsRegistrationStarted`)

```bash
# Register wallet (saved as 'default', the active fallback)
dincli system register-wallet --account 0

# Check ETH balance
dincli system --eth-balance

# Buy DIN tokens
dincli auditor dintoken buy 0.00001

# Stake tokens
dincli auditor dintoken stake 10

# Verify stake
dincli auditor dintoken read-stake

# Register as auditor
dincli auditor register 0
```

---

### Step 4: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 5: Check your Auditor Batch (if state = `AuditorsBatchesCreated`)

```bash
dincli auditor lms-evaluation show-batch 0
```

If a batch is shown, you will soon be required to audit it.

---

### Step 6: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 7: Audit your assigned batch (if state = `LMSevaluationStarted`)

```bash
# check your assigned batch
dincli auditor lms-evaluation show-batch 0

# audit your batch (scripts run automatically)
dincli auditor lms-evaluation evaluate 0 --submit
```
> 💡 Auditor batch assignments depend on the current Global Iteration state and protocol allocation logic. A registered auditor may not receive a batch in every iteration.

---


# 🤖 Clients


* Train local models using their dataset partition
* Submit model updates to the network

## 📊 MNIST Dataset Distribution

Model_0 uses the **MNIST dataset**, which is integrated into `dincli` for ease of use for clients. If you have your own MNIST dataset please proceed to **Dataset Requirements** subsection. Otherwise you can distribute the dataset as follows:

### 📦 Distribute Dataset

```bash
dincli system dataset distribute-mnist \
  --seed <seed> \
  --model-id <model-id> \
  --test-train \
  --clients \
  --num-clients <num-clients> \
  --start-client-index <start-client-index>
```

where:

| Argument               | Description                         |
| ---------------------- | ----------------------------------- |
| `--seed`               | Random seed for shuffling           |
| `--model-id`           | Creates model directory             |
| `--test-train`         | Creates dataset directory           |
| `--clients`            | Enables client dataset distribution |
| `--num-clients`        | Number of participating clients     |
| `--start-client-index` | Starting wallet index               |

Example:

```bash
dincli system dataset distribute-mnist \
  --seed 42 \
  --model-id 0 \
  --test-train \
  --clients \
  --num-clients 9 \
  --start-client-index 0
```

### Account Indexing Requirement

Ensure sufficient private keys in `.env`.

#### Formal Requirement

```
MAX_INDEX ≥ start-client-index + num-clients - 1
```

#### Interpretation

* Clients are assigned sequentially and inclusively
* Total keys required = `num-clients`

#### Example

If:

* `start-client-index = 2`
* `num-clients = 9`

Then:

```
ETH_PRIVATE_KEY_2 → ETH_PRIVATE_KEY_10
```

## 📂 Dataset Requirements

Ensure your dataset is located at:

```
<CACHE_DIR>/sepolia_op_devnet/model_0/dataset/clients/<account_address>/data.pt
```

Find your cache directory:

```bash
dincli system get-cache-dir
```

## Training Process

### Step 1: Explore Model

```bash
dincli task explore 0
```

### Step 2: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 3: Submit Local Model (if state = `LMSstarted`)

```bash
# Register wallet (saved as 'default', the active fallback)
dincli system register-wallet --account 0

# Check ETH balance
dincli system --eth-balance

# Optional (Recommended Step) to ensure training is running fine locally
# Train locally without submitting 
dincli client train-lms 0

# Train and submit local model
dincli client train-lms 0 --submit

# Show submitted models
dincli client lms show-models 0
```

---

# 🧠 Final Notes

* Always verify the Global Iteration State before taking action
* Use multiple accounts strategically if desired
* Stay active in community channels for protocol updates and troubleshooting assistance

---

> 🚀 You are now ready to participate in **Model_0** and contribute to decentralized AI on the Infinite Zero Network.
